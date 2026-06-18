"""Step 10 — Relatório KPI de uso de disco e contagem de arquivos."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Optional

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.logger import setup_logger
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta

log = setup_logger("KpiReporter")


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
class KpiReporter:
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
        from emupipeline.core.config import cfg
        self._cfg   = cfg
        self._mode  = mode
        self._stats: dict[str, int] = {}

    def get_stats(self) -> dict[str, int]:
        return dict(self._stats)

    def run(self, **kwargs: Any) -> None:
        targets = {
            "ROMs (entrada)":    self._cfg.get("paths", "input_roms"),
            "ROMs (saída)":      self._cfg.get("paths", "output_roms"),
            "Imagens (entrada)": self._cfg.get("paths", "input_imgs"),
            "Imagens (saída)":   self._cfg.get("paths", "output_imgs"),
            "Vídeos":            self._cfg.get("paths", "videos_dir"),
        }

        rows: list[tuple[str, int, float]] = []
        for label, path in targets.items():
            if path and Path(str(path)).exists():
                count, size = _dir_stats(Path(str(path)))
                rows.append((label, count, size / 1024 / 1024))

        # Exibe tabela
        print(f"\n{'─'*55}")
        print(f"  {'Local':<28} {'Arquivos':>9}  {'Tamanho (MB)':>12}")
        print(f"{'─'*55}")
        for label, count, mb in rows:
            print(f"  {label:<28} {count:>9}  {mb:>12.1f}")
        print(f"{'─'*55}\n")

        # Salva CSV usando módulo csv para quoting correto
        reports_dir = self._cfg.get("paths", "output_reports")
        if reports_dir:
            if self._mode != ExecutionMode.NORMAL:
                log.info(f"[{self._mode.name}] KPI CSV não gravado em disco.")
                return
            Path(str(reports_dir)).mkdir(parents=True, exist_ok=True)
            csv_path = Path(str(reports_dir)) / "kpi.csv"
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(["local", "arquivos", "tamanho_mb"])
            for label, count, mb in rows:
                writer.writerow([label, count, f"{mb:.2f}"])
            csv_path.write_text(buf.getvalue(), encoding="utf-8")
            log.info(f"KPI salvo em: {csv_path}")

        self._stats["directories_analyzed"] = len(rows)
