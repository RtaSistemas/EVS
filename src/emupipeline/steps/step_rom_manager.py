"""
Step 2 — Organização de ROMs com IGIR.
Herda BaseProcessor (arquitetura consistente).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.processor import WholeRunStep
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta


@register
class RomManager(WholeRunStep):
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
        audit: AuditReport | None = None,
    ) -> None:
        super().__init__("RomManager", mode=mode, audit=audit)

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
            self._audit_record(
                action="run_igir",
                source=dat_source, dest=output_roms,
                reason=f"merge={merge_mode} regions={regions}",
            )
            return

        if self._mode == ExecutionMode.DRY_RUN:
            self.logger.info(f"[DRY] Executaria: {' '.join(cmd)}")
            return

        self.logger.info(f"Executando IGIR: {' '.join(cmd[:4])} …")
        success = self.run_subprocess(cmd, timeout=7200, src_name="igir", stderr_tail=500)
        if success:
            self.logger.info("IGIR concluído com sucesso.")
            self.update_stat("success")
        else:
            self.update_stat("error")
