"""
EmuPipeline TUI — Interface gráfica no terminal via Textual.

Invocada com:  emupipeline --tui
               emupipeline --tui --dry-run
               emupipeline --tui --audit

Layout:
  ┌─ Header ─────────────────────────────────────────────────┐
  │  Sidebar (steps)  │  Log panel (live output)             │
  │                   ├──────────────────────────────────────┤
  │                   │  Stats table                         │
  ├───────────────────┴──────────────────────────────────────┤
  │  Footer (key bindings)                                   │
  └──────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Label,
    ProgressBar,
    RichLog,
    Static,
)


# ──────────────────────────────────────────────────────────────────────────────
# Estilos CSS embutidos
# ──────────────────────────────────────────────────────────────────────────────

CSS = """
Screen {
    background: $surface;
}

#header-bar {
    height: 1;
    background: $primary;
    color: $text;
    content-align: center middle;
    text-style: bold;
}

#mode-badge {
    height: 1;
    width: auto;
    padding: 0 2;
    background: $warning;
    color: $text;
    text-style: bold;
    content-align: center middle;
}

#mode-badge.normal  { background: $success; }
#mode-badge.dry-run { background: $warning; }
#mode-badge.audit   { background: $accent;  }

/* Sidebar */
#sidebar {
    width: 26;
    height: 100%;
    background: $panel;
    border-right: solid $primary-darken-2;
    padding: 0 1;
}

.group-label {
    background: $primary-darken-2;
    color: $text-muted;
    width: 100%;
    padding: 0 1;
    text-style: bold;
}

.step-item {
    height: 1;
    padding: 0 1;
    color: $text-muted;
    width: 100%;
}

.step-item.pending  { color: $text-muted; }
.step-item.running  { color: $warning; text-style: bold; }
.step-item.done     { color: $success; }
.step-item.error    { color: $error; }
.step-item.skipped  { color: $text-disabled; }

/* Main content */
#main-area {
    width: 1fr;
    height: 100%;
}

#log-panel {
    height: 1fr;
    border: solid $primary-darken-2;
    padding: 0 1;
}

#log-title {
    background: $primary-darken-2;
    color: $text-muted;
    padding: 0 1;
    width: 100%;
}

#progress-row {
    height: 3;
    padding: 0 1;
    background: $panel;
    align: left middle;
}

#progress-label {
    width: 20;
    color: $text-muted;
}

#prog-bar {
    width: 1fr;
}

/* Stats */
#stats-panel {
    height: 10;
    border: solid $primary-darken-2;
}

#stats-title {
    background: $primary-darken-2;
    color: $text-muted;
    padding: 0 1;
    width: 100%;
}

#stats-table {
    height: 1fr;
    background: $surface;
}

/* Buttons */
#action-bar {
    height: 3;
    background: $panel;
    align: center middle;
    padding: 0 1;
}

