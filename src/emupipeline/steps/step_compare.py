"""Step 4 — Comparação de dois diretórios."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Optional

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.logger import setup_logger
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta

log = setup_logger("FolderComparator")


@register
class FolderComparator:
    meta = StepMeta(
        id="compare_folders",
        menu_number=4,
        label="Comparar duas pastas",
        group="ROMs & DATs",
        description="Lista arquivos comuns/exclusivos entre dois diretórios.",
        pipeline_order=999,
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

    def run(self, dir_a: str = "", dir_b: str = "", **kwargs: Any) -> None:
        if not dir_a or not dir_b:
            dir_a = input("Pasta A: ").strip()
            dir_b = input("Pasta B: ").strip()

        pa, pb = Path(dir_a), Path(dir_b)
        if not pa.exists() or not pb.exists():
            log.error("Um ou ambos os diretórios não existem.")
            return

        names_a = {p.name for p in pa.rglob("*") if p.is_file()}
        names_b = {p.name for p in pb.rglob("*") if p.is_file()}

        only_a  = sorted(names_a - names_b)
        only_b  = sorted(names_b - names_a)
        common  = sorted(names_a & names_b)

        print(f"\n  Exclusivos em A : {len(only_a)}")
        print(f"  Exclusivos em B : {len(only_b)}")
        print(f"  Em comum        : {len(common)}")

        self._stats = {"only_a": len(only_a), "only_b": len(only_b), "common": len(common)}

        cmp_cfg  = self._cfg.get("compare")
        copy_com = getattr(cmp_cfg, "copy_common", False)
        out_raw  = getattr(cmp_cfg, "output_dir",  None)

        if copy_com and out_raw and common and self._mode == ExecutionMode.NORMAL:
            out_dir = (self._cfg.base_dir / out_raw).resolve()
            if out_dir.exists():
                shutil.rmtree(out_dir)
            out_dir.mkdir(parents=True)
            for name in common:
                src = pa / name
                shutil.copy2(src, out_dir / name)
            log.info(f"Copiados {len(common)} arquivos em comum para {out_dir}")
