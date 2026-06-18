"""
Step 1 — Split DAT por driver.

Divide o DAT Mestre em arquivos por driver (cps1, neogeo…)
aplicando filtros de blacklist, clones e BIOS.

Mudanças v5:
  - @register + StepMeta (autodiscovery)
  - StagingTransaction: output limpo e atômico
  - ExecutionMode: suporte a dry_run e audit
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional

from emupipeline.core.dat_manager import resolve_driver
from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.logger import setup_logger
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta
from emupipeline.core.transaction import StagingTransaction

log = setup_logger("DatSplitter")


@register
class DatSplitter:
    meta = StepMeta(
        id="dat_split",
        menu_number=1,
        label="Split DAT por driver (+ filtros)",
        group="ROMs & DATs",
        description="Divide o DAT Mestre em arquivos por driver com blacklist/clones.",
        pipeline_order=10,
    )

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        audit: Optional[AuditReport] = None,
    ) -> None:
        from emupipeline.core.config import cfg
        self._cfg    = cfg
        self._mode   = mode
        self._audit  = audit
        self._stats: dict[str, int] = {}

    def get_stats(self) -> dict[str, int]:
        return dict(self._stats)

    def _inc(self, key: str) -> None:
        self._stats[key] = self._stats.get(key, 0) + 1

    def run(self, **kwargs: Any) -> None:
        dat_path = self._cfg.get("paths", "dat_file")
        out_dir  = self._cfg.get("paths", "output_dats")
        roms_cfg = self._cfg.get("roms")

        if not Path(dat_path).exists():
            log.error(f"DAT não encontrado: {dat_path}")
            return

        blacklist      = [b.lower() for b in getattr(roms_cfg, "blacklist", [])]
        exclude_clones = getattr(roms_cfg, "exclude_clones", True)
        split          = getattr(roms_cfg, "split_by_driver", True)
        gen_bios       = getattr(roms_cfg, "generate_bios_file", False)
        combined_name  = getattr(roms_cfg, "combined_filename", "FBNeo_Optimized.dat")
        bios_name      = getattr(roms_cfg, "bios_filename", "00_BIOS_Global.dat")

        log.info(f"Lendo DAT: {Path(dat_path).name}")
        raw = Path(dat_path).read_bytes()
        raw = raw.lstrip(b"\xef\xbb\xbf").replace(b"\r\n", b"\n")
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            log.error(f"Erro de parse: {exc}")
            return

        header_el = root.find("header")

        groups:    dict[str, list[ET.Element]] = {}
        bios_list: list[ET.Element]            = []
        total = kept = 0

        for machine in root:
            if machine.tag not in ("game", "machine"):
                continue
            total += 1
            name    = machine.get("name", "")
            is_bios = machine.get("isbios", "no") == "yes"
            desc_el = machine.find("description")
            desc    = (desc_el.text or "").lower() if desc_el is not None else ""

            # Filtros
            if any(b in desc for b in blacklist):
                self._inc("blacklisted")
                continue
            if exclude_clones and machine.get("cloneof"):
                self._inc("clone_excluded")
                continue

            if is_bios:
                if gen_bios:
                    bios_list.append(machine)
                self._inc("bios_excluded")
                continue

            driver = resolve_driver(machine.get("sourcefile", ""))
            groups.setdefault(driver, []).append(machine)
            kept += 1

        log.info(f"Total: {total} | Mantidos: {kept} | Excluídos: {total - kept}")

        if self._mode == ExecutionMode.AUDIT:
            records = groups.items() if split else [("combined", [m for ms in groups.values() for m in ms])]
            for driver, machines in records:
                fname = f"{driver}.dat" if split else combined_name
                if self._audit:
                    self._audit.record(
                        step="dat_split", action="create_dat",
                        source=str(dat_path), dest=str(Path(out_dir) / fname),
                        reason=f"{len(machines)} jogos",
                    )
            return

        if self._mode == ExecutionMode.DRY_RUN:
            log.info(f"[DRY] Geraria {len(groups)} DATs em {out_dir}")
            return

        # Escrita atômica via StagingTransaction
        with StagingTransaction(Path(out_dir)) as txn:
            if split:
                for driver, machines in groups.items():
                    fname = f"{driver}.dat"
                    dest  = txn.stage_path(fname)
                    self._write_dat(dest, machines, header_el)
                    self._inc("dats_created")
                    if self._audit:
                        self._audit.record(
                            step="dat_split", action="create_dat",
                            source=str(dat_path), dest=str(Path(out_dir) / fname),
                            reason=f"{len(machines)} jogos",
                        )
            else:
                all_machines = [m for ms in groups.values() for m in ms]
                dest = txn.stage_path(combined_name)
                self._write_dat(dest, all_machines, header_el)
                self._inc("dats_created")

            if gen_bios and bios_list:
                dest = txn.stage_path(bios_name)
                self._write_dat(dest, bios_list, header_el)
                self._inc("dats_created")

            txn.commit()

        log.info(f"DATs gerados em: {out_dir}")

    @staticmethod
    def _write_dat(
        path: Path,
        machines: list[ET.Element],
        header: Optional[ET.Element],
    ) -> None:
        root = ET.Element("datafile")
        if header is not None:
            root.append(header)
        for m in machines:
            root.append(m)
        tree = ET.ElementTree(root)
        ET.indent(tree, space="\t")
        tree.write(path, encoding="utf-8", xml_declaration=True)
