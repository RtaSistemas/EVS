"""
Testes para DatSplitter.

Verifica filtros, geração de DATs e integração com StagingTransaction.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.steps.step_dat_split import DatSplitter


class TestDatSplitter:
    def test_split_creates_dat_per_driver(self, config_factory, sample_dat, tmp_project):
        config_factory()
        splitter = DatSplitter()
        splitter.run()

        out_dir = tmp_project / "output" / "dats"
        dats = list(out_dir.glob("*.dat"))
        assert len(dats) >= 2  # capcom.dat, snk.dat (misc.dat excluído por blacklist)

    def test_blacklist_excludes_games(self, config_factory, sample_dat, tmp_project):
        config_factory()
        splitter = DatSplitter()
        splitter.run()

        out_dir = tmp_project / "output" / "dats"
        # Verifica que nenhum DAT contém 'mahjong'
        for dat_file in out_dir.glob("*.dat"):
            root = ET.parse(dat_file).getroot()
            for machine in root:
                desc = (machine.findtext("description") or "").lower()
                assert "mahjong" not in desc, f"Jogo blacklistado encontrado em {dat_file.name}"

    def test_exclude_clones_removes_sf2ce(self, config_factory, sample_dat, tmp_project):
        config_factory()
        splitter = DatSplitter()
        splitter.run()

        out_dir = tmp_project / "output" / "dats"
        for dat_file in out_dir.glob("*.dat"):
            root = ET.parse(dat_file).getroot()
            for machine in root:
                assert machine.get("name") != "sf2ce", \
                    f"Clone sf2ce não deveria estar em {dat_file.name}"

    def test_stats_count_dats_created(self, config_factory, sample_dat):
        config_factory()
        splitter = DatSplitter()
        splitter.run()
        assert splitter.get_stats().get("dats_created", 0) >= 1

    def test_dry_run_creates_no_files(self, config_factory, sample_dat, tmp_project):
        config_factory()
        out_dir = tmp_project / "output" / "dats"
        splitter = DatSplitter(mode=ExecutionMode.DRY_RUN)
        splitter.run()
        assert len(list(out_dir.glob("*.dat"))) == 0

    def test_audit_records_without_writing(self, config_factory, sample_dat, tmp_project):
        config_factory()
        audit = AuditReport()
        out_dir = tmp_project / "output" / "dats"

        splitter = DatSplitter(mode=ExecutionMode.AUDIT, audit=audit)
        splitter.run()

        assert audit.total > 0
        assert len(list(out_dir.glob("*.dat"))) == 0

    def test_output_is_valid_xml(self, config_factory, sample_dat, tmp_project):
        config_factory()
        splitter = DatSplitter()
        splitter.run()

        out_dir = tmp_project / "output" / "dats"
        for dat_file in out_dir.glob("*.dat"):
            # Não deve lançar exceção
            ET.parse(dat_file)

    def test_output_dir_is_replaced(self, config_factory, sample_dat, tmp_project):
        """Segunda execução não mistura com resultados anteriores."""
        config_factory()
        splitter = DatSplitter()
        splitter.run()
        first_run = {f.name for f in (tmp_project / "output" / "dats").glob("*.dat")}
        splitter.run()
        second_run = {f.name for f in (tmp_project / "output" / "dats").glob("*.dat")}
        assert first_run == second_run  # conteúdo idêntico, não acumulado


class TestDatSplitterEdgeCases:
    def test_process_file_returns_not_applicable(self, config_factory, sample_dat):
        """process_file() é stub — sempre retorna 'not_applicable'."""
        config_factory()
        result = DatSplitter().process_file(Path())
        assert result == "not_applicable"

    def test_missing_dat_file_returns_without_output(self, config_factory, tmp_project):
        # Sem sample_dat, o arquivo test.dat não existe — cobre o early return
        config_factory()
        DatSplitter().run()
        assert len(list((tmp_project / "output" / "dats").glob("*.dat"))) == 0

    def test_invalid_xml_logs_error_and_returns(self, config_factory, tmp_project):
        config_factory()
        (tmp_project / "dats" / "test.dat").write_text("NOT_VALID_XML", encoding="utf-8")
        DatSplitter().run()
        assert len(list((tmp_project / "output" / "dats").glob("*.dat"))) == 0

    def test_audit_without_report_returns_early(self, config_factory, sample_dat, tmp_project):
        """AUDIT sem AuditReport: não deve criar arquivos nem levantar exceção."""
        config_factory()
        DatSplitter(mode=ExecutionMode.AUDIT, audit=None).run()
        assert len(list((tmp_project / "output" / "dats").glob("*.dat"))) == 0

    def test_combined_mode_creates_single_dat(self, config_factory, sample_dat, tmp_project):
        """split_by_driver=False deve gerar um único DAT combinado."""
        config_factory({"roms": {"split_by_driver": False}})
        DatSplitter().run()
        dats = list((tmp_project / "output" / "dats").glob("*.dat"))
        assert len(dats) == 1

    def test_write_dat_without_header(self, tmp_path):
        """_write_dat com header=None deve gerar XML válido sem <header>."""
        dest = tmp_path / "no_header.dat"
        machine = ET.Element("game", attrib={"name": "test_game"})
        DatSplitter._write_dat(dest, [machine], None)
        assert dest.exists()
        root = ET.parse(dest).getroot()
        assert root.tag == "datafile"
        assert root.find("header") is None

    def test_gen_bios_creates_bios_dat(self, config_factory, tmp_project):
        """generate_bios_file=True deve criar DAT separado com máquinas BIOS."""
        import textwrap
        dat_content = textwrap.dedent("""\
            <?xml version="1.0"?>
            <datafile>
              <header><n>Test</n></header>
              <game name="neogeo" isbios="yes" sourcefile="snk/neogeo.cpp">
                <description>Neo-Geo BIOS</description>
              </game>
              <game name="kof97" sourcefile="snk/neogeo.cpp">
                <description>The King of Fighters '97</description>
              </game>
            </datafile>
        """)
        (tmp_project / "dats").mkdir(exist_ok=True)
        (tmp_project / "dats" / "test.dat").write_text(dat_content, encoding="utf-8")
        config_factory({"roms": {"generate_bios_file": True, "blacklist": []}})

        DatSplitter().run()

        out_dir = tmp_project / "output" / "dats"
        bios_dat = out_dir / "00_BIOS_Global.dat"
        assert bios_dat.exists(), "DAT de BIOS deve ser criado"
        root = ET.parse(bios_dat).getroot()
        names = [m.get("name") for m in root.findall("game")]
        assert "neogeo" in names
