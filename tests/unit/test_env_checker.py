"""
Testes para EnvironmentChecker.

Cobertura alvo: 85%
Foco em:
  - detecção de ferramenta presente vs ausente
  - comparação de versão (ge, lt)
  - relatório legível
  - fail_fast aborta com SystemExit
  - ferramentas opcionais não bloqueiam fail_fast
  - verificação de binários por path
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from emupipeline.core.env_checker import DepStatus, EnvironmentChecker


@pytest.fixture
def checker(config_factory):
    config_factory()
    from emupipeline.core.config import cfg
    return EnvironmentChecker(cfg)


# ---------------------------------------------------------------------------
# Comparação de versão
# ---------------------------------------------------------------------------

class TestVersionComparison:
    def test_equal_versions_pass(self, checker):
        assert checker._version_ge("4.0", "4.0") is True

    def test_higher_version_passes(self, checker):
        assert checker._version_ge("5.1", "4.0") is True

    def test_lower_version_fails(self, checker):
        assert checker._version_ge("3.9", "4.0") is False

    def test_patch_version_matters(self, checker):
        assert checker._version_ge("4.0.1", "4.0.2") is False
        assert checker._version_ge("4.0.3", "4.0.2") is True

    def test_malformed_version_passes(self, checker):
        """Versão que não pode ser parseada assume OK (não bloqueia)."""
        assert checker._version_ge("unknown", "4.0") is True


# ---------------------------------------------------------------------------
# Detecção de ferramentas
# ---------------------------------------------------------------------------

class TestToolDetection:
    @patch("emupipeline.core.env_checker.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("emupipeline.core.env_checker.subprocess.run")
    def test_found_tool_marks_found(self, mock_run, mock_which, checker):
        mock_run.return_value = MagicMock(
            stdout="ffmpeg version 6.1 ...", stderr="", returncode=0
        )
        status = checker._check_tool({
            "name": "ffmpeg",
            "required": True,
            "min_version": "4.0",
            "version_cmd": ["ffmpeg", "-version"],
            "version_pattern": r"ffmpeg version (\d+\.\d+)",
            "hint": "install it",
        })
        assert status.found is True
        assert status.version == "6.1"
        assert status.version_ok is True

    @patch("emupipeline.core.env_checker.shutil.which", return_value=None)
    def test_missing_tool_marks_not_found(self, mock_which, checker):
        status = checker._check_tool({
            "name": "ffmpeg",
            "required": True,
            "min_version": "4.0",
            "version_cmd": ["ffmpeg", "-version"],
            "version_pattern": r"ffmpeg version (\d+\.\d+)",
            "hint": "sudo apt install ffmpeg",
        })
        assert status.found is False
        assert status.version is None

    @patch("emupipeline.core.env_checker.shutil.which", return_value="/usr/bin/ffmpeg")
    @patch("emupipeline.core.env_checker.subprocess.run")
    def test_old_version_marks_version_not_ok(self, mock_run, mock_which, checker):
        mock_run.return_value = MagicMock(
            stdout="ffmpeg version 3.4 ...", stderr="", returncode=0
        )
        status = checker._check_tool({
            "name": "ffmpeg",
            "required": True,
            "min_version": "4.0",
            "version_cmd": ["ffmpeg", "-version"],
            "version_pattern": r"ffmpeg version (\d+\.\d+)",
            "hint": "update it",
        })
        assert status.version_ok is False


# ---------------------------------------------------------------------------
# Path binário (waifu2x, realesrgan)
# ---------------------------------------------------------------------------

class TestPathBinary:
    def test_existing_binary_is_found(self, checker, tmp_path):
        binary = tmp_path / "waifu2x"
        binary.write_bytes(b"ELF")
        checker._check_path_binary("waifu2x", binary)
        result = checker._results[-1]
        assert result.found is True

    def test_missing_binary_is_not_found(self, checker, tmp_path):
        binary = tmp_path / "missing_binary"
        checker._check_path_binary("waifu2x", binary)
        result = checker._results[-1]
        assert result.found is False

    def test_none_path_is_skipped(self, checker):
        count_before = len(checker._results)
        checker._check_path_binary("waifu2x", None)
        assert len(checker._results) == count_before  # nada adicionado


# ---------------------------------------------------------------------------
# has_critical_failures
# ---------------------------------------------------------------------------

class TestCriticalFailures:
    def test_required_missing_is_critical(self, checker):
        checker._results = [
            DepStatus(name="ffmpeg", required=True, found=False, hint="install")
        ]
        assert checker.has_critical_failures() is True

    def test_optional_missing_is_not_critical(self, checker):
        checker._results = [
            DepStatus(name="waifu2x", required=False, found=False, hint="optional")
        ]
        assert checker.has_critical_failures() is False

    def test_required_found_but_old_version_is_critical(self, checker):
        checker._results = [
            DepStatus(
                name="ffmpeg", required=True, found=True,
                version="3.4", min_version="4.0", version_ok=False, hint=""
            )
        ]
        assert checker.has_critical_failures() is True

    def test_all_ok_is_not_critical(self, checker):
        checker._results = [
            DepStatus(name="ffmpeg", required=True, found=True, version_ok=True),
            DepStatus(name="ffprobe", required=True, found=True, version_ok=True),
        ]
        assert checker.has_critical_failures() is False


# ---------------------------------------------------------------------------
# Report legível
# ---------------------------------------------------------------------------

class TestReport:
    def test_report_contains_tool_names(self, checker):
        checker._results = [
            DepStatus(name="ffmpeg", required=True, found=True, version="6.1"),
            DepStatus(name="igir", required=False, found=False, hint="npm install -g igir"),
        ]
        report = checker.report()
        assert "ffmpeg" in report
        assert "igir" in report

    def test_report_marks_missing_with_icon(self, checker):
        checker._results = [
            DepStatus(name="ffmpeg", required=True, found=False, hint="install it")
        ]
        report = checker.report()
        assert "❌" in report
        assert "NÃO ENCONTRADO" in report

    def test_report_marks_found_with_check(self, checker):
        checker._results = [
            DepStatus(name="ffmpeg", required=True, found=True, version="6.1")
        ]
        report = checker.report()
        assert "✅" in report


# ---------------------------------------------------------------------------
# fail_fast
# ---------------------------------------------------------------------------

class TestFailFast:
    def test_fail_fast_raises_on_critical(self, checker):
        with patch.object(checker, "check_all"):
            checker._results = [
                DepStatus(name="ffmpeg", required=True, found=False, hint="install")
            ]
            with pytest.raises(SystemExit):
                checker.fail_fast()

    def test_fail_fast_passes_when_all_ok(self, checker):
        with patch.object(checker, "check_all"):
            checker._results = [
                DepStatus(name="ffmpeg", required=True, found=True, version_ok=True)
            ]
            # Não deve levantar exceção
            checker.fail_fast()
