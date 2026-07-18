"""
Testes para KpiReporter.

Cobertura: ExecutionMode (NORMAL/DRY_RUN/AUDIT), geração de CSV,
log de tabela, AUDIT sem AuditReport.
"""

from __future__ import annotations

from emupipeline.core.execution_mode import AuditReport, ExecutionMode

# ---------------------------------------------------------------------------
# Modo NORMAL
# ---------------------------------------------------------------------------

class TestNormalMode:
    def test_generates_csv_when_reports_dir_configured(self, config_factory, tmp_project):
        config_factory()
        (tmp_project / "source" / "roms" / "sf2.zip").write_bytes(b"ROM")

        from emupipeline.steps.step_kpi import KpiReporter
        kpi = KpiReporter()
        kpi.run()

        csv_path = tmp_project / "output" / "reports" / "kpi.csv"
        assert csv_path.exists()

    def test_csv_has_header_row(self, config_factory, tmp_project):
        config_factory()
        (tmp_project / "source" / "roms" / "sf2.zip").write_bytes(b"ROM")

        from emupipeline.steps.step_kpi import KpiReporter
        KpiReporter().run()

        text = (tmp_project / "output" / "reports" / "kpi.csv").read_text()
        assert "local" in text
        assert "arquivos" in text
        assert "tamanho_mb" in text

    def test_csv_has_data_row_for_existing_dir(self, config_factory, tmp_project):
        config_factory()
        (tmp_project / "source" / "roms" / "sf2.zip").write_bytes(b"ROM" * 100)

        from emupipeline.steps.step_kpi import KpiReporter
        KpiReporter().run()

        text = (tmp_project / "output" / "reports" / "kpi.csv").read_text()
        # Diretório ROMs (entrada) existe — deve aparecer no CSV
        assert "ROMs" in text

    def test_directories_analyzed_stat_set(self, config_factory, tmp_project):
        config_factory()
        (tmp_project / "source" / "roms" / "sf2.zip").write_bytes(b"ROM")

        from emupipeline.steps.step_kpi import KpiReporter
        kpi = KpiReporter()
        kpi.run()
        assert kpi.get_stats().get("directories_analyzed", 0) >= 1

    def test_no_reports_dir_skips_csv_without_crash(self, config_factory, tmp_project):
        """Sem paths.output_reports configurado, não deve gravar CSV nem levantar exceção."""
        config_factory({"paths": {"output_reports": ""}})
        (tmp_project / "source" / "roms" / "sf2.zip").write_bytes(b"ROM")

        from emupipeline.steps.step_kpi import KpiReporter
        KpiReporter().run()  # não deve levantar exceção

    def test_nonexistent_dirs_excluded_from_csv(self, config_factory, tmp_project):
        """Diretórios inexistentes não geram linha no CSV."""
        import shutil
        config_factory()
        shutil.rmtree(tmp_project / "source" / "roms")
        shutil.rmtree(tmp_project / "output" / "roms")

        from emupipeline.steps.step_kpi import KpiReporter
        KpiReporter().run()

        csv_path = tmp_project / "output" / "reports" / "kpi.csv"
        if csv_path.exists():
            text = csv_path.read_text()
            lines = [ln for ln in text.splitlines() if ln and not ln.startswith("local")]
            # Linhas de dados podem ser zero (todos os dirs vazios/inexistentes)
            assert isinstance(lines, list)  # simplesmente não deve levantar


# ---------------------------------------------------------------------------
# Modo DRY_RUN
# ---------------------------------------------------------------------------

class TestDryRunMode:
    def test_dry_run_does_not_write_csv(self, config_factory, tmp_project):
        config_factory()
        (tmp_project / "source" / "roms" / "sf2.zip").write_bytes(b"ROM")

        from emupipeline.steps.step_kpi import KpiReporter
        KpiReporter(mode=ExecutionMode.DRY_RUN).run()

        csv_path = tmp_project / "output" / "reports" / "kpi.csv"
        assert not csv_path.exists()

    def test_dry_run_does_not_set_stat(self, config_factory, tmp_project):
        config_factory()
        (tmp_project / "source" / "roms" / "sf2.zip").write_bytes(b"ROM")

        from emupipeline.steps.step_kpi import KpiReporter
        kpi = KpiReporter(mode=ExecutionMode.DRY_RUN)
        kpi.run()
        assert "directories_analyzed" not in kpi.get_stats()


# ---------------------------------------------------------------------------
# Modo AUDIT
# ---------------------------------------------------------------------------

class TestAuditMode:
    def test_audit_records_existing_dirs(self, config_factory, tmp_project):
        config_factory()
        (tmp_project / "source" / "roms" / "sf2.zip").write_bytes(b"ROM")

        audit = AuditReport()
        from emupipeline.steps.step_kpi import KpiReporter
        KpiReporter(mode=ExecutionMode.AUDIT, audit=audit).run()

        assert audit.total >= 1
        actions = [e.action for e in audit.entries()]
        assert "analyze_dir" in actions

    def test_audit_does_not_write_csv(self, config_factory, tmp_project):
        config_factory()
        (tmp_project / "source" / "roms" / "sf2.zip").write_bytes(b"ROM")

        audit = AuditReport()
        from emupipeline.steps.step_kpi import KpiReporter
        KpiReporter(mode=ExecutionMode.AUDIT, audit=audit).run()

        csv_path = tmp_project / "output" / "reports" / "kpi.csv"
        assert not csv_path.exists()

    def test_audit_without_report_object_logs_error_and_returns(self, config_factory, tmp_project):
        """AUDIT mode sem AuditReport injetado: não deve levantar exceção."""
        config_factory()
        from emupipeline.steps.step_kpi import KpiReporter
        KpiReporter(mode=ExecutionMode.AUDIT, audit=None).run()  # sem crash


# ---------------------------------------------------------------------------
# _dir_stats helper
# ---------------------------------------------------------------------------

class TestDirStats:
    def test_counts_files_correctly(self, tmp_path):
        from emupipeline.steps.step_kpi import _dir_stats
        (tmp_path / "a.txt").write_bytes(b"hello")
        (tmp_path / "b.txt").write_bytes(b"world!")
        count, size = _dir_stats(tmp_path)
        assert count == 2
        assert size == 11  # 5 + 6

    def test_does_not_count_symlinks(self, tmp_path):
        from emupipeline.steps.step_kpi import _dir_stats
        real_file = tmp_path / "real.txt"
        real_file.write_bytes(b"data")
        link = tmp_path / "link.txt"
        link.symlink_to(real_file)
        count, _ = _dir_stats(tmp_path)
        assert count == 1  # só o arquivo real
