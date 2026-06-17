"""
Testes para DatSplitter.

Verifica filtros, geração de DATs e integração com StagingTransaction.
"""

from __future__ import annotations

from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

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
        first_run = set(f.name for f in (tmp_project / "output" / "dats").glob("*.dat"))
        splitter.run()
        second_run = set(f.name for f in (tmp_project / "output" / "dats").glob("*.dat"))
        assert first_run == second_run  # conteúdo idêntico, não acumulado
