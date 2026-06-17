"""Step 11 — Geração de launchers .desktop para Ports."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.logger import setup_logger
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta

log = setup_logger("PortsAutomator")

_AUTORUN_LINUX = """\
#!/bin/bash
cd "{game_dir}"
"{executable}"
"""

_AUTORUN_WINE = """\
#!/bin/bash
export WINEPREFIX="{wine_prefix}"
export WINEARCH=win64
{extra_env}
cd "{game_dir}"
"{runner}" "{executable}"
"""

_DESKTOP = """\
[Desktop Entry]
Name={name}
Exec=bash "{autorun}"
Type=Application
Categories=Game;
"""


@register
class PortsAutomator:
    meta = StepMeta(
        id="ports_launchers",
        menu_number=11,
        label="Gerar launchers de Ports (.desktop)",
        group="Extras",
        description="Cria autorun.sh e .desktop para ports Linux e Windows (Wine).",
        pipeline_order=999,
    )

    name = "PortsAutomator"

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        audit: Optional[AuditReport] = None,
    ) -> None:
        from emupipeline.core.config import cfg
        self._cfg   = cfg
        self._mode  = mode
        self._audit = audit
        self._stats: dict[str, int] = {}

    def get_stats(self) -> dict[str, int]:
        return dict(self._stats)

    def run(self, **kwargs: Any) -> None:
        ports_cfg   = self._cfg.get("ports")
        src_dir     = Path(str(getattr(ports_cfg, "source_dir",  "~/Emulation/ports"))).expanduser()
        out_dir     = Path(str(getattr(ports_cfg, "output_dir",  "~/Emulation/tools/ports_launchers"))).expanduser()
        runner      = str(getattr(ports_cfg, "windows_runner", "wine"))
        win_exts    = set(getattr(ports_cfg, "windows_extensions", [".exe"]))
        win_env     = getattr(ports_cfg, "windows_environment", {})
        gamemode    = getattr(ports_cfg, "enable_gamemode",    False)
        mangohud    = getattr(ports_cfg, "enable_mangohud",    False)
        wine_prefix = str(out_dir / ".wine_ports")

        extra_env_lines = "\n".join(f'export {k}="{v}"' for k, v in win_env.items())

        if not src_dir.exists():
            log.error(f"Diretório de ports não encontrado: {src_dir}")
            return

        if self._mode != ExecutionMode.DRY_RUN:
            out_dir.mkdir(parents=True, exist_ok=True)

        for port_dir in sorted(src_dir.iterdir()):
            if not port_dir.is_dir():
                continue

            executable = self._find_executable(port_dir, win_exts)
            if not executable:
                log.warning(f"Sem executável em: {port_dir.name}")
                self._stats["skipped_no_exec"] = self._stats.get("skipped_no_exec", 0) + 1
                continue

            is_windows   = executable.suffix.lower() in win_exts
            port_name    = port_dir.name.replace("_", " ")
            autorun_path = out_dir / port_dir.name / "autorun.sh"
            desktop_path = out_dir / f"{port_dir.name}.desktop"

            if self._mode == ExecutionMode.AUDIT:
                assert self._audit is not None
                self._audit.record(
                    step=self.name, action="create_launcher",
                    source=str(port_dir), dest=str(desktop_path),
                    reason=f"{'Wine' if is_windows else 'Linux'} port",
                )
                self._stats["audit_recorded"] = self._stats.get("audit_recorded", 0) + 1
                continue

            if self._mode == ExecutionMode.DRY_RUN:
                log.info(f"[DRY] Criaria launcher para: {port_name}")
                self._stats["dry_run"] = self._stats.get("dry_run", 0) + 1
                continue

            try:
                autorun_path.parent.mkdir(parents=True, exist_ok=True)

                if is_windows:
                    content = _AUTORUN_WINE.format(
                        wine_prefix=wine_prefix,
                        extra_env=extra_env_lines,
                        game_dir=port_dir,
                        runner=runner,
                        executable=executable.name,
                    )
                else:
                    exec_str = executable.name
                    if gamemode:
                        exec_str = f"gamemoderun {exec_str}"
                    if mangohud:
                        exec_str = f"mangohud {exec_str}"
                    content = _AUTORUN_LINUX.format(
                        game_dir=port_dir, executable=exec_str,
                    )

                autorun_path.write_text(content, encoding="utf-8")
                autorun_path.chmod(0o755)

                desktop_content = _DESKTOP.format(name=port_name, autorun=autorun_path)
                desktop_path.write_text(desktop_content, encoding="utf-8")

                self._stats["created"] = self._stats.get("created", 0) + 1
                log.debug(f"Launcher criado: {port_name}")
            except OSError as exc:
                log.error(f"Erro ao criar launcher para '{port_dir.name}': {exc}")
                self._stats["error"] = self._stats.get("error", 0) + 1

        total = self._stats.get("created", 0)
        log.info(f"Launchers criados: {total}")

    @staticmethod
    def _find_executable(port_dir: Path, win_exts: set[str]) -> Optional[Path]:
        for p in port_dir.iterdir():
            if p.is_file() and not p.suffix and p.stat().st_mode & 0o111:
                return p
        for p in port_dir.iterdir():
            if p.is_file() and p.suffix.lower() in (".x86_64", ".sh", ".AppImage"):
                return p
        for p in port_dir.iterdir():
            if p.is_file() and p.suffix.lower() in win_exts:
                return p
        return None
