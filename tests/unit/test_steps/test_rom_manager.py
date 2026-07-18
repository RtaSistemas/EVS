"""
Testes para RomManager.

Cobertura: igir não encontrado, igir desabilitado no config,
DRY_RUN, AUDIT (com/sem AuditReport), NORMAL com subprocess mockado
(sucesso, falha, timeout).
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from emupipeline.core.execution_mode import AuditReport, ExecutionMode

# ---------------------------------------------------------------------------
# Igir não encontrado no PATH
# ---------------------------------------------------------------------------

class TestIgirNotFound:
    def test_missing_igir_returns_early(self, config_factory, tmp_project):
        config_factory({"roms": {"enable_igir": True}})
        from emupipeline.steps.step_rom_manager import RomManager

        with patch("shutil.which", return_value=None):
            rm = RomManager()
            with patch("emupipeline.steps.step_rom_manager.subprocess.run") as mock_run:
                rm.run()
                mock_run.assert_not_called()

    def test_missing_igir_leaves_stats_empty(self, config_factory, tmp_project):
        config_factory({"roms": {"enable_igir": True}})
        from emupipeline.steps.step_rom_manager import RomManager

        with patch("shutil.which", return_value=None):
            rm = RomManager()
            rm.run()
            assert rm.get_stats() == {}


# ---------------------------------------------------------------------------
# Igir desabilitado no config
# ---------------------------------------------------------------------------

class TestIgirDisabled:
    def test_disabled_igir_skips_subprocess(self, config_factory, tmp_project):
        # conftest já coloca enable_igir=False por padrão
        config_factory()
        from emupipeline.steps.step_rom_manager import RomManager

        with patch("shutil.which", return_value="/usr/bin/igir"):
            rm = RomManager()
            with patch("emupipeline.steps.step_rom_manager.subprocess.run") as mock_run:
                rm.run()
                mock_run.assert_not_called()

    def test_disabled_igir_leaves_stats_empty(self, config_factory, tmp_project):
        config_factory()
        from emupipeline.steps.step_rom_manager import RomManager

        with patch("shutil.which", return_value="/usr/bin/igir"):
            rm = RomManager()
            rm.run()
            assert rm.get_stats() == {}


# ---------------------------------------------------------------------------
# Modo DRY_RUN
# ---------------------------------------------------------------------------

class TestDryRunMode:
    def test_dry_run_does_not_call_subprocess(self, config_factory, tmp_project):
        config_factory({"roms": {"enable_igir": True}})
        from emupipeline.steps.step_rom_manager import RomManager

        with patch("shutil.which", return_value="/usr/bin/igir"):
            rm = RomManager(mode=ExecutionMode.DRY_RUN)
            with patch("emupipeline.steps.step_rom_manager.subprocess.run") as mock_run:
                rm.run()
                mock_run.assert_not_called()

    def test_dry_run_leaves_stats_empty(self, config_factory, tmp_project):
        config_factory({"roms": {"enable_igir": True}})
        from emupipeline.steps.step_rom_manager import RomManager

        with patch("shutil.which", return_value="/usr/bin/igir"):
            rm = RomManager(mode=ExecutionMode.DRY_RUN)
            rm.run()
            assert rm.get_stats() == {}


# ---------------------------------------------------------------------------
# Modo AUDIT
# ---------------------------------------------------------------------------

class TestAuditMode:
    def test_audit_records_run_igir(self, config_factory, tmp_project):
        config_factory({"roms": {"enable_igir": True}})
        audit = AuditReport()

        with patch("shutil.which", return_value="/usr/bin/igir"):
            from emupipeline.steps.step_rom_manager import RomManager
            rm = RomManager(mode=ExecutionMode.AUDIT, audit=audit)
            with patch("emupipeline.steps.step_rom_manager.subprocess.run") as mock_run:
                rm.run()
                mock_run.assert_not_called()

        assert audit.total >= 1
        assert audit.entries()[0].action == "run_igir"

    def test_audit_does_not_call_subprocess(self, config_factory, tmp_project):
        config_factory({"roms": {"enable_igir": True}})
        audit = AuditReport()

        with patch("shutil.which", return_value="/usr/bin/igir"):
            from emupipeline.steps.step_rom_manager import RomManager
            rm = RomManager(mode=ExecutionMode.AUDIT, audit=audit)
            with patch("emupipeline.steps.step_rom_manager.subprocess.run") as mock_run:
                rm.run()
                mock_run.assert_not_called()

    def test_audit_without_report_object_returns_early(self, config_factory, tmp_project):
        config_factory({"roms": {"enable_igir": True}})

        with patch("shutil.which", return_value="/usr/bin/igir"):
            from emupipeline.steps.step_rom_manager import RomManager
            rm = RomManager(mode=ExecutionMode.AUDIT, audit=None)
            with patch("emupipeline.steps.step_rom_manager.subprocess.run") as mock_run:
                rm.run()  # não deve levantar exceção
                mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Modo NORMAL — subprocess mockado
# ---------------------------------------------------------------------------

class TestNormalMode:
    def _run_with_igir(self, config_factory, tmp_project, returncode: int):
        config_factory({"roms": {"enable_igir": True}})
        from emupipeline.steps.step_rom_manager import RomManager

        with patch("shutil.which", return_value="/usr/bin/igir"):
            rm = RomManager()
            mock_result = MagicMock()
            mock_result.returncode = returncode
            mock_result.stderr = ""
            with patch("emupipeline.steps.step_rom_manager.subprocess.run",
                       return_value=mock_result) as mock_run:
                rm.run()
                return rm, mock_run

    def test_success_calls_subprocess(self, config_factory, tmp_project):
        _, mock_run = self._run_with_igir(config_factory, tmp_project, returncode=0)
        assert mock_run.called

    def test_success_sets_success_stat(self, config_factory, tmp_project):
        rm, _ = self._run_with_igir(config_factory, tmp_project, returncode=0)
        assert rm.get_stats().get("success") == 1

    def test_failure_sets_error_stat(self, config_factory, tmp_project):
        rm, _ = self._run_with_igir(config_factory, tmp_project, returncode=1)
        assert rm.get_stats().get("error") == 1

    def test_subprocess_cmd_contains_igir(self, config_factory, tmp_project):
        config_factory({"roms": {"enable_igir": True}})
        from emupipeline.steps.step_rom_manager import RomManager

        with patch("shutil.which", return_value="/usr/bin/igir"):
            rm = RomManager()
            mock_result = MagicMock(returncode=0, stderr="")
            with patch("emupipeline.steps.step_rom_manager.subprocess.run",
                       return_value=mock_result) as mock_run:
                rm.run()

        cmd = mock_run.call_args[0][0]
        assert "igir" in cmd[0]

    def test_subprocess_cmd_contains_copy(self, config_factory, tmp_project):
        config_factory({"roms": {"enable_igir": True}})
        from emupipeline.steps.step_rom_manager import RomManager

        with patch("shutil.which", return_value="/usr/bin/igir"):
            rm = RomManager()
            mock_result = MagicMock(returncode=0, stderr="")
            with patch("emupipeline.steps.step_rom_manager.subprocess.run",
                       return_value=mock_result) as mock_run:
                rm.run()

        cmd = mock_run.call_args[0][0]
        assert "copy" in cmd

    def test_timeout_sets_timeout_stat(self, config_factory, tmp_project):
        config_factory({"roms": {"enable_igir": True}})
        from emupipeline.steps.step_rom_manager import RomManager

        with patch("shutil.which", return_value="/usr/bin/igir"):
            rm = RomManager()
            with patch("emupipeline.steps.step_rom_manager.subprocess.run",
                       side_effect=subprocess.TimeoutExpired("igir", 7200)):
                rm.run()

        assert rm.get_stats().get("timeout") == 1

    def test_file_not_found_in_subprocess_sets_error_stat(self, config_factory, tmp_project):
        """FileNotFoundError de subprocess (não do shutil.which) define stat error."""
        config_factory({"roms": {"enable_igir": True}})
        from emupipeline.steps.step_rom_manager import RomManager

        with patch("shutil.which", return_value="/usr/bin/igir"):
            rm = RomManager()
            with patch("emupipeline.steps.step_rom_manager.subprocess.run",
                       side_effect=FileNotFoundError("igir")):
                rm.run()

        assert rm.get_stats().get("error") == 1

    def test_uses_output_dats_dir_when_dat_files_exist(self, config_factory, tmp_project):
        """Quando output/dats/ tem .dat files, igir usa o glob *.dat em vez do dat_file mestre."""
        config_factory({"roms": {"enable_igir": True}})
        # Cria um arquivo .dat no diretório de saída
        (tmp_project / "output" / "dats" / "platform.dat").write_text("<dat/>")

        from emupipeline.steps.step_rom_manager import RomManager

        with patch("shutil.which", return_value="/usr/bin/igir"):
            rm = RomManager()
            mock_result = MagicMock(returncode=0, stderr="")
            with patch("emupipeline.steps.step_rom_manager.subprocess.run",
                       return_value=mock_result) as mock_run:
                rm.run()

        cmd = mock_run.call_args[0][0]
        dat_idx = cmd.index("--dat") + 1
        assert "*.dat" in cmd[dat_idx]
