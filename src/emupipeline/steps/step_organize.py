"""
Step 5 — Organização de imagens por fuzzy match contra o DAT.

Responsabilidade: associar imagens de nomes variados aos ROMs correspondentes,
criando symlinks relativos ou cópias na pasta de saída organizada.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Optional

from emupipeline.core.dat_manager import DatMaster
from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.processor import BaseProcessor
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta


@register
class ImageOrganizer(BaseProcessor):
    meta = StepMeta(
        id="organize_images",
        menu_number=5,
        label="Organizar imagens (fuzzy match DAT)",
        group="Imagens",
        description="Associa imagens a ROMs via DAT. Cria symlinks ou cópias.",
        requires_dat=True,
        pipeline_order=50,
    )

    def __init__(
        self,
        dat: Optional[DatMaster] = None,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        audit: Optional[AuditReport] = None,
    ) -> None:
        super().__init__("ImageOrganizer", mode=mode, audit=audit)
        self._dat = dat

        img_cfg = self.config.get("images")
        self._mode_img         = getattr(img_cfg, "mode",              "symlink")
        self._org_mode         = getattr(img_cfg, "organization_mode", "subfolders")
        self._overwrite        = getattr(img_cfg, "overwrite",         False)
        self._fuzzy_threshold  = getattr(img_cfg, "fuzzy_threshold",   0.80)
        self._valid_exts: set[str] = set(
            getattr(img_cfg, "valid_extensions", [".png", ".jpg", ".jpeg", ".gif", ".webp"])
        )

        self._unmatched: list[str] = []
        self._out_dir: Path = Path(".")

    def run(self, dat: Optional[DatMaster] = None, **kwargs: Any) -> None:
        self._dat = dat or self._dat
        if self._dat is None:
            self.logger.error("DatMaster não fornecido. Use run(dat=DatMaster(...))")
            return

        src_dir = self.config.get("paths", "input_imgs")
        out_dir = self.config.get("paths", "output_imgs")

        if not src_dir or not Path(src_dir).exists():
            self.logger.error(f"Diretório de imagens não encontrado: {src_dir}")
            return

        if self._mode == ExecutionMode.NORMAL:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
        files = self.scan(Path(src_dir), extensions=self._valid_exts)
        self._out_dir = Path(out_dir)
        self.run_parallel(files)
        self._save_unmatched_report()

    def process_file(self, file_path: Path) -> str:
        result = self._match_and_place(file_path, self._out_dir)
        if result in ("copied", "linked"):
            return "matched"
        if result == "no_match":
            return "unmatched"
        return result

    def _match_and_place(self, file_path: Path, out_dir: Path) -> str:
        """
        Match a single image against the DAT and place it in out_dir.

        Returns one of: "copied" | "linked" | "no_match" | "skipped_exists" |
                        "skipped_ext" | "dry_run" | "audit_recorded" | "error"
        """
        if file_path.suffix.lower() not in self._valid_exts:
            return "skipped_ext"

        if self._dat is None:
            self.logger.error("DatMaster não disponível em _match_and_place.")
            return "error"
        game, match_type = self._dat.search(file_path.name, self._fuzzy_threshold)

        if game is None:
            self._unmatched.append(file_path.name)
            return "no_match"

        # Clones usam o nome do parent para consolidar imagens
        rom_name = game.parent if game.parent else game.name

        if self._org_mode == "subfolders":
            dest_dir = out_dir / game.driver
        else:
            dest_dir = out_dir

        dest = dest_dir / f"{rom_name}{file_path.suffix.lower()}"

        if dest.exists() and not self._overwrite:
            return "skipped_exists"

        if self._mode == ExecutionMode.AUDIT:
            if self._audit is None:
                self.logger.error("AUDIT mode requer AuditReport injetado no construtor.")
                return "error"
            self._audit.record(
                step=self.name, action=f"create_{self._mode_img}",
                source=str(file_path), dest=str(dest),
                reason=f"match={match_type} game={rom_name}",
            )
            return "audit_recorded"

        if self._mode == ExecutionMode.DRY_RUN:
            self.logger.debug(f"[DRY] {match_type}: {file_path.name} → {dest.name}")
            return "dry_run"

        dest_dir.mkdir(parents=True, exist_ok=True)

        try:
            if dest.exists():
                dest.unlink()

            if self._mode_img == "symlink":
                rel = Path(os.path.relpath(file_path, dest.parent))
                dest.symlink_to(rel)
                return "linked"
            else:
                shutil.copy2(file_path, dest)
                return "copied"
        except Exception as exc:
            self.logger.error(f"Erro ao processar {file_path.name}: {exc}")
            return "error"

    def _save_unmatched_report(self) -> None:
        if not self._unmatched or self._mode != ExecutionMode.NORMAL:
            return
        reports_dir = self.config.get("paths", "output_reports")
        if reports_dir:
            Path(reports_dir).mkdir(parents=True, exist_ok=True)
            report = Path(reports_dir) / "unmatched_images.txt"
            report.write_text("\n".join(sorted(self._unmatched)), encoding="utf-8")
            self.logger.info(f"Imagens sem match: {len(self._unmatched)} → {report}")
