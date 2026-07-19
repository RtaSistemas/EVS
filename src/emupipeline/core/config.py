"""
ConfigLoader — singleton que carrega e valida config.yaml.

Ordem de busca:
  1. Variável de ambiente EMUPIPELINE_CONFIG
  2. Diretório de trabalho atual (CWD/config.yaml)
  3. Diretório raiz do pacote instalado

Paths relativos na seção `paths` são resolvidos contra `global.base_dir`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from emupipeline.core.config_schema import ConfigSchema, load_and_validate


class ConfigLoader:
    """Singleton. Importe como: `from emupipeline.core.config import cfg`"""

    _instance: "ConfigLoader | None" = None

    def __new__(cls) -> "ConfigLoader":
        if cls._instance is None:
            inst = object.__new__(cls)
            inst._schema: ConfigSchema | None = None
            inst._load()
            cls._instance = inst
        return cls._instance

    # ------------------------------------------------------------------
    # Carregamento
    # ------------------------------------------------------------------

    def _find_config(self) -> Path:
        env = os.environ.get("EMUPIPELINE_CONFIG")
        if env:
            p = Path(env)
            if p.exists():
                return p
            raise FileNotFoundError(f"EMUPIPELINE_CONFIG aponta para arquivo inexistente: {p}")

        candidates = [
            Path.cwd() / "config.yaml",
            Path(__file__).resolve().parent.parent.parent.parent / "config.yaml",
        ]
        for c in candidates:
            if c.exists():
                return c

        raise FileNotFoundError(
            "config.yaml não encontrado.\n"
            "Defina EMUPIPELINE_CONFIG=<caminho> ou rode do diretório do projeto."
        )

    def _load(self) -> None:
        path = self._find_config()
        with open(path, encoding="utf-8") as fh:
            raw: dict = yaml.safe_load(fh) or {}

        # Resolve caminhos relativos em `paths` contra base_dir
        base_dir_raw = raw.get("global", {}).get("base_dir", "~/emupipeline")
        base = Path(os.path.expanduser(base_dir_raw)).resolve()
        paths_raw = raw.get("paths", {})
        for key, val in paths_raw.items():
            if isinstance(val, str) and not val.startswith("/") and not val.startswith("~"):
                paths_raw[key] = str(base / val)

        self._schema = load_and_validate(path, raw)

    # ------------------------------------------------------------------
    # Acesso
    # ------------------------------------------------------------------

    @property
    def schema(self) -> ConfigSchema:
        assert self._schema is not None
        return self._schema

    def get(self, section: str, key: str | None = None, default: Any = None) -> Any:
        """
        Acesso compatível com a v4.

        cfg.get("global", "threads")  → int
        cfg.get("videos", "crf")      → int
        cfg.get("paths", "dat_file")  → Path
        cfg.get("images")             → sub-objeto com atributos
        """
        section_map = {
            "global":    lambda: self._schema.global_,   # type: ignore[union-attr]
            "paths":     lambda: self._schema.paths,     # type: ignore[union-attr]
            "roms":      lambda: self._schema.roms,      # type: ignore[union-attr]
            "images":    lambda: self._schema.images,    # type: ignore[union-attr]
            "webp":      lambda: self._schema.webp,      # type: ignore[union-attr]
            "videos":    lambda: self._schema.videos,    # type: ignore[union-attr]
            "upscale":   lambda: self._schema.upscale,   # type: ignore[union-attr]
            "compare":   lambda: self._schema.compare,   # type: ignore[union-attr]
            "ports":     lambda: self._schema.ports,     # type: ignore[union-attr]
            "compress":  lambda: self._schema.compress,  # type: ignore[union-attr]
        }
        getter = section_map.get(section)
        if getter is None:
            return default
        obj = getter()
        if key is None:
            return obj
        # Seção global é mapeada como global_ no schema
        attr = "base_dir" if (section == "global" and key == "base_dir") else key
        return getattr(obj, attr, default)

    @property
    def base_dir(self) -> Path:
        return self._schema.global_.base_dir  # type: ignore[union-attr]

    def reload(self) -> None:
        """Força recarga (útil em testes)."""
        ConfigLoader._instance = None
        self._schema = None
        self._load()
        ConfigLoader._instance = self


# Instância global
cfg = ConfigLoader()
