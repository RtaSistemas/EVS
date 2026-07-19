"""
Step 3 — Validação do Romset contra o DAT.
Herda BaseProcessor (arquitetura consistente).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from emupipeline.core.dat_manager import DatMaster
from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.processor import BaseProcessor, WholeRunStep
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta


@register
class RomValidator(WholeRunStep):
    meta = StepMeta(
        id="validate_roms",
        menu_number=3,
        label="Validar Romset vs DAT",
        group="ROMs & DATs",
        description="Compara ROMs locais com o DAT. Gera relatório de faltantes e extras.",
        requires_dat=True,
        pipeline_order=999,
    )

    def __init__(
        self,
        dat: Optional[DatMaster] = None,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        audit: Optional[AuditReport] = None,
    ) -> None:
        super().__init__("RomValidator", mode=mode, audit=audit)
        self._dat = dat

    def run(self, dat: Optional[DatMaster] = None, **kwargs: Any) -> None:
        if not self._resolve_dat(dat):
            return

        roms_dir = self._resolve_dir(self.config.get("paths", "input_roms"), "Diretório de ROMs")
        if roms_dir is None:
            return

        local_names = {
            p.stem.lower()
            for p in roms_dir.rglob("*.zip")
        }
        dat_names = set(self._dat.rom_map.keys())

        missing = sorted(dat_names - local_names)
        extras  = sorted(local_names - dat_names)
        found   = len(dat_names) - len(missing)

        self.logger.info("=" * 50)
        self.logger.info("VALIDAÇÃO DO ROMSET")
        self.logger.info("=" * 50)
        self.logger.info(f"Total no DAT  : {len(dat_names)}")
        self.logger.info(f"Encontrados   : {found}")
        self.logger.info(f"Faltantes     : {len(missing)}")
        self.logger.info(f"Extras        : {len(extras)}")
        self.logger.info("=" * 50)

        self.update_stat("dat_total", len(dat_names))
        self.update_stat("found",     found)
        self.update_stat("missing",   len(missing))
        self.update_stat("extras",    len(extras))

        reports_dir = self.config.get("paths", "output_reports")
        if not reports_dir:
            return

        if self._mode == ExecutionMode.AUDIT:
            if not self._require_audit():
                return
            self._audit.record(
                step=self.name, action="write_validation_report",
                source=str(roms_dir),
                dest=str(Path(reports_dir) / "validation_report.txt"),
                reason=f"missing={len(missing)} extras={len(extras)}",
            )
            return

        if self._mode == ExecutionMode.DRY_RUN:
            self.logger.info("[DRY] Relatório de validação não gravado em disco.")
            return

        # NORMAL
        Path(reports_dir).mkdir(parents=True, exist_ok=True)
        report = Path(reports_dir) / "validation_report.txt"
        lines = [
            "=== FALTANTES ===", *missing, "",
            "=== EXTRAS ===",    *extras,
        ]
        report.write_text("\n".join(lines), encoding="utf-8")
        self.logger.info(f"Relatório salvo em: {report}")
