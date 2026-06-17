"""
EmuPipeline CLI — entry point formal (emupipeline = "emupipeline.cli:main").

Menu gerado dinamicamente a partir do registry de steps.
Modos: interativo | --pipeline | --step N | --audit | --dry-run
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path


def _build_menu() -> str:
    from emupipeline.core.registry import autodiscover, get_all_steps
    autodiscover()

    groups: dict[str, list] = {}
    for cls in sorted(get_all_steps().values(), key=lambda c: (c.meta.group, c.meta.menu_number)):
        groups.setdefault(cls.meta.group, []).append(cls)

    w = 52
    lines = ["╔" + "═"*w + "╗", f"║{'  EmuPipeline v5.0':^{w}}║", "╠" + "═"*w + "╣"]
    for group_name, group_steps in groups.items():
        lines.append(f"║  {group_name:<{w-2}}║")
        for cls in group_steps:
            line = f"  {cls.meta.menu_number:>3}. {cls.meta.label}"
            lines.append(f"║{line:<{w}}║")
        lines.append("╠" + "═"*w + "╣")
    lines += [
        f"║{'  99. PIPELINE COMPLETO (automático)':<{w}}║",
        f"║{'   0. Sair':<{w}}║",
        "╚" + "═"*w + "╝",
    ]
    return "\n".join(lines)


def _make_step(cls: type, mode, audit=None) -> object:
    """Instancia step injetando mode e audit quando suportado."""
    import inspect
    sig = inspect.signature(cls.__init__)
    kwargs: dict = {}
    if "mode" in sig.parameters:
        kwargs["mode"] = mode
    if "audit" in sig.parameters:
        kwargs["audit"] = audit
    return cls(**kwargs)


def _load_dat():
    from emupipeline.core.config import cfg
    from emupipeline.core.dat_manager import DatMaster
    dat_path = cfg.get("paths", "dat_file")
    if not dat_path or not Path(str(dat_path)).exists():
        print(f"\n⚠  DAT não encontrado: {dat_path}")
        print("   Configure 'paths.dat_file' no config.yaml\n")
        return None
    return DatMaster(dat_path)


def _run_step_by_number(number: int, mode, audit=None) -> None:
    from emupipeline.core.registry import get_by_menu_number
    cls = get_by_menu_number(number)
    if cls is None:
        print(f"  Step '{number}' não encontrado.")
        return
    step = _make_step(cls, mode, audit)
    if cls.meta.requires_dat:
        dat = _load_dat()
        if dat is None:
            return
        step.run(dat=dat)
    else:
        step.run()


def run_full_pipeline(mode, audit=None) -> None:
    from emupipeline.core.logger import setup_logger
    from emupipeline.core.registry import get_pipeline_steps

    log = setup_logger("Pipeline")
    log.info("=" * 60)
    log.info("  PIPELINE COMPLETO")
    log.info("=" * 60)

    # Verifica ambiente antes de começar
    from emupipeline.core.config import cfg
    from emupipeline.core.env_checker import EnvironmentChecker
    checker = EnvironmentChecker(cfg.schema)
    checker.check_all()
    print(checker.report())
    if checker.has_critical_failures():
        raise SystemExit("\n❌ Corrija as dependências antes de continuar.")

    pipeline_steps = get_pipeline_steps()
    dat = None

    for cls in pipeline_steps:
        log.info(f"\n>>> [{cls.meta.label}]")
        try:
            step = _make_step(cls, mode, audit)
            if cls.meta.requires_dat:
                if dat is None:
                    dat = _load_dat()
                if dat is None:
                    log.warning(f"DAT não disponível, pulando {cls.meta.id}")
                    continue
                step.run(dat=dat)
            else:
                step.run()
        except Exception as exc:
            log.error(f"Erro em '{cls.meta.label}': {exc}")
            traceback.print_exc()
            resp = input(f"\nErro em '{cls.meta.label}'. Continuar? (s/N): ").strip().lower()
            if resp != "s":
                log.warning("Pipeline interrompido.")
                return

    log.info("\n>>> Pipeline completo finalizado.")

    # Exporta métricas de auditoria
    if audit is not None:
        from emupipeline.core.config import cfg
        reports = cfg.get("paths", "output_reports")
        if reports:
            audit.export_json(Path(str(reports)) / "audit_report.json")
            audit.export_html(Path(str(reports)) / "audit_report.html")
            audit.print_summary()


def interactive_menu(mode, audit=None) -> None:
    from emupipeline.core.registry import autodiscover
    autodiscover()

    while True:
        print(_build_menu())
        try:
            opt = input("Opção: ").strip()
        except EOFError:
            break

        if opt == "0":
            print("Saindo.")
            break
        if opt == "99":
            run_full_pipeline(mode, audit)
        elif opt.isdigit():
            try:
                _run_step_by_number(int(opt), mode, audit)
            except KeyboardInterrupt:
                print("\n  Interrompido.")
            except Exception as exc:
                print(f"  Erro: {exc}")
        else:
            print(f"  Opção '{opt}' inválida.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="emupipeline",
        description="EmuPipeline v5 — Gerenciador de biblioteca de emulação",
    )
    parser.add_argument("--pipeline",  action="store_true",
                        help="Executa pipeline completo sem menu")
    parser.add_argument("--step",      metavar="NUM", type=int,
                        help="Executa step pelo número do menu")
    parser.add_argument("--dry-run",   action="store_true",
                        help="Simula sem modificar arquivos")
    parser.add_argument("--audit",     action="store_true",
                        help="Gera relatório de operações sem modificar disco")
    parser.add_argument("--config",    metavar="PATH",
                        help="Caminho alternativo para config.yaml")
    parser.add_argument("--version",   action="version",
                        version="%(prog)s 5.0.0")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Config alternativo
    if args.config:
        import os
        os.environ["EMUPIPELINE_CONFIG"] = args.config
        from emupipeline.core.config import cfg
        cfg.reload()

    # Determina modo de execução
    from emupipeline.core.execution_mode import AuditReport, ExecutionMode
    if args.audit:
        mode  = ExecutionMode.AUDIT
        audit = AuditReport()
    elif args.dry_run:
        mode  = ExecutionMode.DRY_RUN
        audit = None
    else:
        mode  = ExecutionMode.NORMAL
        audit = None

    if mode != ExecutionMode.NORMAL:
        label = "AUDIT" if args.audit else "DRY-RUN"
        from emupipeline.core.logger import setup_logger
        setup_logger("CLI").warning(f"Modo {label} ativado.")

    try:
        if args.pipeline:
            run_full_pipeline(mode, audit)
        elif args.step is not None:
            _run_step_by_number(args.step, mode, audit)
        else:
            interactive_menu(mode, audit)
    except KeyboardInterrupt:
        print("\nSaindo.")
    except SystemExit:
        raise
    except Exception as exc:
        print(f"\nErro fatal: {exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
