"""
Step 3 — Validação do Romset contra o DAT.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from emupipeline.core.dat_manager import DatMaster
from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.logger import setup_logger
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta

log = setup_logger("RomValidator")


@register
class RomValidator:
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
        from emupipeline.core.config import cfg
        self._cfg   = cfg
        self._dat   = dat
        self._mode  = mode
        self._stats: dict[str, int] = {}

    def get_stats(self) -> dict[str, int]:
        return dict(self._stats)

    def run(self, dat: Optional[DatMaster] = None, **kwargs: Any) -> None:
        self._dat = dat or self._dat
        if self._dat is None:
            log.error("DatMaster não fornecido.")
            return

        roms_dir = self._cfg.get("paths", "input_roms")
        if not roms_dir or not Path(roms_dir).exists():
            log.error(f"Diretório de ROMs não encontrado: {roms_dir}")
            return

        local_names = {
            p.stem.lower()
            for p in Path(roms_dir).rglob("*.zip")
        }
        dat_names = set(self._dat.rom_map.keys())

        missing = sorted(dat_names - local_names)
        extras  = sorted(local_names - dat_names)
        found   = len(dat_names) - len(missing)

        print(f"\n{'='*50}")
        print(f"VALIDAÇÃO DO ROMSET")
        print(f"{'='*50}")
        print(f"Total no DAT  : {len(dat_names)}")
        print(f"Encontrados   : {found}")
        print(f"Faltantes     : {len(missing)}")
        print(f"Extras        : {len(extras)}")
        print(f"{'='*50}\n")

        self._stats = {
            "dat_total": len(dat_names),
            "found": found,
            "missing": len(missing),
            "extras": len(extras),
        }

        reports_dir = self._cfg.get("paths", "output_reports")
        if reports_dir:
            if self._mode != ExecutionMode.NORMAL:
                log.info(f"[{self._mode.name}] Relatório de validação não gravado em disco.")
                return
            Path(reports_dir).mkdir(parents=True, exist_ok=True)
            report = Path(reports_dir) / "validation_report.txt"
            lines = [
                "=== FALTANTES ===", *missing, "",
                "=== EXTRAS ===",    *extras,
            ]
            report.write_text("\n".join(lines), encoding="utf-8")
            log.info(f"Relatório salvo em: {report}")
