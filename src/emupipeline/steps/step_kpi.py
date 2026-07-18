"""Step 10 — Relatório KPI de uso de disco e contagem de arquivos.
Herda BaseProcessor (arquitetura consistente).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Optional

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.processor import BaseProcessor
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta


def _dir_stats(path: Path) -> tuple[int, int]:
    """Retorna (arquivo_count, bytes_total) — não conta symlinks."""
    count = size = 0
    try:
        for p in path.rglob("*"):
            if p.is_file() and not p.is_symlink():
                count += 1
                size  += p.stat().st_size
    except PermissionError:
        pass
    return count, size


@register
class KpiReporter(BaseProcessor):
    meta = StepMeta(
        id="kpi_report",
        menu_number=10,
        label="Relatório KPI (uso de disco)",
        group="Vídeo & Metadados",
        description="Gera relatório de arquivos e uso de disco por diretório.",
        pipeline_order=100,
    )

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        audit: Optional[AuditReport] = None,
    ) -> None:
        super().__init__("KpiReporter", mode=mode, audit=audit)

    def process_file(self, file_path: Path) -> str:
        return "not_applicable"

    def run(self, **kwargs: Any) -> None:
        targets = {
            "ROMs (entrada)":    self.config.get("paths", "input_roms"),
            "ROMs (saída)":      self.config.get("paths", "output_roms"),
            "Imagens (entrada)": self.config.get("paths", "input_imgs"),
            "Imagens (saída)":   self.config.get("paths", "output_imgs"),
            "Vídeos":            self.config.get("paths", "videos_dir"),
        }

        rows: list[tuple[str, int, float]] = []
        for label, path in targets.items():
            if path and Path(str(path)).exists():
                count, size = _dir_stats(Path(str(path)))
                rows.append((label, count, size / 1024 / 1024))

        if self._mode == ExecutionMode.AUDIT:
            if self._audit is None:
                self.logger.error("AUDIT mode requer AuditReport injetado no construtor.")
                return
            for label, path in targets.items():
                if path and Path(str(path)).exists():
                    count, size = _dir_stats(Path(str(path)))
                    self._audit.record(
                        step=self.name, action="analyze_dir",
                        source=str(path),
                        reason=f"{label}: {count} arqs, {size / 1024 / 1024:.1f}MB",
                    )
            return

        if self._mode == ExecutionMode.DRY_RUN:
            self.logger.info(f"[DRY] Analisaria {len(rows)} diretórios.")
            return

        # NORMAL: exibe tabela via logger
        self._log_table(rows)

        # Salva CSV usando módulo csv para quoting correto
        reports_dir = self.config.get("paths", "output_reports")
        if reports_dir:
            Path(str(reports_dir)).mkdir(parents=True, exist_ok=True)
            csv_path = Path(str(reports_dir)) / "kpi.csv"
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["local", "arquivos", "tamanho_mb"])
            for label, count, mb in rows:
                writer.writerow([label, count, f"{mb:.2f}"])
            csv_path.write_text(buf.getvalue(), encoding="utf-8")
            self.logger.info(f"KPI salvo em: {csv_path}")

        self._stats["directories_analyzed"] = len(rows)

    def _log_table(self, rows: list[tuple[str, int, float]]) -> None:
        sep = "─" * 55
        lines = [
            "",
            sep,
            f"  {'Local':<28} {'Arquivos':>9}  {'Tamanho (MB)':>12}",
            sep,
        ]
        for label, count, mb in rows:
            lines.append(f"  {label:<28} {count:>9}  {mb:>12.1f}")
        lines.append(sep)
        self.logger.info("\n".join(lines))
