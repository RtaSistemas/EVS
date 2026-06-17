"""
Testes para step_ports (PortsAutomator).

Foco em:
  - Diretório de ports não encontrado → retorna early
  - Dry-run → nenhum arquivo criado, stats["dry_run"] incrementado
  - Audit mode → AuditReport registrado, nenhum arquivo criado
  - Port Linux: autorun.sh e .desktop criados corretamente
  - Port Windows (Wine): autorun.sh com WINEPREFIX
  - Sem executável → warning e skipped_no_exec
  - gamemode e mangohud inseridos no autorun.sh Linux
  - Erro de I/O → logado, stats["error"] incrementado, continua para próximo port
  - name = "PortsAutomator" acessível como atributo de classe e instância
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from emupipeline.core.execution_mode import AuditReport, ExecutionMode


@pytest.fixture
def ports_dir(tmp_project: Path) -> Path:
    d = tmp_project / "ports"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def automator(config_factory, ports_dir):
    config_factory({
        "ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          "%(base_dir)s/output/ports_launchers",
            "windows_runner":      "wine",
            "enable_gamemode":     False,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }
    })
    from emupipeline.steps.step_ports import PortsAutomator
    return PortsAutomator()


def _make_linux_port(ports_dir: Path, name: str = "MyGame") -> Path:
    port_dir = ports_dir / name
    port_dir.mkdir()
    exe = port_dir / "mygame"
    exe.write_bytes(b"#!/bin/bash\necho hi")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return port_dir


def _make_windows_port(ports_dir: Path, name: str = "WinGame") -> Path:
    port_dir = ports_dir / name
    port_dir.mkdir()
    exe = port_dir / "game.exe"
    exe.write_bytes(b"MZ")
    return port_dir


# ---------------------------------------------------------------------------
# Atributo name
# ---------------------------------------------------------------------------

class TestName:
    def test_class_attribute_name(self):
        from emupipeline.steps.step_ports import PortsAutomator
        assert PortsAutomator.name == "PortsAutomator"

    def test_instance_attribute_name(self, config_factory):
        config_factory()
        from emupipeline.steps.step_ports import PortsAutomator
        inst = PortsAutomator()
        assert inst.name == "PortsAutomator"


# ---------------------------------------------------------------------------
# Diretório não encontrado
# ---------------------------------------------------------------------------

class TestSourceDirMissing:
    def test_missing_src_dir_returns_early(self, config_factory, tmp_project):
        config_factory({"ports": {
            "source_dir":          str(tmp_project / "nonexistent_ports"),
            "output_dir":          str(tmp_project / "output" / "ports_launchers"),
            "windows_runner":      "wine",
            "enable_gamemode":     False,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator
        automator = PortsAutomator()
        automator.run()
        assert automator.get_stats() == {}


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_creates_no_files(self, config_factory, ports_dir, tmp_project):
        config_factory({"ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          str(tmp_project / "output" / "ports_launchers"),
            "windows_runner":      "wine",
            "enable_gamemode":     False,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator

        _make_linux_port(ports_dir)
        automator = PortsAutomator(mode=ExecutionMode.DRY_RUN)
        automator.run()

        out_dir = tmp_project / "output" / "ports_launchers"
        # Em dry_run, o diretório de saída não deve ser criado
        assert not out_dir.exists()

    def test_dry_run_increments_stat(self, config_factory, ports_dir, tmp_project):
        config_factory({"ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          str(tmp_project / "output" / "ports_launchers"),
            "windows_runner":      "wine",
            "enable_gamemode":     False,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator

        _make_linux_port(ports_dir, "GameA")
        _make_linux_port(ports_dir, "GameB")
        automator = PortsAutomator(mode=ExecutionMode.DRY_RUN)
        automator.run()

        stats = automator.get_stats()
        assert stats.get("dry_run", 0) == 2


# ---------------------------------------------------------------------------
# Audit mode
# ---------------------------------------------------------------------------

class TestAuditMode:
    def test_audit_records_launchers(self, config_factory, ports_dir, tmp_project):
        config_factory({"ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          str(tmp_project / "output" / "ports_launchers"),
            "windows_runner":      "wine",
            "enable_gamemode":     False,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator

        _make_linux_port(ports_dir, "GameAudit")
        report = AuditReport()
        automator = PortsAutomator(mode=ExecutionMode.AUDIT, audit=report)
        automator.run()

        assert report.total == 1
        entry = report.entries()[0]
        assert entry.action == "create_launcher"
        assert entry.step == "PortsAutomator"

    def test_audit_creates_no_files(self, config_factory, ports_dir, tmp_project):
        out_dir = tmp_project / "output" / "ports_launchers"
        config_factory({"ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          str(out_dir),
            "windows_runner":      "wine",
            "enable_gamemode":     False,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator

        _make_linux_port(ports_dir)
        report = AuditReport()
        automator = PortsAutomator(mode=ExecutionMode.AUDIT, audit=report)
        automator.run()

        # out_dir pode ser criado (não é dry-run), mas sem autorun.sh nem .desktop
        for f in out_dir.rglob("*.desktop"):
            pytest.fail(f"Arquivo .desktop criado em modo audit: {f}")
        for f in out_dir.rglob("autorun.sh"):
            pytest.fail(f"autorun.sh criado em modo audit: {f}")


# ---------------------------------------------------------------------------
# Port Linux
# ---------------------------------------------------------------------------

class TestLinuxPort:
    def test_creates_autorun_sh(self, config_factory, ports_dir, tmp_project):
        out_dir = tmp_project / "output" / "ports_launchers"
        config_factory({"ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          str(out_dir),
            "windows_runner":      "wine",
            "enable_gamemode":     False,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator

        _make_linux_port(ports_dir, "CoolGame")
        automator = PortsAutomator()
        automator.run()

        autorun = out_dir / "CoolGame" / "autorun.sh"
        assert autorun.exists(), "autorun.sh não foi criado"
        content = autorun.read_text()
        assert "#!/bin/bash" in content
        assert "CoolGame" in content or "mygame" in content

    def test_creates_desktop_file(self, config_factory, ports_dir, tmp_project):
        out_dir = tmp_project / "output" / "ports_launchers"
        config_factory({"ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          str(out_dir),
            "windows_runner":      "wine",
            "enable_gamemode":     False,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator

        _make_linux_port(ports_dir, "CoolGame")
        automator = PortsAutomator()
        automator.run()

        desktop = out_dir / "CoolGame.desktop"
        assert desktop.exists(), ".desktop não foi criado"
        content = desktop.read_text()
        assert "[Desktop Entry]" in content
        assert "Type=Application" in content

    def test_autorun_is_executable(self, config_factory, ports_dir, tmp_project):
        out_dir = tmp_project / "output" / "ports_launchers"
        config_factory({"ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          str(out_dir),
            "windows_runner":      "wine",
            "enable_gamemode":     False,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator

        _make_linux_port(ports_dir, "CoolGame")
        automator = PortsAutomator()
        automator.run()

        autorun = out_dir / "CoolGame" / "autorun.sh"
        assert autorun.stat().st_mode & 0o111, "autorun.sh não é executável"

    def test_created_stat_incremented(self, config_factory, ports_dir, tmp_project):
        out_dir = tmp_project / "output" / "ports_launchers"
        config_factory({"ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          str(out_dir),
            "windows_runner":      "wine",
            "enable_gamemode":     False,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator

        _make_linux_port(ports_dir, "Game1")
        _make_linux_port(ports_dir, "Game2")
        automator = PortsAutomator()
        automator.run()

        assert automator.get_stats().get("created") == 2


# ---------------------------------------------------------------------------
# Port Windows (Wine)
# ---------------------------------------------------------------------------

class TestWindowsPort:
    def test_wine_autorun_contains_wineprefix(self, config_factory, ports_dir, tmp_project):
        out_dir = tmp_project / "output" / "ports_launchers"
        config_factory({"ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          str(out_dir),
            "windows_runner":      "wine",
            "enable_gamemode":     False,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator

        _make_windows_port(ports_dir, "WinGame")
        automator = PortsAutomator()
        automator.run()

        autorun = out_dir / "WinGame" / "autorun.sh"
        assert autorun.exists()
        content = autorun.read_text()
        assert "WINEPREFIX" in content
        assert "game.exe" in content

    def test_wine_autorun_calls_runner(self, config_factory, ports_dir, tmp_project):
        out_dir = tmp_project / "output" / "ports_launchers"
        config_factory({"ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          str(out_dir),
            "windows_runner":      "wine",
            "enable_gamemode":     False,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator

        _make_windows_port(ports_dir, "WinGame")
        automator = PortsAutomator()
        automator.run()

        autorun = out_dir / "WinGame" / "autorun.sh"
        content = autorun.read_text()
        assert "wine" in content


# ---------------------------------------------------------------------------
# Sem executável → skipped
# ---------------------------------------------------------------------------

class TestNoExecutable:
    def test_port_without_executable_skipped(self, config_factory, ports_dir, tmp_project):
        out_dir = tmp_project / "output" / "ports_launchers"
        config_factory({"ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          str(out_dir),
            "windows_runner":      "wine",
            "enable_gamemode":     False,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator

        # Cria pasta sem nenhum executável
        empty_port = ports_dir / "EmptyGame"
        empty_port.mkdir()
        (empty_port / "readme.txt").write_text("no exe here")

        automator = PortsAutomator()
        automator.run()

        stats = automator.get_stats()
        assert stats.get("created", 0) == 0
        assert stats.get("skipped_no_exec", 0) == 1


# ---------------------------------------------------------------------------
# gamemode / mangohud
# ---------------------------------------------------------------------------

class TestLaunchWrappers:
    def test_gamemode_in_autorun(self, config_factory, ports_dir, tmp_project):
        out_dir = tmp_project / "output" / "ports_launchers"
        config_factory({"ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          str(out_dir),
            "windows_runner":      "wine",
            "enable_gamemode":     True,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator

        _make_linux_port(ports_dir, "PerfGame")
        automator = PortsAutomator()
        automator.run()

        content = (out_dir / "PerfGame" / "autorun.sh").read_text()
        assert "gamemoderun" in content

    def test_mangohud_in_autorun(self, config_factory, ports_dir, tmp_project):
        out_dir = tmp_project / "output" / "ports_launchers"
        config_factory({"ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          str(out_dir),
            "windows_runner":      "wine",
            "enable_gamemode":     False,
            "enable_mangohud":     True,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator

        _make_linux_port(ports_dir, "HUDGame")
        automator = PortsAutomator()
        automator.run()

        content = (out_dir / "HUDGame" / "autorun.sh").read_text()
        assert "mangohud" in content

    def test_gamemode_not_in_windows_autorun(self, config_factory, ports_dir, tmp_project):
        """gamemode não deve aparecer no autorun de port Windows."""
        out_dir = tmp_project / "output" / "ports_launchers"
        config_factory({"ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          str(out_dir),
            "windows_runner":      "wine",
            "enable_gamemode":     True,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator

        _make_windows_port(ports_dir, "WinPerfGame")
        automator = PortsAutomator()
        automator.run()

        content = (out_dir / "WinPerfGame" / "autorun.sh").read_text()
        assert "gamemoderun" not in content


# ---------------------------------------------------------------------------
# Erro de I/O
# ---------------------------------------------------------------------------

class TestIOError:
    def test_io_error_sets_error_stat(self, config_factory, ports_dir, tmp_project):
        out_dir = tmp_project / "output" / "ports_launchers"
        config_factory({"ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          str(out_dir),
            "windows_runner":      "wine",
            "enable_gamemode":     False,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator
        from unittest.mock import patch

        _make_linux_port(ports_dir, "FailGame")
        automator = PortsAutomator()

        with patch("pathlib.Path.write_text", side_effect=OSError("permission denied")):
            automator.run()

        stats = automator.get_stats()
        assert stats.get("error", 0) >= 1

    def test_io_error_continues_to_next_port(self, config_factory, ports_dir, tmp_project):
        out_dir = tmp_project / "output" / "ports_launchers"
        config_factory({"ports": {
            "source_dir":          str(ports_dir),
            "output_dir":          str(out_dir),
            "windows_runner":      "wine",
            "enable_gamemode":     False,
            "enable_mangohud":     False,
            "windows_extensions":  [".exe"],
            "windows_environment": {},
        }})
        from emupipeline.steps.step_ports import PortsAutomator
        from unittest.mock import patch

        _make_linux_port(ports_dir, "AAA_FailGame")
        _make_linux_port(ports_dir, "ZZZ_OkGame")

        automator = PortsAutomator()

        write_calls = [0]

        original_write = Path.write_text

        def selective_fail(self, content, **kwargs):
            write_calls[0] += 1
            if "AAA_FailGame" in str(self):
                raise OSError("permission denied")
            original_write(self, content, **kwargs)

        with patch.object(Path, "write_text", selective_fail):
            automator.run()

        # ZZZ_OkGame deve ter sido processado apesar da falha em AAA_FailGame
        assert (out_dir / "ZZZ_OkGame.desktop").exists()


# ---------------------------------------------------------------------------
# _find_executable
# ---------------------------------------------------------------------------

class TestFindExecutable:
    def test_finds_linux_executable_no_suffix(self, tmp_path):
        from emupipeline.steps.step_ports import PortsAutomator

        port_dir = tmp_path / "game"
        port_dir.mkdir()
        exe = port_dir / "game"
        exe.write_bytes(b"#!/bin/bash")
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)

        result = PortsAutomator._find_executable(port_dir, {".exe"})
        assert result == exe

    def test_finds_sh_script(self, tmp_path):
        from emupipeline.steps.step_ports import PortsAutomator

        port_dir = tmp_path / "game"
        port_dir.mkdir()
        script = port_dir / "run.sh"
        script.write_bytes(b"#!/bin/bash")

        result = PortsAutomator._find_executable(port_dir, {".exe"})
        assert result == script

    def test_finds_exe_when_no_linux_exec(self, tmp_path):
        from emupipeline.steps.step_ports import PortsAutomator

        port_dir = tmp_path / "game"
        port_dir.mkdir()
        exe = port_dir / "game.exe"
        exe.write_bytes(b"MZ")

        result = PortsAutomator._find_executable(port_dir, {".exe"})
        assert result == exe

    def test_returns_none_for_empty_dir(self, tmp_path):
        from emupipeline.steps.step_ports import PortsAutomator

        port_dir = tmp_path / "empty"
        port_dir.mkdir()

        result = PortsAutomator._find_executable(port_dir, {".exe"})
        assert result is None
