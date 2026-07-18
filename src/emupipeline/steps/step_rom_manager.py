"""
Step 2 — Organização de ROMs com IGIR.
Herda BaseProcessor (arquitetura consistente).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.processor import BaseProcessor
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta


@register
class RomManager(BaseProcessor):
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
        super().__init__("RomManager", mode=mode, audit=audit)

    def process_file(self, file_path: Path) -> str:
        return "not_applicable"

    def run(self, **kwargs: Any) -> None:
        if not shutil.which("igir"):
            self.logger.error("igir não encontrado no PATH. Instale: npm install -g igir")
            return

        roms_cfg = self.config.get("roms")
        if not getattr(roms_cfg, "enable_igir", True):
            self.logger.info("IGIR desabilitado no config (roms.enable_igir=false). Pulando.")
            return

        # Seleciona DATs gerados (preferido) ou DAT mestre como fallback
        dats_dir   = Path(self.config.get("paths", "output_dats"))
        dat_source = str(dats_dir / "*.dat") if (dats_dir.exists() and any(dats_dir.glob("*.dat"))) \
                     else str(self.config.get("paths", "dat_file"))

        input_roms  = str(self.config.get("paths", "input_roms"))
        output_roms = str(self.config.get("paths", "output_roms"))
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

        if self._mode == ExecutionMode.AUDIT:
            if self._audit is None:
                self.logger.error("AUDIT mode requer AuditReport injetado no construtor.")
                return
            self._audit.record(
                step=self.name, action="run_igir",
                source=dat_source, dest=output_roms,
                reason=f"merge={merge_mode} regions={regions}",
            )
            return

        if self._mode == ExecutionMode.DRY_RUN:
            self.logger.info(f"[DRY] Executaria: {' '.join(cmd)}")
            return

        self.logger.info(f"Executando IGIR: {' '.join(cmd[:4])} …")
        try:
            result = subprocess.run(cmd, timeout=7200, text=True, capture_output=True)
            if result.returncode == 0:
                self.logger.info("IGIR concluído com sucesso.")
                self.update_stat("success")
            else:
                self.logger.error(f"IGIR falhou (código {result.returncode}):\n{result.stderr[-500:]}")
                self.update_stat("error")
        except subprocess.TimeoutExpired:
            self.logger.error("IGIR timeout após 2 horas.")
            self.update_stat("timeout")
        except FileNotFoundError:
            self.logger.error("igir não encontrado. Instale: npm install -g igir")
            self.update_stat("error")
