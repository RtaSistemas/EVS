"""
Testes para RomCompressor.

Cobertura: sistema não reconhecido, binário ausente, arquivo já comprimido,
DRY_RUN, AUDIT (com/sem AuditReport), NORMAL (sucesso/falha/timeout),
delete_original, output_dir separado, helpers _build_cmd e _delete_originals.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from emupipeline.core.execution_mode import AuditReport, ExecutionMode

if TYPE_CHECKING:
    from pathlib import Path

# Binário real que existe mas não faz nada útil (para testes de shutil.which)
_REAL_BIN = "/usr/bin/true"


def _make_iso(path: Path) -> None:
    path.write_bytes(b"\x00" * 32)


# ---------------------------------------------------------------------------
# Sistema não reconhecido
# ---------------------------------------------------------------------------

class TestUnknownSystem:
    def test_unknown_system_dir_is_skipped(self, config_factory, tmp_project):
        config_factory()
        (tmp_project / "source" / "roms" / "snes").mkdir()
        (tmp_project / "source" / "roms" / "snes" / "game.sfc").write_bytes(b"ROM")

        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor()
        with patch("shutil.which", return_value=_REAL_BIN), patch(
            "emupipeline.core.processor.subprocess.run"
        ) as mock_run:
            rc.run()
            mock_run.assert_not_called()

    def test_unknown_system_leaves_stats_empty(self, config_factory, tmp_project):
        config_factory()
        (tmp_project / "source" / "roms" / "nes").mkdir()

        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor()
        with patch("shutil.which", return_value=_REAL_BIN):
            rc.run()
        assert rc.get_stats() == {}


# ---------------------------------------------------------------------------
# Binário ausente
# ---------------------------------------------------------------------------

class TestBinaryNotFound:
    def test_missing_chdman_skips_ps1(self, config_factory, tmp_project):
        config_factory()
        ps1_dir = tmp_project / "source" / "roms" / "ps1"
        ps1_dir.mkdir()
        _make_iso(ps1_dir / "game.iso")

        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor()

        def mock_which(name: str) -> str | None:
            return None if "chdman" in name else _REAL_BIN

        with patch("shutil.which", side_effect=mock_which), patch(
            "emupipeline.core.processor.subprocess.run"
        ) as mock_run:
            rc.run()
            mock_run.assert_not_called()

        assert rc.get_stats().get("skipped_no_bin", 0) >= 1

    def test_missing_dolphin_skips_wii(self, config_factory, tmp_project):
        config_factory()
        wii_dir = tmp_project / "source" / "roms" / "wii"
        wii_dir.mkdir()
        _make_iso(wii_dir / "game.iso")

        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor()

        with patch("shutil.which", return_value=None):
            rc.run()

        assert rc.get_stats().get("skipped_no_bin", 0) >= 1


# ---------------------------------------------------------------------------
# Arquivo já comprimido (destino existe)
# ---------------------------------------------------------------------------

class TestAlreadyCompressed:
    def test_existing_chd_is_skipped(self, config_factory, tmp_project):
        config_factory()
        ps1_dir = tmp_project / "source" / "roms" / "ps1"
        ps1_dir.mkdir()
        _make_iso(ps1_dir / "game.iso")
        (ps1_dir / "game.chd").write_bytes(b"CHD")   # já existe

        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor()

        with patch("shutil.which", return_value=_REAL_BIN), patch(
            "emupipeline.core.processor.subprocess.run"
        ) as mock_run:
            rc.run()
            mock_run.assert_not_called()

        assert rc.get_stats().get("skipped_exists", 0) >= 1


# ---------------------------------------------------------------------------
# Modo DRY_RUN
# ---------------------------------------------------------------------------

class TestDryRunMode:
    def test_dry_run_does_not_call_subprocess(self, config_factory, tmp_project):
        config_factory()
        ps1_dir = tmp_project / "source" / "roms" / "ps1"
        ps1_dir.mkdir()
        _make_iso(ps1_dir / "game.iso")

        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor(mode=ExecutionMode.DRY_RUN)

        with patch("shutil.which", return_value=_REAL_BIN), patch(
            "emupipeline.core.processor.subprocess.run"
        ) as mock_run:
            rc.run()
            mock_run.assert_not_called()

    def test_dry_run_increments_dry_run_stat(self, config_factory, tmp_project):
        config_factory()
        ps1_dir = tmp_project / "source" / "roms" / "ps1"
        ps1_dir.mkdir()
        _make_iso(ps1_dir / "game.iso")

        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor(mode=ExecutionMode.DRY_RUN)

        with patch("shutil.which", return_value=_REAL_BIN):
            rc.run()

        assert rc.get_stats().get("dry_run", 0) >= 1

    def test_dry_run_does_not_create_chd(self, config_factory, tmp_project):
        config_factory()
        ps1_dir = tmp_project / "source" / "roms" / "ps1"
        ps1_dir.mkdir()
        _make_iso(ps1_dir / "game.iso")

        from emupipeline.steps.step_compress import RomCompressor
        RomCompressor(mode=ExecutionMode.DRY_RUN).run()

        assert not (ps1_dir / "game.chd").exists()


# ---------------------------------------------------------------------------
# Modo AUDIT
# ---------------------------------------------------------------------------

class TestAuditMode:
    def test_audit_records_compress_action(self, config_factory, tmp_project):
        config_factory()
        ps1_dir = tmp_project / "source" / "roms" / "ps1"
        ps1_dir.mkdir()
        _make_iso(ps1_dir / "game.iso")

        audit = AuditReport()
        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor(mode=ExecutionMode.AUDIT, audit=audit)

        with patch("shutil.which", return_value=_REAL_BIN):
            rc.run()

        assert audit.total >= 1
        assert audit.entries()[0].action == "compress_chd"

    def test_audit_does_not_call_subprocess(self, config_factory, tmp_project):
        config_factory()
        ps1_dir = tmp_project / "source" / "roms" / "ps1"
        ps1_dir.mkdir()
        _make_iso(ps1_dir / "game.iso")

        audit = AuditReport()
        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor(mode=ExecutionMode.AUDIT, audit=audit)

        with patch("shutil.which", return_value=_REAL_BIN), patch(
            "emupipeline.core.processor.subprocess.run"
        ) as mock_run:
            rc.run()
            mock_run.assert_not_called()

    def test_audit_does_not_create_file(self, config_factory, tmp_project):
        config_factory()
        ps1_dir = tmp_project / "source" / "roms" / "ps1"
        ps1_dir.mkdir()
        _make_iso(ps1_dir / "game.iso")

        audit = AuditReport()
        from emupipeline.steps.step_compress import RomCompressor
        RomCompressor(mode=ExecutionMode.AUDIT, audit=audit).run()

        assert not (ps1_dir / "game.chd").exists()

    def test_audit_records_rvz_for_gamecube(self, config_factory, tmp_project):
        config_factory()
        gc_dir = tmp_project / "source" / "roms" / "gamecube"
        gc_dir.mkdir()
        _make_iso(gc_dir / "game.iso")

        audit = AuditReport()
        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor(mode=ExecutionMode.AUDIT, audit=audit)

        with patch("shutil.which", return_value=_REAL_BIN):
            rc.run()

        actions = [e.action for e in audit.entries()]
        assert "compress_rvz" in actions

    def test_audit_records_cso_for_psp(self, config_factory, tmp_project):
        config_factory()
        psp_dir = tmp_project / "source" / "roms" / "psp"
        psp_dir.mkdir()
        _make_iso(psp_dir / "game.iso")

        audit = AuditReport()
        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor(mode=ExecutionMode.AUDIT, audit=audit)

        with patch("shutil.which", return_value=_REAL_BIN):
            rc.run()

        actions = [e.action for e in audit.entries()]
        assert "compress_cso" in actions

    def test_audit_without_report_object_returns_early(self, config_factory, tmp_project):
        config_factory()
        ps1_dir = tmp_project / "source" / "roms" / "ps1"
        ps1_dir.mkdir()
        _make_iso(ps1_dir / "game.iso")

        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor(mode=ExecutionMode.AUDIT, audit=None)

        with patch("shutil.which", return_value=_REAL_BIN), patch(
            "emupipeline.core.processor.subprocess.run"
        ) as mock_run:
            rc.run()  # não deve levantar exceção
            mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# Modo NORMAL — subprocess mockado
# ---------------------------------------------------------------------------

class TestNormalMode:
    def _setup_ps1(self, config_factory, tmp_project) -> Path:
        config_factory()
        ps1_dir = tmp_project / "source" / "roms" / "ps1"
        ps1_dir.mkdir()
        _make_iso(ps1_dir / "game.iso")
        return ps1_dir

    def test_success_increments_compressed_stat(self, config_factory, tmp_project):
        self._setup_ps1(config_factory, tmp_project)
        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor()

        with patch("shutil.which", return_value=_REAL_BIN), patch(
            "emupipeline.core.processor.subprocess.run",
            return_value=MagicMock(returncode=0, stderr=""),
        ):
            rc.run()

        assert rc.get_stats().get("compressed", 0) >= 1

    def test_failure_increments_error_stat(self, config_factory, tmp_project):
        self._setup_ps1(config_factory, tmp_project)
        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor()

        with patch("shutil.which", return_value=_REAL_BIN), patch(
            "emupipeline.core.processor.subprocess.run",
            return_value=MagicMock(returncode=1, stderr="error detail"),
        ):
            rc.run()

        assert rc.get_stats().get("error", 0) >= 1

    def test_timeout_increments_error_stat(self, config_factory, tmp_project):
        self._setup_ps1(config_factory, tmp_project)
        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor()

        with patch("shutil.which", return_value=_REAL_BIN), patch(
            "emupipeline.core.processor.subprocess.run",
            side_effect=subprocess.TimeoutExpired("chdman", 3600),
        ):
            rc.run()

        assert rc.get_stats().get("error", 0) >= 1

    def test_subprocess_cmd_contains_createcd_for_chd(self, config_factory, tmp_project):
        self._setup_ps1(config_factory, tmp_project)
        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor()

        with patch("shutil.which", return_value=_REAL_BIN), patch(
            "emupipeline.core.processor.subprocess.run",
            return_value=MagicMock(returncode=0, stderr=""),
        ) as mock_run:
            rc.run()

        cmd = mock_run.call_args[0][0]
        assert "createcd" in cmd
        assert "-o" in cmd

    def test_subprocess_cmd_contains_convert_for_rvz(self, config_factory, tmp_project):
        config_factory()
        gc_dir = tmp_project / "source" / "roms" / "gamecube"
        gc_dir.mkdir()
        _make_iso(gc_dir / "game.iso")

        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor()

        with patch("shutil.which", return_value=_REAL_BIN), patch(
            "emupipeline.core.processor.subprocess.run",
            return_value=MagicMock(returncode=0, stderr=""),
        ) as mock_run:
            rc.run()

        cmd = mock_run.call_args[0][0]
        assert "convert" in cmd
        assert "rvz" in cmd

    def test_nonexistent_roms_dir_returns_early(self, config_factory, tmp_project):
        import shutil as _shutil
        config_factory()
        _shutil.rmtree(tmp_project / "source" / "roms")

        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor()
        rc.run()  # não deve levantar exceção
        assert rc.get_stats() == {}

    def test_bin_skipped_when_cue_exists(self, config_factory, tmp_project):
        """BIN com CUE acompanhante não deve gerar CHD separado — o CUE fará isso."""
        config_factory()
        ps1_dir = tmp_project / "source" / "roms" / "ps1"
        ps1_dir.mkdir()
        (ps1_dir / "game.bin").write_bytes(b"\x00" * 32)
        (ps1_dir / "game.cue").write_text('FILE "game.bin" BINARY\n')

        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor()

        call_count = 0

        def mock_run(cmd, **kw):
            nonlocal call_count
            call_count += 1
            # Verifica que o input é o CUE, não o BIN
            assert ".cue" in cmd[cmd.index("-i") + 1]
            return MagicMock(returncode=0, stderr="")

        with patch("shutil.which", return_value=_REAL_BIN), patch(
            "emupipeline.core.processor.subprocess.run", side_effect=mock_run
        ):
            rc.run()

        assert call_count == 1  # apenas UMA compressão (do CUE), não do BIN


# ---------------------------------------------------------------------------
# delete_original
# ---------------------------------------------------------------------------

class TestDeleteOriginal:
    def test_delete_original_removes_iso_on_success(self, config_factory, tmp_project):
        config_factory({"compress": {"delete_original": True}})
        ps1_dir = tmp_project / "source" / "roms" / "ps1"
        ps1_dir.mkdir()
        iso = ps1_dir / "game.iso"
        _make_iso(iso)

        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor()

        with patch("shutil.which", return_value=_REAL_BIN), patch(
            "emupipeline.core.processor.subprocess.run",
            return_value=MagicMock(returncode=0, stderr=""),
        ):
            rc.run()

        assert not iso.exists()

    def test_delete_original_false_keeps_iso(self, config_factory, tmp_project):
        config_factory({"compress": {"delete_original": False}})
        ps1_dir = tmp_project / "source" / "roms" / "ps1"
        ps1_dir.mkdir()
        iso = ps1_dir / "game.iso"
        _make_iso(iso)

        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor()

        with patch("shutil.which", return_value=_REAL_BIN), patch(
            "emupipeline.core.processor.subprocess.run",
            return_value=MagicMock(returncode=0, stderr=""),
        ):
            rc.run()

        assert iso.exists()

    def test_delete_original_not_called_on_failure(self, config_factory, tmp_project):
        config_factory({"compress": {"delete_original": True}})
        ps1_dir = tmp_project / "source" / "roms" / "ps1"
        ps1_dir.mkdir()
        iso = ps1_dir / "game.iso"
        _make_iso(iso)

        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor()

        with patch("shutil.which", return_value=_REAL_BIN), patch(
            "emupipeline.core.processor.subprocess.run",
            return_value=MagicMock(returncode=1, stderr="fail"),
        ):
            rc.run()

        assert iso.exists()  # original preservado após falha


# ---------------------------------------------------------------------------
# output_dir separado
# ---------------------------------------------------------------------------

class TestSeparateOutputDir:
    def test_output_dir_creates_chd_in_separate_location(self, config_factory, tmp_project):
        out_dir = tmp_project / "compressed"
        config_factory({"compress": {"output_dir": str(out_dir)}})
        ps1_dir = tmp_project / "source" / "roms" / "ps1"
        ps1_dir.mkdir()
        _make_iso(ps1_dir / "game.iso")

        from emupipeline.steps.step_compress import RomCompressor
        rc = RomCompressor()

        with patch("shutil.which", return_value=_REAL_BIN), patch(
            "emupipeline.core.processor.subprocess.run",
            return_value=MagicMock(returncode=0, stderr=""),
        ) as mock_run:
            rc.run()

        cmd = mock_run.call_args[0][0]
        dest_arg = cmd[cmd.index("-o") + 1]
        # Destino deve estar no output_dir separado, não dentro de ps1/
        assert str(out_dir) in dest_arg


# ---------------------------------------------------------------------------
# _build_cmd
# ---------------------------------------------------------------------------

class TestBuildCmd:
    def _rc(self, config_factory):
        config_factory()
        from emupipeline.steps.step_compress import RomCompressor
        return RomCompressor()

    def test_chd_cmd_uses_createcd(self, config_factory, tmp_path):
        rc = self._rc(config_factory)
        src = tmp_path / "game.iso"
        dest = tmp_path / "game.chd"
        cmd = rc._build_cmd("chd", src, dest, "chdman", "zstd", 5, "cso")
        assert cmd is not None
        assert "createcd" in cmd
        assert str(src) in cmd
        assert str(dest) in cmd

    def test_rvz_cmd_uses_convert(self, config_factory, tmp_path):
        rc = self._rc(config_factory)
        src = tmp_path / "game.iso"
        dest = tmp_path / "game.rvz"
        cmd = rc._build_cmd("rvz", src, dest, "DolphinTool", "zstd", 5, "cso")
        assert cmd is not None
        assert "convert" in cmd
        assert "rvz" in cmd
        assert "zstd" in cmd
        assert "5" in cmd

    def test_cso_cmd_default(self, config_factory, tmp_path):
        rc = self._rc(config_factory)
        src = tmp_path / "game.iso"
        dest = tmp_path / "game.cso"
        cmd = rc._build_cmd("cso", src, dest, "maxcso", "zstd", 5, "cso")
        assert cmd is not None
        assert str(src) in cmd
        assert str(dest) in cmd

    def test_zso_cmd_uses_zst_flag(self, config_factory, tmp_path):
        rc = self._rc(config_factory)
        src = tmp_path / "game.iso"
        dest = tmp_path / "game.zso"
        cmd = rc._build_cmd("cso", src, dest, "maxcso", "zstd", 5, "zso")
        assert cmd is not None
        assert "--zst" in cmd

    def test_unknown_format_returns_none(self, config_factory, tmp_path):
        rc = self._rc(config_factory)
        src = tmp_path / "game.iso"
        dest = tmp_path / "game.xyz"
        cmd = rc._build_cmd("xyz", src, dest, "tool", "zstd", 5, "cso")
        assert cmd is None

    def test_bin_with_cue_uses_cue_as_input(self, config_factory, tmp_path):
        rc = self._rc(config_factory)
        bin_file = tmp_path / "game.bin"
        bin_file.write_bytes(b"\x00")
        cue_file = tmp_path / "game.cue"
        cue_file.write_text('FILE "game.bin" BINARY\n')
        dest = tmp_path / "game.chd"
        cmd = rc._build_cmd("chd", bin_file, dest, "chdman", "zstd", 5, "cso")
        assert cmd is not None
        assert str(cue_file) in cmd


# ---------------------------------------------------------------------------
# _delete_originals
# ---------------------------------------------------------------------------

class TestDeleteOriginals:
    def _rc(self, config_factory):
        config_factory()
        from emupipeline.steps.step_compress import RomCompressor
        return RomCompressor()

    def test_deletes_single_iso(self, config_factory, tmp_path):
        rc = self._rc(config_factory)
        iso = tmp_path / "game.iso"
        _make_iso(iso)
        rc._delete_originals(iso)
        assert not iso.exists()

    def test_cue_deletes_bin_companions(self, config_factory, tmp_path):
        rc = self._rc(config_factory)
        bin_file = tmp_path / "game.bin"
        bin_file.write_bytes(b"\x00" * 32)
        cue_file = tmp_path / "game.cue"
        cue_file.write_text('FILE "game.bin" BINARY\n  TRACK 01 MODE2/2352\n')
        rc._delete_originals(cue_file)
        assert not cue_file.exists()
        assert not bin_file.exists()

    def test_missing_companion_does_not_raise(self, config_factory, tmp_path):
        rc = self._rc(config_factory)
        cue_file = tmp_path / "game.cue"
        cue_file.write_text('FILE "missing.bin" BINARY\n')
        rc._delete_originals(cue_file)  # não deve levantar exceção
