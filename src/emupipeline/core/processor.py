"""
BaseProcessor v5 — engine base para todos os steps.

Mudanças em relação à v4:
  - ExecutionMode injetado via construtor (não monkey-patch de classe)
  - AuditReport injetado opcionalmente
  - _executor_type por subclasse (THREAD vs PROCESS)
  - Controle de oversubscription CPU para ferramentas externas
  - dry_run permanece como atalho para DRY_RUN mode
"""

from __future__ import annotations

import os
import threading
import time
from abc import ABC, abstractmethod
from concurrent.futures import Executor, ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from emupipeline.core.config import cfg
from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.logger import setup_logger
from emupipeline.core.metrics import StepMetrics


class ExecutorType(Enum):
    THREAD  = auto()   # I/O-bound: subprocess, rede, disco
    PROCESS = auto()   # CPU-bound: PIL, numpy — contorna GIL


class BaseProcessor(ABC):
    """
    Engine base para processamento paralelo de arquivos.

    Subclasses implementam `process_file(path) -> str` e declaram
    `_executor_type` adequado ao tipo de tarefa.
    """

    _executor_type: ExecutorType = ExecutorType.THREAD

    def __init__(
        self,
        name: str,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        audit: Optional[AuditReport] = None,
    ) -> None:
        from emupipeline.core.config import cfg as _cfg
        self.name   = name
        self.logger = setup_logger(name)
        self.config = _cfg
        self._mode  = mode
        self._audit = audit

        self._stats: dict[str, int] = {}
        self._stats_lock = threading.Lock()
        self._metrics: Optional[StepMetrics] = None

    # ------------------------------------------------------------------
    # Atalhos de modo
    # ------------------------------------------------------------------

    @property
    def dry_run(self) -> bool:
        return self._mode == ExecutionMode.DRY_RUN

    @dry_run.setter
    def dry_run(self, value: bool) -> None:
        self._mode = ExecutionMode.DRY_RUN if value else ExecutionMode.NORMAL

    @property
    def audit_mode(self) -> bool:
        return self._mode == ExecutionMode.AUDIT

    # ------------------------------------------------------------------
    # Interface de template
    # ------------------------------------------------------------------

    @abstractmethod
    def process_file(self, file_path: Path) -> str:
        """
        Processa um único arquivo. Retorna string de status.
        Valores padrão: "processed" | "skipped" | "error" | "dry_run" | "audit_recorded"
        """
        ...

    def run(self, **kwargs: object) -> None:
        """Entry point do step — subclasses podem sobrescrever."""
        raise NotImplementedError(f"{self.__class__.__name__} deve implementar run()")

    # ------------------------------------------------------------------
    # Stats thread-safe
    # ------------------------------------------------------------------

    def update_stat(self, key: str, delta: int = 1) -> None:
        with self._stats_lock:
            self._stats[key] = self._stats.get(key, 0) + delta

    def get_stats(self) -> dict[str, int]:
        with self._stats_lock:
            return dict(self._stats)

    # ------------------------------------------------------------------
    # Varredura de diretório
    # ------------------------------------------------------------------

    def scan(
        self,
        directory: str | Path,
        extensions: Optional[set[str]] = None,
        recursive: bool = True,
    ) -> list[Path]:
        directory = Path(directory).resolve()
        if not directory.exists():
            self.logger.error(f"Diretório não existe: {directory}")
            return []

        self.logger.info(f"Escaneando: {directory}")
        files: list[Path] = []
        walk = directory.rglob("*") if recursive else directory.glob("*")
        for p in walk:
            if not p.is_file():
                continue
            if any(part.startswith(".") or part == "__pycache__" for part in p.parts):
                continue
            if extensions is None or p.suffix.lower() in extensions:
                files.append(p)

        self.logger.info(f"Encontrados {len(files)} arquivo(s).")
        return files

    # ------------------------------------------------------------------
    # Runner paralelo com executor configurável
    # ------------------------------------------------------------------

    def _make_executor(self, n: int) -> Executor:
        if self._executor_type == ExecutorType.PROCESS:
            # Limita a cpu_count-1 para não afogar o sistema
            safe = min(n, max(1, (os.cpu_count() or 2) - 1))
            return ProcessPoolExecutor(max_workers=safe)
        return ThreadPoolExecutor(max_workers=n)

    def run_parallel(self, files: list[Path], threads: Optional[int] = None) -> None:
        if not files:
            self.logger.warning("Nenhum arquivo para processar.")
            return

        n_threads = threads or cfg.get("global", "threads", 4)
        total = len(files)
        self.logger.info(f"Processando {total} arquivo(s) com {n_threads} worker(s).")

        # Inicia métricas
        self._metrics = StepMetrics(step_name=self.name, files_total=total)

        start = time.monotonic()
        done  = 0

        with self._make_executor(n_threads) as executor:
            future_map = {executor.submit(self._safe_process, f): f for f in files}
            for future in as_completed(future_map):
                status = future.result()
                self.update_stat(status)
                done += 1
                if done % max(1, total // 20) == 0:
                    pct = done / total * 100
                    print(f"\r  {self.name}: {done}/{total} ({pct:.0f}%)", end="", flush=True)

        print()  # quebra linha do progresso
        elapsed = time.monotonic() - start

        # Finaliza métricas
        if self._metrics:
            stats = self.get_stats()
            self._metrics.files_processed = stats.get("processed", 0) + stats.get("converted", 0)
            self._metrics.files_skipped   = sum(v for k, v in stats.items() if "skip" in k)
            self._metrics.files_error     = stats.get("error", 0)
            self._metrics.finish()

        self._log_summary(elapsed)

    def _safe_process(self, file_path: Path) -> str:
        try:
            return self.process_file(file_path)
        except Exception as exc:
            self.logger.error(f"Erro em {file_path.name}: {exc}", exc_info=True)
            return "error"

    def _log_summary(self, elapsed: float) -> None:
        stats = self.get_stats()
        self.logger.info(f"--- {self.name} concluído em {elapsed:.2f}s ---")
        for k, v in sorted(stats.items()):
            self.logger.info(f"  {k:<22}: {v}")
