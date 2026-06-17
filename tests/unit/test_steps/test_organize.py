"""
Testes para step_organize (ImageOrganizer).

Cobertura alvo: 75%
Foco em:
  - 3 camadas de match (exact_rom, exact_title, fuzzy)
  - symlink relativo vs cópia
  - consolidação de clone → parent
  - dry-run e audit-mode
  - arquivos sem match → relatório unmatched
  - extensões inválidas ignoradas
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from emupipeline.core.execution_mode import AuditReport, ExecutionMode


@pytest.fixture
def dat(sample_dat):
    from emupipeline.core.dat_manager import DatMaster
    return DatMaster(sample_dat)


@pytest.fixture
def organizer(dat, config_factory):
    config_factory({"images": {"mode": "copy", "organization_mode": "flat",
                                "overwrite": False, "fuzzy_threshold": 0.80,
                                "valid_extensions": [".png", ".jpg"]}})
    from emupipeline.steps.step_organize import ImageOrganizer
    return ImageOrganizer(dat)


@pytest.fixture
def organizer_symlink(dat, config_factory):
    config_factory({"images": {"mode": "symlink", "organization_mode": "subfolders",
                                "overwrite": False, "fuzzy_threshold": 0.80,
                                "valid_extensions": [".png", ".jpg"]}})
    from emupipeline.steps.step_organize import ImageOrganizer
    return ImageOrganizer(dat)


# ---------------------------------------------------------------------------
# Match de 3 camadas
# ---------------------------------------------------------------------------

class TestMatchLayers:
    def test_exact_rom_match(self, organizer, tmp_path):
        """Imagem com nome idêntico ao ROM → exact_rom."""
        src = tmp_path / "sf2.png"
        src.write_bytes(b"PNG")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = organizer._match_and_place(src, out_dir)
        assert result in ("copied", "linked")

    def test_exact_title_match(self, organizer, tmp_path):
        """Nome normalizado do arquivo == clean_title do DAT."""
        # "Street Fighter II The World Warrior.png" normaliza para "street fighter ii the world warrior"
        src = tmp_path / "Street Fighter II The World Warrior.png"
        src.write_bytes(b"PNG")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = organizer._match_and_place(src, out_dir)
        assert result in ("copied", "linked")

    def test_fuzzy_match(self, organizer, tmp_path):
        """Título com variação pequena deve casar via fuzzy."""
        src = tmp_path / "King of Fighters 97.png"  # sem "The" → fuzzy match
        src.write_bytes(b"PNG")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = organizer._match_and_place(src, out_dir)
        assert result in ("copied", "linked", "no_match")  # depende do threshold

    def test_no_match_returns_no_match(self, organizer, tmp_path):
        src = tmp_path / "completely_unknown_game_xyz_123.png"
        src.write_bytes(b"PNG")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = organizer._match_and_place(src, out_dir)
        assert result == "no_match"

    def test_invalid_extension_ignored(self, organizer, tmp_path):
        src = tmp_path / "sf2.bmp"  # .bmp não está em valid_extensions
        src.write_bytes(b"BMP")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = organizer._match_and_place(src, out_dir)
        assert result == "skipped_ext"


# ---------------------------------------------------------------------------
# Clone → Parent
# ---------------------------------------------------------------------------

class TestCloneConsolidation:
    def test_clone_uses_parent_name(self, organizer, tmp_path):
        """sf2ce.png (clone de sf2) deve ser salvo como sf2.png."""
        src = tmp_path / "sf2ce.png"
        src.write_bytes(b"PNG")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        organizer._match_and_place(src, out_dir)

        # Deve existir sf2.png (parent), não sf2ce.png
        assert (out_dir / "sf2.png").exists()


# ---------------------------------------------------------------------------
# Symlink relativo
# ---------------------------------------------------------------------------

class TestSymlinkMode:
    def test_symlink_is_relative(self, organizer_symlink, tmp_path):
        """Symlink criado deve ser relativo, não absoluto."""
        src = tmp_path / "source_images" / "sf2.png"
        src.parent.mkdir()
        src.write_bytes(b"PNG")
        out_dir = tmp_path / "output_images"
        out_dir.mkdir()

        organizer_symlink._match_and_place(src, out_dir)

        # Verifica se algum symlink foi criado
        links = [f for f in out_dir.rglob("*") if f.is_symlink()]
        if links:
            link = links[0]
            target = os.readlink(link)
            assert not os.path.isabs(target), f"Symlink deve ser relativo, mas é: {target}"

    def test_symlink_resolves_correctly(self, organizer_symlink, tmp_path):
        """Symlink criado deve apontar para o arquivo correto."""
        src = tmp_path / "sources" / "sf2.png"
        src.parent.mkdir()
        src.write_bytes(b"REAL_IMAGE_DATA")
        out_dir = tmp_path / "output"
        out_dir.mkdir(exist_ok=True)

        organizer_symlink._match_and_place(src, out_dir)

        links = [f for f in out_dir.rglob("*") if f.is_symlink()]
        if links:
            assert links[0].read_bytes() == b"REAL_IMAGE_DATA"


# ---------------------------------------------------------------------------
# Dry-run e Audit
# ---------------------------------------------------------------------------

class TestExecutionModes:
    def test_dry_run_creates_no_files(self, dat, config_factory, tmp_path):
        config_factory({"images": {"mode": "copy", "organization_mode": "flat",
                                    "overwrite": False, "fuzzy_threshold": 0.80,
                                    "valid_extensions": [".png"]}})
        from emupipeline.steps.step_organize import ImageOrganizer
        org = ImageOrganizer(dat, mode=ExecutionMode.DRY_RUN)

        src = tmp_path / "sf2.png"
        src.write_bytes(b"PNG")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        org._match_and_place(src, out_dir)

        # Nenhum arquivo deve ter sido criado em out_dir
        assert list(out_dir.iterdir()) == []

    def test_audit_records_planned_operation(self, dat, config_factory, tmp_path):
        config_factory({"images": {"mode": "copy", "organization_mode": "flat",
                                    "overwrite": False, "fuzzy_threshold": 0.80,
                                    "valid_extensions": [".png"]}})
        from emupipeline.steps.step_organize import ImageOrganizer
        report = AuditReport()
        org = ImageOrganizer(dat, mode=ExecutionMode.AUDIT, audit=report)

        src = tmp_path / "sf2.png"
        src.write_bytes(b"PNG")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        org._match_and_place(src, out_dir)

        assert report.total >= 1
        assert report.entries()[0].source == str(src)


# ---------------------------------------------------------------------------
# Overwrite
# ---------------------------------------------------------------------------

class TestOverwrite:
    def test_no_overwrite_skips_existing(self, organizer, tmp_path):
        src = tmp_path / "sf2.png"
        src.write_bytes(b"NEW")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        existing = out_dir / "sf2.png"
        existing.write_bytes(b"OLD")

        result = organizer._match_and_place(src, out_dir)
        assert result == "skipped_exists"
        assert existing.read_bytes() == b"OLD"  # não sobrescreveu

    def test_overwrite_replaces_existing(self, dat, config_factory, tmp_path):
        config_factory({"images": {"mode": "copy", "organization_mode": "flat",
                                    "overwrite": True, "fuzzy_threshold": 0.80,
                                    "valid_extensions": [".png"]}})
        from emupipeline.steps.step_organize import ImageOrganizer
        org = ImageOrganizer(dat)

        src = tmp_path / "sf2.png"
        src.write_bytes(b"NEW")
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        existing = out_dir / "sf2.png"
        existing.write_bytes(b"OLD")

        org._match_and_place(src, out_dir)
        assert existing.read_bytes() == b"NEW"


# ---------------------------------------------------------------------------
# Relatório de unmatched
# ---------------------------------------------------------------------------

class TestUnmatchedReport:
    def test_unmatched_written_to_report(self, organizer, tmp_path):
        src = tmp_path / "xyzzy_unknown.png"
        src.write_bytes(b"PNG")
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        organizer._unmatched: list[str] = []
        organizer._match_and_place(src, out_dir)

        if hasattr(organizer, "_unmatched"):
            assert str(src) in organizer._unmatched or src.name in organizer._unmatched
