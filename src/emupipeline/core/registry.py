"""
Registry de steps com descoberta automática.

Dois mecanismos:
  1. Automático: varre emupipeline.steps via pkgutil
  2. Plugins externos: entry_points "emupipeline.steps"
     (pip install emupipeline-myplugin, declarado no pyproject.toml do plugin)

O simples import de cada módulo dispara o decorator @register.
"""

from __future__ import annotations

import importlib
import importlib.metadata
import pkgutil
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from emupipeline.core.step_interface import StepMeta, StepProtocol

_REGISTRY: dict[str, type["StepProtocol"]] = {}
_log = logging.getLogger("Registry")


def register(cls: type) -> type:
    """
    Decorator que registra uma classe de step.

    Uso:
        @register
        class DatSplitter(BaseProcessor):
            meta = StepMeta(id="dat_split", ...)
    """
    meta = getattr(cls, "meta", None)
    if meta is None:
        raise TypeError(f"{cls.__name__} não tem atributo `meta` (StepMeta).")

    step_id: str = meta.id
    if step_id in _REGISTRY:
        existing = _REGISTRY[step_id]
        if existing is not cls:
            raise ValueError(
                f"Step ID duplicado: '{step_id}'.\n"
                f"  Já registrado: {existing.__module__}.{existing.__name__}\n"
                f"  Conflito com:  {cls.__module__}.{cls.__name__}"
            )
    _REGISTRY[step_id] = cls
    return cls


def autodiscover() -> None:
    """
    Importa todos os módulos em emupipeline.steps e plugins externos.
    Idempotente — pode ser chamado múltiplas vezes com segurança.
    """
    if _REGISTRY:
        return  # já descoberto

    # 1. Steps internos
    import emupipeline.steps as steps_pkg
    for info in pkgutil.iter_modules(steps_pkg.__path__):
        try:
            importlib.import_module(f"emupipeline.steps.{info.name}")
        except Exception as exc:
            _log.warning(f"Falha ao carregar step '{info.name}': {exc}")

    # 2. Plugins externos via entry_points
    try:
        eps = importlib.metadata.entry_points(group="emupipeline.steps")
        for ep in eps:
            try:
                ep.load()
            except Exception as exc:
                _log.warning(f"Falha ao carregar plugin '{ep.name}': {exc}")
    except Exception:
        pass  # entry_points indisponível — ignora silenciosamente


def get_step(step_id: str) -> type["StepProtocol"]:
    if not _REGISTRY:
        autodiscover()
    if step_id not in _REGISTRY:
        raise KeyError(
            f"Step '{step_id}' não encontrado.\n"
            f"Disponíveis: {sorted(_REGISTRY.keys())}"
        )
    return _REGISTRY[step_id]


def get_by_menu_number(number: int) -> type["StepProtocol"] | None:
    if not _REGISTRY:
        autodiscover()
    for cls in _REGISTRY.values():
        if cls.meta.menu_number == number:
            return cls
    return None


def get_all_steps() -> dict[str, type["StepProtocol"]]:
    if not _REGISTRY:
        autodiscover()
    return dict(_REGISTRY)


def get_pipeline_steps() -> list[type["StepProtocol"]]:
    """Retorna steps na ordem do pipeline automático (pipeline_order < 999)."""
    steps = [cls for cls in get_all_steps().values() if cls.meta.pipeline_order < 999]
    return sorted(steps, key=lambda c: c.meta.pipeline_order)
