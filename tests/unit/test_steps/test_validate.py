"""
Testes para RomValidator.

Cobertura: ExecutionMode (NORMAL/DRY_RUN/AUDIT), DAT ausente,
diretório inexistente, geração de relatório, sem reports_dir.
"""

from __future__ import annotations

import pytest

from emupipeline.core.execution_mode import AuditReport, ExecutionMode


@pytest.fixture
def dat(sample_dat):
    from emupipeline.core.dat_manager import DatMaster
    return DatMaster(sample_dat)


@pytest.fixture
def validator(dat, config_factory):
    config_factory()
    from emupipeline.steps.step_validate import RomValidator
    return RomValidator(dat)


# ---------------------------------------------------------------------------
# Guards de entrada
# ---------------------------------------------------------------------------

class TestInputGuards:
    def test_no_dat_returns_early(self, config_factory, tmp_project):
        config_factory()
        from emupipeline.steps.step_validate import RomValidator
        v = RomValidator(dat=None)
        v.run()  # não deve levantar exceção
        assert v.get_stats() == {}

    def test_nonexistent_roms_dir_returns_early(self, dat, config_factory, tmp_project):
        import shutil
        config_factory()
        shutil.rmtree(tmp_project / "source" / "roms")
        from emupipeline.steps.step_validate import RomValidator
        v = RomValidator(dat=dat)
        v.run()
        assert v.get_stats() == {}


# ---------------------------------------------------------------------------
# Modo NORMAL
# ---------------------------------------------------------------------------

class TestNormalMode:
    def test_generates_validation_report(self, validator, tmp_project):
        validator.run()
        report = tmp_project / "output" / "reports" / "validation_report.txt"
        assert report.exists()

    def test_report_contains_sections(self, validator, tmp_project):
        validator.run()
        text = (tmp_project / "output" / "reports" / "validation_report.txt").read_text()
        assert "FALTANTES" in text
        assert "EXTRAS" in text

    def test_stats_populated(self, validator):
        validator.run()
        stats = validator.get_stats()
        assert "dat_total" in stats
        assert "found" in stats
        assert "missing" in stats
        assert "extras" in stats

    def test_local_rom_counted_as_found(self, dat, config_factory, tmp_project):
        config_factory()
        (tmp_project / "source" / "roms" / "sf2.zip").write_bytes(b"ROM")
        from emupipeline.steps.step_validate import RomValidator
        v = RomValidator(dat=dat)
        v.run()
        assert v.get_stats()["found"] >= 1

    def test_no_reports_dir_skips_file(self, dat, config_factory, tmp_project):
        """Sem paths.output_reports, o relatório não é gerado (sem crash)."""
        config_factory({"paths": {"output_reports": ""}})
        from emupipeline.steps.step_validate import RomValidator
        v = RomValidator(dat=dat)
        v.run()  # não deve levantar exceção


# ---------------------------------------------------------------------------
# Modo DRY_RUN
# ---------------------------------------------------------------------------

class TestDryRunMode:
    def test_dry_run_does_not_write_report(self, dat, config_factory, tmp_project):
        config_factory()
        from emupipeline.steps.step_validate import RomValidator
        v = RomValidator(dat=dat, mode=ExecutionMode.DRY_RUN)
        v.run()
        report = tmp_project / "output" / "reports" / "validation_report.txt"
        assert not report.exists()

    def test_dry_run_still_populates_stats(self, dat, config_factory):
        config_factory()
        from emupipeline.steps.step_validate import RomValidator
        v = RomValidator(dat=dat, mode=ExecutionMode.DRY_RUN)
        v.run()
        assert v.get_stats().get("dat_total", 0) >= 1


# ---------------------------------------------------------------------------
# Modo AUDIT
# ---------------------------------------------------------------------------

class TestAuditMode:
    def test_audit_records_operation(self, dat, config_factory, tmp_project):
        config_factory()
        audit = AuditReport()
        from emupipeline.steps.step_validate import RomValidator
        v = RomValidator(dat=dat, mode=ExecutionMode.AUDIT, audit=audit)
        v.run()
        assert audit.total >= 1
        assert audit.entries()[0].action == "write_validation_report"

    def test_audit_does_not_write_report(self, dat, config_factory, tmp_project):
        config_factory()
        audit = AuditReport()
        from emupipeline.steps.step_validate import RomValidator
        v = RomValidator(dat=dat, mode=ExecutionMode.AUDIT, audit=audit)
        v.run()
        report = tmp_project / "output" / "reports" / "validation_report.txt"
        assert not report.exists()

    def test_audit_without_report_object_returns_early(self, dat, config_factory):
        config_factory()
        from emupipeline.steps.step_validate import RomValidator
        v = RomValidator(dat=dat, mode=ExecutionMode.AUDIT, audit=None)
        v.run()  # não deve levantar exceção
        assert v.get_stats().get("dat_total", 0) >= 1

    def test_dat_passed_via_run(self, dat, config_factory):
        """DAT pode ser passado via run(dat=...) em vez do construtor."""
        config_factory()
        audit = AuditReport()
        from emupipeline.steps.step_validate import RomValidator
        v = RomValidator(mode=ExecutionMode.AUDIT, audit=audit)
        v.run(dat=dat)
        assert audit.total >= 1
