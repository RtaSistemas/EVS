"""
Testes para MetadataGenerator.

Cobertura: sem DAT, NORMAL (cria gamelist.xml), DRY_RUN (não grava),
AUDIT (registra operação), AUDIT sem AuditReport, catver.ini.
"""

from __future__ import annotations

import pytest

from emupipeline.core.execution_mode import AuditReport, ExecutionMode


@pytest.fixture
def dat(sample_dat):
    from emupipeline.core.dat_manager import DatMaster
    return DatMaster(sample_dat)


@pytest.fixture
def generator(dat, config_factory):
    config_factory()
    from emupipeline.steps.step_metadata import MetadataGenerator
    return MetadataGenerator(dat=dat)


# ---------------------------------------------------------------------------
# Guarda de entrada
# ---------------------------------------------------------------------------

class TestInputGuards:
    def test_no_dat_returns_early(self, config_factory, tmp_project):
        config_factory()
        from emupipeline.steps.step_metadata import MetadataGenerator
        gen = MetadataGenerator(dat=None)
        gen.run()  # não deve levantar exceção
        xml_out = tmp_project / "output" / "gamelist.xml"
        assert not xml_out.exists()

    def test_dat_passed_via_run(self, dat, config_factory, tmp_project):
        """DAT pode ser passado via run(dat=...) em vez do construtor."""
        config_factory()
        from emupipeline.steps.step_metadata import MetadataGenerator
        gen = MetadataGenerator()
        gen.run(dat=dat)  # não deve levantar exceção


# ---------------------------------------------------------------------------
# Modo NORMAL
# ---------------------------------------------------------------------------

class TestNormalMode:
    def test_creates_gamelist_xml(self, generator, tmp_project):
        (tmp_project / "output" / "roms" / "sf2.zip").write_bytes(b"ROM")
        generator.run()
        xml_out = tmp_project / "output" / "gamelist.xml"
        assert xml_out.exists()

    def test_xml_contains_game_entry(self, generator, tmp_project):
        (tmp_project / "output" / "roms" / "sf2.zip").write_bytes(b"ROM")
        generator.run()
        text = (tmp_project / "output" / "gamelist.xml").read_text()
        assert "<game>" in text or "<gameList>" in text

    def test_xml_has_game_name(self, generator, tmp_project):
        (tmp_project / "output" / "roms" / "sf2.zip").write_bytes(b"ROM")
        generator.run()
        text = (tmp_project / "output" / "gamelist.xml").read_text()
        # sf2 tem descrição "Street Fighter II"
        assert "Street Fighter" in text

    def test_entries_stat_set(self, generator, tmp_project):
        (tmp_project / "output" / "roms" / "sf2.zip").write_bytes(b"ROM")
        generator.run()
        assert generator.get_stats().get("entries", 0) >= 1

    def test_no_roms_in_dir_produces_empty_gamelist(self, generator, tmp_project):
        """Diretório output/roms vazio → gamelist.xml com zero entradas."""
        generator.run()
        xml_out = tmp_project / "output" / "gamelist.xml"
        assert xml_out.exists()
        text = xml_out.read_text()
        assert "<game>" not in text

    def test_includes_image_path_when_image_exists(self, dat, config_factory, tmp_project):
        """Quando imagem existe em output/images/<driver>/<rom>.webp, inclui <image>."""
        config_factory()
        # Cria ROM e imagem correspondente
        (tmp_project / "output" / "roms" / "sf2.zip").write_bytes(b"ROM")
        img_dir = tmp_project / "output" / "images" / "capcom"
        img_dir.mkdir(parents=True, exist_ok=True)
        (img_dir / "sf2.webp").write_bytes(b"WEBP")

        from emupipeline.steps.step_metadata import MetadataGenerator
        gen = MetadataGenerator(dat=dat)
        gen.run()

        text = (tmp_project / "output" / "gamelist.xml").read_text()
        assert "<image>" in text


# ---------------------------------------------------------------------------
# Modo DRY_RUN
# ---------------------------------------------------------------------------

