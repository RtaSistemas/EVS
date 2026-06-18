"""
Step 2 — Organização de ROMs com IGIR.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.logger import setup_logger
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta

log = setup_logger("RomManager")


@register
class RomManager:
    meta = StepMeta(
        id="rom_manager",
        menu_number=2,
        label="Organizar ROMs (IGIR)",
        group="ROMs & DATs",
        description="Usa IGIR para organizar, verificar e renomear ROMs.",
        pipeline_order=20,
    )

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        audit: Optional[AuditReport] = None,
    ) -> None:
        from emupipeline.core.config import cfg
        self._cfg   = cfg
        self._mode  = mode
        self._audit = audit
        self._stats: dict[str, int] = {}

    def get_stats(self) -> dict[str, int]:
        return dict(self._stats)

    def run(self, **kwargs: Any) -> None:
        if not shutil.which("igir"):
            log.error("igir não encontrado no PATH. Instale: npm install -g igir")
            return

        roms_cfg = self._cfg.get("roms")
        if not getattr(roms_cfg, "enable_igir", True):
            log.info("IGIR desabilitado no config (roms.enable_igir=false). Pulando.")
            return

        # Seleciona DATs gerados (preferido) ou DAT mestre como fallback
        dats_dir   = Path(self._cfg.get("paths", "output_dats"))
        dat_source = str(dats_dir / "*.dat") if (dats_dir.exists() and any(dats_dir.glob("*.dat"))) \
                     else str(self._cfg.get("paths", "dat_file"))

        input_roms  = str(self._cfg.get("paths", "input_roms"))
        output_roms = str(self._cfg.get("paths", "output_roms"))
        merge_mode  = getattr(roms_cfg, "merge_mode", "nonmerged")
        regions     = getattr(roms_cfg, "filter_regions", "WORLD,USA")
        threads_io  = str(getattr(roms_cfg, "threads_io", 4))

        cmd = [
            "igir", "copy",
            "--dat",        dat_source,
            "--input",      input_roms,
            "--output",     output_roms,
            "--merge-roms", merge_mode,
            "--prefer-regions", *regions.split(","),
            "--threads",    threads_io,
            "--verbose",
        ]

        if self._mode == ExecutionMode.DRY_RUN:
            log.info(f"[DRY] Executaria: {' '.join(cmd)}")
            return

        log.info(f"Executando IGIR: {' '.join(cmd[:4])} …")
        try:
            result = subprocess.run(cmd, timeout=7200, text=True, capture_output=True)
            if result.returncode == 0:
                log.info("IGIR concluído com sucesso.")
                self._stats["success"] = 1
            else:
                log.error(f"IGIR falhou (código {result.returncode}):\n{result.stderr[-500:]}")
                self._stats["error"] = 1
        except subprocess.TimeoutExpired:
            log.error("IGIR timeout após 2 horas.")
            self._stats["timeout"] = 1
        except FileNotFoundError:
            log.error("igir não encontrado. Instale: npm install -g igir")
            self._stats["error"] = 1
