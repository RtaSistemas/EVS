"""Step 11 — Geração de launchers .desktop para Ports.
Herda BaseProcessor (arquitetura consistente).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.processor import BaseProcessor
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta

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
class PortsAutomator(BaseProcessor):
    meta = StepMeta(
        id="ports_launchers",
        menu_number=11,
        label="Gerar launchers de Ports (.desktop)",
        group="Extras",
        description="Cria autorun.sh e .desktop para ports Linux e Windows (Wine).",
        pipeline_order=999,
    )

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        audit: Optional[AuditReport] = None,
    ) -> None:
        super().__init__("PortsAutomator", mode=mode, audit=audit)

    def process_file(self, file_path: Path) -> str:
        return "not_applicable"

    def run(self, **kwargs: Any) -> None:
        ports_cfg   = self.config.get("ports")
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
            self.logger.error(f"Diretório de ports não encontrado: {src_dir}")
            return

        if self._mode == ExecutionMode.NORMAL:
            out_dir.mkdir(parents=True, exist_ok=True)

        for port_dir in sorted(src_dir.iterdir()):
            if not port_dir.is_dir():
                continue

            executable = self._find_executable(port_dir, win_exts)
            if not executable:
                self.logger.warning(f"Sem executável em: {port_dir.name}")
                self.update_stat("skipped_no_exec")
                continue

            is_windows   = executable.suffix.lower() in win_exts
            port_name    = port_dir.name.replace("_", " ")
            autorun_path = out_dir / port_dir.name / "autorun.sh"
            desktop_path = out_dir / f"{port_dir.name}.desktop"

            if self._mode == ExecutionMode.AUDIT:
                if self._audit is None:
                    self.logger.error("AUDIT mode requer AuditReport injetado no construtor.")
                    self.update_stat("error")
                    continue
                self._audit.record(
                    step=self.name, action="create_launcher",
                    source=str(port_dir), dest=str(desktop_path),
                    reason=f"{'Wine' if is_windows else 'Linux'} port",
                )
                self.update_stat("audit_recorded")
                continue

            if self._mode == ExecutionMode.DRY_RUN:
                self.logger.info(f"[DRY] Criaria launcher para: {port_name}")
                self.update_stat("dry_run")
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

                self.update_stat("created")
                self.logger.debug(f"Launcher criado: {port_name}")
            except OSError as exc:
                self.logger.error(f"Erro ao criar launcher para '{port_dir.name}': {exc}")
                self.update_stat("error")

        total = self.get_stats().get("created", 0)
        self.logger.info(f"Launchers criados: {total}")

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
