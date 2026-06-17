"""
Contrato de interface para todos os steps do pipeline.

Usa Protocol (tipagem estrutural) ao invés de ABC nominal —
steps externos podem satisfazer a interface sem herdar de BaseProcessor.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class StepMeta:
    """Metadados declarativos de um step — sem instanciação da classe."""

    id:             str    # identificador único: "dat_split"
    menu_number:    int    # número no menu interativo: 1
    label:          str    # rótulo no menu: "Split DAT por driver"
    group:          str    # grupo no menu: "ROMs & DATs"
    description:    str    # exibido em --help
    requires_dat:   bool   = False  # se True, DatMaster é passado via run(dat=...)
    pipeline_order: int    = 999    # ordem no pipeline completo; 999 = excluído


@runtime_checkable
class StepProtocol(Protocol):
    """Contrato mínimo que todo step deve satisfazer."""

    meta: StepMeta  # atributo de CLASSE (não instância)

    def run(self, **kwargs: Any) -> None: ...
    def get_stats(self) -> dict[str, int]: ...
