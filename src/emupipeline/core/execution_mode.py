"""
Modos de execução e relatório de auditoria.

Três modos distintos — não confundir dry-run com audit:

  NORMAL   → execução real, escreve em disco
  DRY_RUN  → simula, imprime o que faria, zero I/O
  AUDIT    → executa toda lógica de decisão, registra operações
             em AuditReport exportável, zero escrita em disco

O modo é injetado nos steps via construtor. Na v4 era monkey-patch
de variável de classe — thread-unsafe e não reversível.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any


class ExecutionMode(Enum):
    NORMAL = auto()
    DRY_RUN = auto()
    AUDIT = auto()


@dataclass
class AuditEntry:
    step: str
    action: str
    source: str
    dest: str | None = None
    reason: str = ""
    would_delete: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


class AuditReport:
    """
    Coleta operações planejadas em modo AUDIT.
    Thread-safe — steps paralelos podem registrar simultaneamente.
    """

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._lock = threading.Lock()

    def record(
        self,
        step: str,
        action: str,
        source: str,
        dest: str | None = None,
        reason: str = "",
        would_delete: bool = False,
        **extra: Any,
    ) -> None:
        entry = AuditEntry(
            step=step, action=action, source=source,
            dest=dest, reason=reason, would_delete=would_delete, extra=extra,
        )
        with self._lock:
            self._entries.append(entry)

    def entries(self) -> list[AuditEntry]:
        with self._lock:
            return list(self._entries)

    @property
    def total(self) -> int:
        return len(self._entries)

    @property
    def destructive_count(self) -> int:
        return sum(1 for e in self.entries() if e.would_delete)

    # ------------------------------------------------------------------
    # Exportação
    # ------------------------------------------------------------------

    def export_json(self, path: Path) -> None:
        data = {
            "mode": "AUDIT",
            "total_operations": self.total,
            "destructive_operations": self.destructive_count,
            "operations": [
                {"step": e.step, "action": e.action, "source": e.source,
                 "dest": e.dest, "reason": e.reason, "would_delete": e.would_delete,
                 **e.extra}
                for e in self.entries()
            ],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def export_html(self, path: Path) -> None:
        rows = "\n".join(
            f"<tr class=\"{'destructive' if e.would_delete else ''}\">"
            f"<td>{e.step}</td><td>{e.action}</td>"
            f"<td title=\"{e.source}\">{Path(e.source).name}</td>"
            f"<td>{Path(e.dest).name if e.dest else '—'}</td>"
            f"<td>{'🗑 ' if e.would_delete else ''}{e.reason}</td></tr>"
            for e in self.entries()
        )
        html = f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8">
<title>EmuPipeline — Audit Report</title>
<style>
  body{{font-family:monospace;padding:20px;background:#1a1a1a;color:#e0e0e0}}
  h1{{color:#7cb8ff}} .summary{{background:#2a2a2a;padding:12px;border-radius:4px;margin-bottom:16px}}
  table{{border-collapse:collapse;width:100%;font-size:.85em}}
  th{{background:#333;padding:8px;text-align:left;position:sticky;top:0}}
  td{{padding:6px 8px;border-bottom:1px solid #333}}
  tr:hover{{background:#2a2a2a}} tr.destructive td{{color:#ff6b6b}}
  .badge{{display:inline-block;padding:2px 8px;border-radius:12px;background:#ff4444;color:white;font-size:.75em}}
</style></head><body>
<h1>🔍 EmuPipeline — Audit Report</h1>
<div class="summary">
  <strong>Total:</strong> {self.total} operações &nbsp;|&nbsp;
  <strong>Destrutivas:</strong> <span class="badge">{self.destructive_count}</span>
</div>
<table>
  <tr><th>Step</th><th>Ação</th><th>Fonte</th><th>Destino</th><th>Motivo</th></tr>
  {rows}
</table></body></html>"""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")

    def print_summary(self) -> None:
        print(f"\n{'='*60}")
        print(f"AUDIT REPORT — {self.total} operações planejadas")
        if self.destructive_count:
            print(f"⚠️  {self.destructive_count} operações DESTRUTIVAS (deleção)")
        print(f"{'='*60}")
        by_step: dict[str, dict[str, int]] = {}
        for e in self.entries():
            by_step.setdefault(e.step, {})
            by_step[e.step][e.action] = by_step[e.step].get(e.action, 0) + 1
        for step_name, actions in by_step.items():
            actions_str = " | ".join(f"{a}: {n}" for a, n in actions.items())
            print(f"  {step_name:<28} {actions_str}")
