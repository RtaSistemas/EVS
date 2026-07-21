"""
Testes para OriginalCleaner.

Cobertura: DRY_RUN, AUDIT (com/sem AuditReport), NORMAL (candidatos com/sem
WebP válido, confirmação cancelada, stdin não-tty, OSError no unlink),
process_file() individual, _find_candidates().
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from emupipeline.core.execution_mode import AuditReport, ExecutionMode


def _make_png(path: Path, size: int = 40) -> None:
    path.write_bytes(b"PNG" * size)


def _make_webp(path: Path, size: int = 40) -> None:
    """WebP válido = mais de 50 bytes."""
    path.write_bytes(b"WEBP" * size)


# ---------------------------------------------------------------------------
# Modo DRY_RUN
# ---------------------------------------------------------------------------

class TestDryRunMode:
    def test_dry_run_does_not_delete(self, config_factory, tmp_project):
        config_factory()
        out = tmp_project / "output" / "images"
        out.mkdir(parents=True, exist_ok=True)
        png = out / "sf2.png"
        _make_png(png)
        _make_webp(out / "sf2.webp")

        from emupipeline.steps.step_clean import OriginalCleaner
        OriginalCleaner(mode=ExecutionMode.DRY_RUN).run()
        assert png.exists()

    def test_dry_run_leaves_stats_empty(self, config_factory, tmp_project):
        config_factory()
        out = tmp_project / "output" / "images"
        out.mkdir(parents=True, exist_ok=True)
        _make_png(out / "sf2.png")
        _make_webp(out / "sf2.webp")

        from emupipeline.steps.step_clean import OriginalCleaner
        cleaner = OriginalCleaner(mode=ExecutionMode.DRY_RUN)
        cleaner.run()
        assert "deleted" not in cleaner.get_stats()

    def test_dry_run_with_no_candidates_returns_early(self, config_factory, tmp_project):
        config_factory()
        out = tmp_project / "output" / "images"
        out.mkdir(parents=True, exist_ok=True)
        _make_png(out / "sf2.png")  # sem WebP correspondente

        from emupipeline.steps.step_clean import OriginalCleaner
        OriginalCleaner(mode=ExecutionMode.DRY_RUN).run()  # não deve levantar exceção


# ---------------------------------------------------------------------------
# Modo AUDIT
# ---------------------------------------------------------------------------

class TestAuditMode:
    def test_audit_records_delete_action(self, config_factory, tmp_project):
        config_factory()
        out = tmp_project / "output" / "images"
        out.mkdir(parents=True, exist_ok=True)
        _make_png(out / "sf2.png")
        _make_webp(out / "sf2.webp")

        audit = AuditReport()
        from emupipeline.steps.step_clean import OriginalCleaner
        OriginalCleaner(mode=ExecutionMode.AUDIT, audit=audit).run()

        assert audit.total >= 1
        assert audit.entries()[0].action == "delete_original"

    def test_audit_does_not_delete_file(self, config_factory, tmp_project):
        config_factory()
        out = tmp_project / "output" / "images"
        out.mkdir(parents=True, exist_ok=True)
        png = out / "kof97.png"
        _make_png(png)
        _make_webp(out / "kof97.webp")

        audit = AuditReport()
        from emupipeline.steps.step_clean import OriginalCleaner
        OriginalCleaner(mode=ExecutionMode.AUDIT, audit=audit).run()
        assert png.exists()

    def test_audit_without_report_object_returns_early(self, config_factory, tmp_project):
        config_factory()
        out = tmp_project / "output" / "images"
        out.mkdir(parents=True, exist_ok=True)
        _make_png(out / "sf2.png")
        _make_webp(out / "sf2.webp")

        from emupipeline.steps.step_clean import OriginalCleaner
        OriginalCleaner(mode=ExecutionMode.AUDIT, audit=None).run()  # não deve levantar


# ---------------------------------------------------------------------------
# Modo NORMAL
# ---------------------------------------------------------------------------

class TestNormalMode:
    def _setup(self, tmp_project):
        out = tmp_project / "output" / "images"
        out.mkdir(parents=True, exist_ok=True)
        return out

    def test_deletes_png_when_valid_webp_exists(self, config_factory, tmp_project):
        config_factory()
        out = self._setup(tmp_project)
        png = out / "sf2.png"
        _make_png(png)
        _make_webp(out / "sf2.webp")

        from emupipeline.steps.step_clean import OriginalCleaner
        with patch("builtins.input", return_value="DELETAR"), \
             patch("sys.stdin.isatty", return_value=True):
            OriginalCleaner().run()

        assert not png.exists()

    def test_preserves_png_without_webp(self, config_factory, tmp_project):
        config_factory()
        out = self._setup(tmp_project)
        png = out / "game.png"
        _make_png(png)  # sem .webp correspondente

        from emupipeline.steps.step_clean import OriginalCleaner
        with patch("builtins.input", return_value="DELETAR"), \
             patch("sys.stdin.isatty", return_value=True):
            OriginalCleaner().run()

        assert png.exists()

    def test_preserves_png_when_webp_too_small(self, config_factory, tmp_project):
        """WebP com menos de 50 bytes não é considerado válido."""
        config_factory()
        out = self._setup(tmp_project)
        png = out / "small.png"
        _make_png(png)
        (out / "small.webp").write_bytes(b"tiny")  # < 50 bytes

        from emupipeline.steps.step_clean import OriginalCleaner
        with patch("builtins.input", return_value="DELETAR"), \
             patch("sys.stdin.isatty", return_value=True):
            OriginalCleaner().run()

        assert png.exists()

    def test_cancel_confirmation_preserves_files(self, config_factory, tmp_project):
        config_factory()
        out = self._setup(tmp_project)
        png = out / "sf2.png"
        _make_png(png)
        _make_webp(out / "sf2.webp")

        from emupipeline.steps.step_clean import OriginalCleaner
        with patch("builtins.input", return_value="nao"), \
             patch("sys.stdin.isatty", return_value=True):
            OriginalCleaner().run()

        assert png.exists()

    def test_non_tty_stdin_aborts(self, config_factory, tmp_project):
        config_factory()
        out = self._setup(tmp_project)
        png = out / "sf2.png"
        _make_png(png)
        _make_webp(out / "sf2.webp")

        from emupipeline.steps.step_clean import OriginalCleaner
        with patch("sys.stdin.isatty", return_value=False):
            OriginalCleaner().run()

        assert png.exists()

    def test_deleted_stat_incremented(self, config_factory, tmp_project):
        config_factory()
        out = self._setup(tmp_project)
        _make_png(out / "sf2.png")
        _make_webp(out / "sf2.webp")
        _make_png(out / "kof97.jpg")
        _make_webp(out / "kof97.webp")

        from emupipeline.steps.step_clean import OriginalCleaner
        cleaner = OriginalCleaner()
        with patch("builtins.input", return_value="DELETAR"), \
             patch("sys.stdin.isatty", return_value=True):
            cleaner.run()

        assert cleaner.get_stats().get("deleted", 0) == 2

    def test_oserror_on_unlink_increments_error_stat(self, config_factory, tmp_project):
        config_factory()
        out = self._setup(tmp_project)
        _make_png(out / "sf2.png")
        _make_webp(out / "sf2.webp")

        from emupipeline.steps.step_clean import OriginalCleaner
        cleaner = OriginalCleaner()

        with patch("builtins.input", return_value="DELETAR"), \
             patch("sys.stdin.isatty", return_value=True), \
             patch.object(Path, "unlink", side_effect=OSError("permissão negada")):
            cleaner.run()

        assert cleaner.get_stats().get("error", 0) >= 1

    def test_no_candidates_returns_early_without_prompt(self, config_factory, tmp_project):
        config_factory()
        out = self._setup(tmp_project)
        _make_png(out / "lonely.png")  # sem webp

        from emupipeline.steps.step_clean import OriginalCleaner
        with patch("builtins.input", side_effect=AssertionError("input chamado inesperadamente")):
            OriginalCleaner().run()  # input NÃO deve ser chamado


# ---------------------------------------------------------------------------
# process_file() individual
# ---------------------------------------------------------------------------

class TestProcessFile:
    def _setup(self, tmp_project):
        out = tmp_project / "output" / "images"
        out.mkdir(parents=True, exist_ok=True)
        return out

    def test_skipped_ext_for_non_image(self, config_factory, tmp_project):
        config_factory()
        out = self._setup(tmp_project)
        txt = out / "readme.txt"
        txt.write_text("text")

        from emupipeline.steps.step_clean import OriginalCleaner
        result = OriginalCleaner().process_file(txt)
        assert result == "skipped_ext"

    def test_no_webp_returns_no_webp(self, config_factory, tmp_project):
        config_factory()
        out = self._setup(tmp_project)
        png = out / "sf2.png"
        _make_png(png)

        from emupipeline.steps.step_clean import OriginalCleaner
        result = OriginalCleaner().process_file(png)
        assert result == "no_webp"

    def test_dry_run_returns_dry_run(self, config_factory, tmp_project):
        config_factory()
        out = self._setup(tmp_project)
        png = out / "sf2.png"
        _make_png(png)
        _make_webp(out / "sf2.webp")

        from emupipeline.steps.step_clean import OriginalCleaner
        result = OriginalCleaner(mode=ExecutionMode.DRY_RUN).process_file(png)
        assert result == "dry_run"

    def test_normal_deletes_and_returns_deleted(self, config_factory, tmp_project):
        config_factory()
        out = self._setup(tmp_project)
        png = out / "sf2.png"
        _make_png(png)
        _make_webp(out / "sf2.webp")

        from emupipeline.steps.step_clean import OriginalCleaner
        result = OriginalCleaner().process_file(png)
        assert result == "deleted"
        assert not png.exists()

    def test_audit_returns_audit_recorded(self, config_factory, tmp_project):
        config_factory()
        out = self._setup(tmp_project)
        png = out / "sf2.png"
        _make_png(png)
        _make_webp(out / "sf2.webp")

        from emupipeline.steps.step_clean import OriginalCleaner
        audit = AuditReport()
        result = OriginalCleaner(mode=ExecutionMode.AUDIT, audit=audit).process_file(png)
        assert result == "audit_recorded"
