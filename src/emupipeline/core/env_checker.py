"""
Verificação de dependências externas com fail-fast.

Problema resolvido: na v4 o pipeline podia rodar 40 minutos
e só então descobrir que igir não estava no PATH.

Agora: verificação completa antes de qualquer processamento,
com relatório legível e instrução de instalação por ferramenta.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class DepStatus:
    name:        str
    required:    bool
    found:       bool
    version:     Optional[str] = None
    min_version: Optional[str] = None
    version_ok:  bool = True
    hint:        str  = ""


class EnvironmentChecker:

    # Definição declarativa de cada ferramenta
    _TOOLS = [
        {
            "name": "ffmpeg",
            "required": True,
            "min_version": "4.0",
            "version_cmd": ["ffmpeg", "-version"],
            "version_pattern": r"ffmpeg version (\d+\.\d+)",
            "hint": "sudo dnf install ffmpeg  # Bazzite/Fedora\n"
                    "       sudo apt install ffmpeg   # Ubuntu/Debian",
        },
        {
            "name": "ffprobe",
            "required": True,
            "min_version": None,
            "version_cmd": ["ffprobe", "-version"],
            "version_pattern": r"ffprobe version (\d+\.\d+)",
            "hint": "Incluído com o pacote ffmpeg",
        },
        {
            "name": "igir",
            "required": False,   # obrigatório apenas se enable_igir=True
            "min_version": "1.8",
            "version_cmd": ["igir", "--version"],
            "version_pattern": r"(\d+\.\d+)",
            "hint": "npm install -g igir   (requer Node.js >= 18)",
        },
    ]

    def __init__(self, cfg: object) -> None:
        self._cfg = cfg
        self._results: list[DepStatus] = []

    def check_all(self, steps_to_run: list[str] | None = None) -> list[DepStatus]:
        """
        Verifica ferramentas relevantes para os steps solicitados.
        steps_to_run=None → verifica tudo.
        """
        self._results = []

        for tool in self._TOOLS:
            name = tool["name"]
            # Pula ferramentas que não são necessárias para os steps selecionados
            if steps_to_run is not None:
                if name == "igir" and "rom_manager" not in steps_to_run:
                    continue
                if name in ("ffmpeg", "ffprobe") and "optimize" not in steps_to_run:
                    continue
            self._results.append(self._check_tool(tool))

        # Binários de upscale (caminhos configurados, não no PATH)
        if steps_to_run is None or "upscale" in steps_to_run:
            for attr, label in [("bin_waifu2x", "waifu2x"), ("bin_realesrgan", "realesrgan")]:
                p = getattr(getattr(self._cfg, "paths", None), attr, None)
                if p:
                    self._results.append(DepStatus(
                        name=label, required=False,
                        found=Path(p).exists(),
                        hint=f"Configure paths.{attr} no config.yaml",
                    ))

        return self._results

    def _check_tool(self, tool: dict) -> DepStatus:
        name = tool["name"]
        found = shutil.which(name) is not None
        version: Optional[str] = None
        version_ok = True

        if found and tool.get("version_cmd"):
            try:
                r = subprocess.run(
                    tool["version_cmd"],
                    capture_output=True, text=True, timeout=10,
                )
                output = r.stdout + r.stderr
                if tool.get("version_pattern"):
                    m = re.search(tool["version_pattern"], output)
                    if m:
                        version = m.group(1)
                        if tool.get("min_version") and version:
                            version_ok = self._version_ge(version, tool["min_version"])
            except (subprocess.TimeoutExpired, FileNotFoundError):
                found = False

        return DepStatus(
            name=name,
            required=tool.get("required", False),
            found=found,
            version=version,
            min_version=tool.get("min_version"),
            version_ok=version_ok,
            hint=tool.get("hint", ""),
        )

    @staticmethod
    def _version_ge(v: str, minimum: str) -> bool:
        def parse(s: str) -> tuple[int, ...]:
            return tuple(int(x) for x in s.split(".")[:3] if x.isdigit())
        try:
            parsed = parse(v)
            if not parsed:  # string não reconhecida → assume compatível
                return True
            return parsed >= parse(minimum)
        except (ValueError, TypeError):
            return True

    def _check_path_binary(self, label: str, path: "str | Path | None") -> None:
        """Verifica binário em caminho absoluto e adiciona resultado a _results.

        Quando path=None (não configurado), ignora silenciosamente.
        """
        if path is None:
            return
        exists = Path(str(path)).exists()
        self._results.append(DepStatus(
            name=label, required=False, found=exists,
            hint="" if exists else f"Configure paths.{label.replace('-', '_')} no config.yaml",
        ))

    def report(self) -> str:
        lines = ["\n🔍 VERIFICAÇÃO DE AMBIENTE\n"]
        for s in self._results:
            if not s.found:
                icon = "❌" if s.required else "⚠️ "
                lines.append(f"  {icon} {s.name:<18} NÃO ENCONTRADO")
                if s.hint:
                    for line in s.hint.splitlines():
                        lines.append(f"       {line}")
            elif not s.version_ok:
                lines.append(f"  ⚠️  {s.name:<18} v{s.version} < mínimo v{s.min_version}")
                if s.hint:
                    lines.append(f"       Atualize: {s.hint}")
            else:
                ver = f"v{s.version}" if s.version else "(ok)"
                lines.append(f"  ✅ {s.name:<18} {ver}")
        return "\n".join(lines)

    def has_critical_failures(self) -> bool:
        return any(s.required and (not s.found or not s.version_ok) for s in self._results)

    def fail_fast(self, steps_to_run: list[str] | None = None) -> None:
        """Verifica e aborta com relatório legível se há falhas críticas."""
        self.check_all(steps_to_run)
        print(self.report())
        if self.has_critical_failures():
            raise SystemExit("\n❌ Corrija as dependências acima antes de continuar.\n")