class TestDryRunMode:
    def test_dry_run_does_not_create_xml(self, dat, config_factory, tmp_project):
        config_factory()
        (tmp_project / "output" / "roms" / "sf2.zip").write_bytes(b"ROM")

        from emupipeline.steps.step_metadata import MetadataGenerator
        MetadataGenerator(dat=dat, mode=ExecutionMode.DRY_RUN).run()

        xml_out = tmp_project / "output" / "gamelist.xml"
        assert not xml_out.exists()

    def test_dry_run_does_not_set_entries_stat(self, dat, config_factory, tmp_project):
        config_factory()
        (tmp_project / "output" / "roms" / "sf2.zip").write_bytes(b"ROM")

        from emupipeline.steps.step_metadata import MetadataGenerator
        gen = MetadataGenerator(dat=dat, mode=ExecutionMode.DRY_RUN)
        gen.run()
        assert "entries" not in gen.get_stats()


# ---------------------------------------------------------------------------
# Modo AUDIT
# ---------------------------------------------------------------------------

class TestAuditMode:
    def test_audit_records_operation(self, dat, config_factory, tmp_project):
        config_factory()
        (tmp_project / "output" / "roms" / "sf2.zip").write_bytes(b"ROM")

        audit = AuditReport()
        from emupipeline.steps.step_metadata import MetadataGenerator
        MetadataGenerator(dat=dat, mode=ExecutionMode.AUDIT, audit=audit).run()

        assert audit.total >= 1
        assert audit.entries()[0].action == "create_gamelist_xml"

    def test_audit_does_not_create_xml(self, dat, config_factory, tmp_project):
        config_factory()
        (tmp_project / "output" / "roms" / "sf2.zip").write_bytes(b"ROM")

        audit = AuditReport()
        from emupipeline.steps.step_metadata import MetadataGenerator
        MetadataGenerator(dat=dat, mode=ExecutionMode.AUDIT, audit=audit).run()

        xml_out = tmp_project / "output" / "gamelist.xml"
        assert not xml_out.exists()

    def test_audit_without_report_object_returns_early(self, dat, config_factory, tmp_project):
        config_factory()
        (tmp_project / "output" / "roms" / "sf2.zip").write_bytes(b"ROM")

        from emupipeline.steps.step_metadata import MetadataGenerator
        gen = MetadataGenerator(dat=dat, mode=ExecutionMode.AUDIT, audit=None)
        gen.run()  # não deve levantar exceção
        xml_out = tmp_project / "output" / "gamelist.xml"
        assert not xml_out.exists()

    def test_audit_does_not_create_parent_dir(self, dat, config_factory, tmp_project):
        """AUDIT mode não cria diretórios no disco."""
        config_factory()
        # Remove output/roms para o test ser limpo; XML ficaria em output/
        (tmp_project / "output" / "roms" / "sf2.zip").write_bytes(b"ROM")

        # Verifica que xml_out.parent não é criado em AUDIT
        xml_parent = tmp_project / "output"
        initial_contents = set(xml_parent.iterdir())

        audit = AuditReport()
        from emupipeline.steps.step_metadata import MetadataGenerator
        MetadataGenerator(dat=dat, mode=ExecutionMode.AUDIT, audit=audit).run()

        # Nenhum novo diretório deve ter sido criado
        new_contents = set(xml_parent.iterdir())
        assert new_contents == initial_contents


# ---------------------------------------------------------------------------
# _load_catver helper
# ---------------------------------------------------------------------------

class TestLoadCatver:
    def test_parses_category_section(self, tmp_path):
        from emupipeline.steps.step_metadata import MetadataGenerator
        catver = tmp_path / "catver.ini"
        catver.write_text(
            "[Category]\nsf2=Fighter / Versus\nkof97=Fighter / Versus\n[Other]\n",
            encoding="utf-8",
        )
        genres = MetadataGenerator._load_catver(catver)
        assert genres["sf2"] == "Fighter / Versus"
        assert genres["kof97"] == "Fighter / Versus"

    def test_ignores_content_before_category(self, tmp_path):
        from emupipeline.steps.step_metadata import MetadataGenerator
        catver = tmp_path / "catver.ini"
        catver.write_text(
            "[Header]\nVersion=1.0\n[Category]\ngame1=Shooter\n",
            encoding="utf-8",
        )
        genres = MetadataGenerator._load_catver(catver)
        assert "game1" in genres
        assert "Version" not in genres

    def test_stops_at_next_section(self, tmp_path):
        from emupipeline.steps.step_metadata import MetadataGenerator
        catver = tmp_path / "catver.ini"
        catver.write_text(
            "[Category]\ngame1=Shooter\n[OtherSection]\ngame2=Racing\n",
            encoding="utf-8",
        )
        genres = MetadataGenerator._load_catver(catver)
        assert "game1" in genres
        assert "game2" not in genres