Button {
    margin: 0 1;
    min-width: 14;
}
"""


# ──────────────────────────────────────────────────────────────────────────────
# Widgets de apoio
# ──────────────────────────────────────────────────────────────────────────────

STEP_ICONS = {
    "pending": "○",
    "running": "►",
    "done":    "✓",
    "error":   "✗",
    "skipped": "–",
}


class StepItem(Static):
    """Linha de step na sidebar com ícone de estado."""

    DEFAULT_CSS = ""

    def __init__(self, step_id: str, label: str) -> None:
        super().__init__(f"  {STEP_ICONS['pending']} {label}")
        self.step_id = step_id
        self._label = label
        self._state = "pending"
        self.add_class("step-item", "pending")

    def set_state(self, state: str) -> None:
        self.remove_class(self._state)
        self._state = state
        icon = STEP_ICONS.get(state, "○")
        self.update(f"  {icon} {self._label}")
        self.add_class(state)


class GroupLabel(Static):
    """Cabeçalho de grupo na sidebar."""

    def __init__(self, name: str) -> None:
        super().__init__(f" {name}")
        self.add_class("group-label")


# ──────────────────────────────────────────────────────────────────────────────
# Logging handler que redireciona para o RichLog
# ──────────────────────────────────────────────────────────────────────────────

import logging

LEVEL_COLORS = {
    logging.DEBUG:    "[dim]",
    logging.INFO:     "[cyan]",
    logging.WARNING:  "[yellow]",
    logging.ERROR:    "[red bold]",
    logging.CRITICAL: "[red bold reverse]",
}


class TuiLogHandler(logging.Handler):
    """Redireciona logs do Python para o painel RichLog da TUI."""

    def __init__(self, rich_log: RichLog) -> None:
        super().__init__()
        self._log = rich_log

    def emit(self, record: logging.LogRecord) -> None:
        try:
            color = LEVEL_COLORS.get(record.levelno, "")
            end   = "[/]" if color else ""
            ts    = time.strftime("%H:%M:%S", time.localtime(record.created))
            name  = record.name[-18:].ljust(18)
            level = record.levelname[:7].ljust(7)
            msg   = self.format(record)
            line  = f"[dim]{ts}[/] {color}{level}[/] [italic]{name}[/] {color}{msg}{end}"
            self._log.write(line)
        except Exception:  # noqa: BLE001
            pass


# ──────────────────────────────────────────────────────────────────────────────
# App principal
# ──────────────────────────────────────────────────────────────────────────────

class EmuPipelineApp(App):
    """Interface gráfica terminal para EmuPipeline."""

    TITLE   = "EmuPipeline v5.0"
    CSS     = CSS
    BINDINGS = [
        Binding("p",     "run_pipeline",  "Pipeline",   priority=True),
        Binding("d",     "toggle_dryrun", "Dry-Run",    priority=True),
        Binding("a",     "toggle_audit",  "Audit",      priority=True),
        Binding("c",     "clear_log",     "Limpar log", priority=True),
        Binding("escape","cancel",        "Cancelar",   priority=True),
        Binding("q",     "quit",          "Sair",       priority=True),
    ]

    def __init__(self, initial_mode: str = "normal") -> None:
        super().__init__()
        self._mode_name = initial_mode   # "normal" | "dry-run" | "audit"
        self._running   = False
        self._cancel    = threading.Event()
        self._step_widgets: dict[str, StepItem] = {}
        self._handler: TuiLogHandler | None = None
        self._stats_buffer: dict[str, dict[str, int]] = {}

    # ── composição ────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="top-bar"):
            yield Static(f" Modo: ", id="mode-prefix")
            yield Static(self._mode_label(), id="mode-badge",
                         classes=f"mode-badge {self._mode_name}")

        with Horizontal(id="body"):
            # Sidebar
            with Vertical(id="sidebar"):
                yield Static(" STEPS", classes="group-label")
                yield from self._build_sidebar()

            # Área principal
            with Vertical(id="main-area"):
                # Barra de progresso
                with Horizontal(id="progress-row"):
                    yield Label("Aguardando…", id="progress-label")
                    yield ProgressBar(id="prog-bar", total=100, show_eta=False)

                # Log
                yield Static(" LOG DO PIPELINE", id="log-title")
                yield RichLog(id="log-panel", highlight=True, markup=True,
                              auto_scroll=True, wrap=True)

                # Stats
                yield Static(" ESTATÍSTICAS DO STEP ATUAL", id="stats-title")
                yield DataTable(id="stats-table", zebra_stripes=True)

        # Botões de ação
        with Horizontal(id="action-bar"):
            yield Button("▶  Pipeline (P)",   id="btn-pipeline", variant="success")
            yield Button("⏸  Dry-Run (D)",    id="btn-dry",      variant="warning")
            yield Button("🔍 Audit (A)",       id="btn-audit",    variant="primary")
            yield Button("✕  Cancelar (Esc)", id="btn-cancel",   variant="error")

        yield Footer()

    def _mode_label(self) -> str:
        labels = {
            "normal":  " ● NORMAL ",
            "dry-run": " ⏸ DRY-RUN ",
            "audit":   " 🔍 AUDIT ",
        }
        return labels.get(self._mode_name, self._mode_name.upper())

    def _build_sidebar(self):
        """Gera StepItem e GroupLabel para todos os steps registrados."""
        try:
            from emupipeline.core.registry import autodiscover, get_all_steps
            autodiscover()
            all_steps = get_all_steps()
            groups: dict[str, list] = {}
            for cls in sorted(all_steps.values(),
                               key=lambda c: (c.meta.group, c.meta.menu_number)):
                groups.setdefault(cls.meta.group, []).append(cls)

            for group_name, group_steps in groups.items():
                yield GroupLabel(group_name)
                for cls in group_steps:
                    w = StepItem(cls.meta.id, cls.meta.label[:20])
                    self._step_widgets[cls.meta.id] = w
                    yield w
        except Exception as exc:
            yield Static(f"[red]Erro ao carregar steps: {exc}[/]")

    # ── mount / setup ─────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Configura logging e tabela de stats ao montar."""
        rich_log = self.query_one("#log-panel", RichLog)

        # Conecta handler de logging
        self._handler = TuiLogHandler(rich_log)
        self._handler.setFormatter(logging.Formatter("%(message)s"))
        logging.root.addHandler(self._handler)
        logging.root.setLevel(logging.DEBUG)

        # Configura tabela de stats
        table = self.query_one("#stats-table", DataTable)
        table.add_columns("Métrica", "Valor")

        # Log inicial
        rich_log.write("[bold cyan]EmuPipeline TUI iniciada.[/]")
        rich_log.write(f"Modo: [bold]{self._mode_label()}[/]")
        try:
            from emupipeline.core.config import cfg
            rich_log.write(f"Config: [italic]{cfg.base_dir}[/]")
        except Exception:
            rich_log.write("[yellow]Config não carregada — rode do diretório do projeto.[/]")

    def on_unmount(self) -> None:
        if self._handler:
            logging.root.removeHandler(self._handler)

    # ── botões ────────────────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-pipeline")
    def _btn_pipeline(self) -> None:
        self.action_run_pipeline()

    @on(Button.Pressed, "#btn-dry")
    def _btn_dry(self) -> None:
        self.action_toggle_dryrun()

    @on(Button.Pressed, "#btn-audit")
    def _btn_audit(self) -> None:
        self.action_toggle_audit()

    @on(Button.Pressed, "#btn-cancel")
    def _btn_cancel(self) -> None:
        self.action_cancel()

    # ── ações de teclado ──────────────────────────────────────────────────────

    def action_toggle_dryrun(self) -> None:
        if self._running:
            return
        self._mode_name = "normal" if self._mode_name == "dry-run" else "dry-run"
        self._refresh_mode()

    def action_toggle_audit(self) -> None:
        if self._running:
            return
        self._mode_name = "normal" if self._mode_name == "audit" else "audit"
        self._refresh_mode()

    def action_cancel(self) -> None:
        if self._running:
            self._cancel.set()
            log = self.query_one("#log-panel", RichLog)
            log.write("[yellow]⚠ Cancelamento solicitado…[/]")

    def action_clear_log(self) -> None:
        self.query_one("#log-panel", RichLog).clear()

    def action_run_pipeline(self) -> None:
        if self._running:
            self.query_one("#log-panel", RichLog).write(
                "[yellow]Pipeline já em execução.[/]"
            )
            return
        self._cancel.clear()
        self._execute_pipeline()

    def _refresh_mode(self) -> None:
        badge = self.query_one("#mode-badge", Static)
        badge.update(self._mode_label())
        badge.remove_class("normal", "dry-run", "audit")
        badge.add_class(self._mode_name)
        self.query_one("#log-panel", RichLog).write(
            f"[bold]Modo alterado para: {self._mode_label()}[/]"
        )

    # ── execução do pipeline ──────────────────────────────────────────────────

    @work(thread=True)
    def _execute_pipeline(self) -> None:
        """Executa o pipeline em thread separada para não bloquear a UI."""
        self._running = True
        self.call_from_thread(self._set_ui_running, True)

        try:
            from emupipeline.core.execution_mode import AuditReport, ExecutionMode
            from emupipeline.core.registry import get_pipeline_steps

            mode_map = {
                "normal":  ExecutionMode.NORMAL,
                "dry-run": ExecutionMode.DRY_RUN,
                "audit":   ExecutionMode.AUDIT,
            }
            mode  = mode_map.get(self._mode_name, ExecutionMode.NORMAL)
            audit = AuditReport() if mode == ExecutionMode.AUDIT else None

            pipeline_steps = get_pipeline_steps()
            total = len(pipeline_steps)
            dat   = None

            for i, cls in enumerate(pipeline_steps):
                if self._cancel.is_set():
                    self.call_from_thread(
                        self._log, "[yellow]Pipeline cancelado pelo usuário.[/]"
                    )
                    break

                step_id = cls.meta.id
                self.call_from_thread(self._set_step_state, step_id, "running")
                self.call_from_thread(
                    self._update_progress,
                    f"[{i+1}/{total}] {cls.meta.label}",
                    int(i / total * 100),
                )

                try:
                    import inspect
                    sig = inspect.signature(cls.__init__)
                    kwargs: dict[str, Any] = {}
                    if "mode"  in sig.parameters: kwargs["mode"]  = mode
                    if "audit" in sig.parameters: kwargs["audit"] = audit
                    step = cls(**kwargs)

                    if cls.meta.requires_dat:
                        if dat is None:
                            dat = self._try_load_dat()
                        if dat is None:
                            self.call_from_thread(
                                self._log,
                                f"[yellow]⚠ DAT indisponível — pulando {cls.meta.id}[/]",
                            )
                            self.call_from_thread(self._set_step_state, step_id, "skipped")
                            continue
                        step.run(dat=dat)
                    else:
                        step.run()

                    stats = step.get_stats() if hasattr(step, "get_stats") else {}
                    self.call_from_thread(self._update_stats, step_id, stats)
                    self.call_from_thread(self._set_step_state, step_id, "done")

                except Exception as exc:
                    self.call_from_thread(
                        self._log, f"[red bold]✗ Erro em '{cls.meta.label}': {exc}[/]"
                    )
                    self.call_from_thread(self._set_step_state, step_id, "error")

            self.call_from_thread(self._update_progress, "Pipeline concluído ✓", 100)

            # Exporta audit se ativo
            if audit is not None:
                self._export_audit(audit)

        except Exception as exc:
            self.call_from_thread(
                self._log, f"[red bold]Erro fatal no pipeline: {exc}[/]"
            )
        finally:
            self._running = False
            self.call_from_thread(self._set_ui_running, False)

    def _try_load_dat(self):
        try:
            from emupipeline.core.config import cfg
            from emupipeline.core.dat_manager import DatMaster
            dat_path = cfg.get("paths", "dat_file")
            if dat_path and Path(str(dat_path)).exists():
                return DatMaster(dat_path)
        except Exception as exc:
            self.call_from_thread(self._log, f"[red]Erro ao carregar DAT: {exc}[/]")
        return None

    def _export_audit(self, audit) -> None:
        try:
            from emupipeline.core.config import cfg
            reports = cfg.get("paths", "output_reports")
            if reports:
                out = Path(str(reports))
                out.mkdir(parents=True, exist_ok=True)
                audit.export_json(out / "audit_report.json")
                audit.export_html(out / "audit_report.html")
                self.call_from_thread(
                    self._log,
                    f"[green]Relatório de auditoria salvo em: {out}[/]",
                )
        except Exception as exc:
            self.call_from_thread(self._log, f"[yellow]Audit export: {exc}[/]")

    # ── helpers de UI (chamados via call_from_thread) ─────────────────────────

    def _log(self, msg: str) -> None:
        self.query_one("#log-panel", RichLog).write(msg)

    def _set_step_state(self, step_id: str, state: str) -> None:
        if step_id in self._step_widgets:
            self._step_widgets[step_id].set_state(state)

    def _update_progress(self, label: str, percent: int) -> None:
        self.query_one("#progress-label", Label).update(label)
        bar = self.query_one("#prog-bar", ProgressBar)
        bar.progress = percent

    def _update_stats(self, step_id: str, stats: dict[str, int]) -> None:
        self._stats_buffer[step_id] = stats
        table = self.query_one("#stats-table", DataTable)
        table.clear()
        for key, val in stats.items():
            table.add_row(key, str(val))

    def _set_ui_running(self, running: bool) -> None:
        btn_p = self.query_one("#btn-pipeline", Button)
        btn_p.disabled = running
        if running:
            btn_p.label = "⏳ Executando…"
        else:
            btn_p.label = "▶  Pipeline (P)"

    # ── step individual (clique futuro) ───────────────────────────────────────

    def run_single_step(self, step_id: str) -> None:
        """Executa um step individualmente (extensão futura)."""
        self._log(f"[dim]Executando step: {step_id}…[/]")


# ──────────────────────────────────────────────────────────────────────────────
# Entry point da TUI
# ──────────────────────────────────────────────────────────────────────────────

def launch_tui(mode: str = "normal") -> None:
    """Lança a TUI. Chamado por cli.py quando --tui é passado."""
    app = EmuPipelineApp(initial_mode=mode)
    app.run()
