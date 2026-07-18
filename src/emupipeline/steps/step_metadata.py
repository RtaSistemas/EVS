"""Step 9 — Geração de gamelist.xml para EmulationStation.
Herda BaseProcessor (arquitetura consistente).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional

from emupipeline.core.dat_manager import DatMaster
from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.processor import BaseProcessor
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta


@register
class MetadataGenerator(BaseProcessor):
    meta = StepMeta(
        id="generate_metadata",
        menu_number=9,
        label="Gerar gamelist.xml",
        group="Vídeo & Metadados",
        description="Gera gamelist.xml com metadados para EmulationStation.",
        requires_dat=True,
        pipeline_order=90,
    )

    def __init__(
        self,
        dat: Optional[DatMaster] = None,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        audit: Optional[AuditReport] = None,
    ) -> None:
        super().__init__("MetadataGenerator", mode=mode, audit=audit)
        self._dat = dat

    def process_file(self, file_path: Path) -> str:
        return "not_applicable"

    def run(self, dat: Optional[DatMaster] = None, **kwargs: Any) -> None:
        self._dat = dat or self._dat
        if self._dat is None:
            self.logger.error("DatMaster não fornecido.")
            return

        roms_dir   = Path(str(self.config.get("paths", "output_roms")))
        imgs_dir   = Path(str(self.config.get("paths", "output_imgs")))
        xml_out    = Path(str(self.config.get("paths", "output_xml")))
        catver_raw = self.config.get("paths", "catver_ini")
        catver     = Path(str(catver_raw)) if catver_raw else None

        # Carrega catver.ini se disponível
        genres: dict[str, str] = {}
        if catver and Path(str(catver)).exists():
            genres = self._load_catver(Path(str(catver)))

        root = ET.Element("gameList")
        count = 0

        for rom_path in sorted(roms_dir.rglob("*.zip")):
            rom_name = rom_path.stem.lower()
            game = self._dat.get_game(rom_name)
            if game is None:
                continue

            # Procura imagem correspondente
            img_path: Optional[Path] = None
            for ext in (".webp", ".png", ".jpg"):
                candidate = imgs_dir / game.driver / f"{rom_name}{ext}"
                if candidate.exists():
                    img_path = candidate
                    break

            game_el = ET.SubElement(root, "game")
            ET.SubElement(game_el, "path").text  = f"./{rom_path.relative_to(roms_dir.parent)}"
            ET.SubElement(game_el, "n").text     = game.description
            ET.SubElement(game_el, "desc").text  = f"Driver: {game.driver}"
            ET.SubElement(game_el, "genre").text = genres.get(rom_name, "")
            if img_path:
                ET.SubElement(game_el, "image").text = f"./{img_path.relative_to(xml_out.parent)}"
            count += 1

        if self._mode == ExecutionMode.AUDIT:
            if self._audit is None:
                self.logger.error("AUDIT mode requer AuditReport injetado no construtor.")
                return
            self._audit.record(
                step=self.name, action="create_gamelist_xml",
                source=str(roms_dir), dest=str(xml_out),
                reason=f"{count} jogos",
            )
            return

        if self._mode == ExecutionMode.DRY_RUN:
            self.logger.info(f"[DRY] Geraria gamelist.xml com {count} entradas em {xml_out}")
            return

        # NORMAL
        xml_out.parent.mkdir(parents=True, exist_ok=True)
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(xml_out, encoding="UTF-8", xml_declaration=True)
        self._stats["entries"] = count
        self.logger.info(f"gamelist.xml gerado: {count} jogos → {xml_out}")

    @staticmethod
    def _load_catver(path: Path) -> dict[str, str]:
        genres: dict[str, str] = {}
        in_section = False
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line == "[Category]":
                in_section = True
                continue
            if in_section and line.startswith("["):
                break
            if in_section and "=" in line:
                name, genre = line.split("=", 1)
                genres[name.strip().lower()] = genre.strip()
        return genres
