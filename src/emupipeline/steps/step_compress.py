"""
Step 12 — Compressão de ROMs por sistema (CHD / RVZ / CSO).

Replica o comportamento do EmuDeck: detecta o sistema pelo nome do
subdiretório em paths.input_roms e converte para o formato comprimido
adequado usando chdman, DolphinTool ou maxcso.

Sistemas suportados
-------------------
CHD  : ps1 / psx / ps2 / dreamcast / saturn / segacd / 3do / neogeocd /
       pcenginecd / cd32
RVZ  : gamecube / wii
CSO  : psp

Configuração (config.yaml → seção compress)
--------------------------------------------
compress:
  delete_original: false        # apaga original após sucesso
  output_dir: ""                # "" = in-place; caminho = diretório separado
  chdman_bin:  "chdman"
  dolphin_bin: "DolphinTool"
  maxcso_bin:  "maxcso"
  rvz_compression: "zstd"       # zstd | bzip2 | lzma | lzma2 | none
  rvz_level: 5                  # 1–9
  psp_format: "cso"             # cso | zso
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.processor import BaseProcessor
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta

# Sistema → (formato_saída, extensões_de_entrada_aceitas)
_SYSTEM_MAP: dict[str, tuple[str, list[str]]] = {
    # CHD — imagens de CD/DVD
    "ps1":        ("chd", [".iso", ".bin", ".cue", ".img", ".mdf", ".pbp"]),
    "psx":        ("chd", [".iso", ".bin", ".cue"]),
    "ps2":        ("chd", [".iso"]),
    "dreamcast":  ("chd", [".gdi", ".cdi", ".iso"]),
    "saturn":     ("chd", [".iso", ".bin", ".cue"]),
    "segacd":     ("chd", [".iso", ".bin", ".cue"]),
    "3do":        ("chd", [".iso", ".bin", ".cue"]),
    "neogeocd":   ("chd", [".iso", ".bin", ".cue"]),
    "pcenginecd": ("chd", [".iso", ".bin", ".cue"]),
    "cd32":       ("chd", [".iso", ".bin", ".cue"]),
    # RVZ — GameCube / Wii
    "gamecube":   ("rvz", [".iso", ".gcm", ".gcz"]),
    "wii":        ("rvz", [".iso", ".wbfs", ".gcz"]),
    # CSO / ZSO — PSP
    "psp":        ("cso", [".iso"]),
}


@register
class RomCompressor(BaseProcessor):
    meta = StepMeta(
        id="compress_roms",
        menu_number=12,
        label="Comprimir ROMs (CHD/RVZ/CSO)",
        group="ROMs & DATs",
        description=(
            "Converte ROMs para formatos comprimidos por sistema: "
            "CHD (PS1/PS2/Dreamcast…), RVZ (GameCube/Wii), CSO (PSP)."
        ),
        pipeline_order=25,
    )

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        audit: AuditReport | None = None,
    ) -> None:
        super().__init__("RomCompressor", mode=mode, audit=audit)

    def process_file(self, file_path: Path) -> str:
        return "not_applicable"

    def run(self, **kwargs: Any) -> None:
        compress_cfg    = self.config.get("compress")
        delete_original = getattr(compress_cfg, "delete_original",  False)
        output_dir_raw  = str(getattr(compress_cfg, "output_dir",   ""))
        chdman_bin      = str(getattr(compress_cfg, "chdman_bin",   "chdman"))
        dolphin_bin     = str(getattr(compress_cfg, "dolphin_bin",  "DolphinTool"))
        maxcso_bin      = str(getattr(compress_cfg, "maxcso_bin",   "maxcso"))
        rvz_compression = str(getattr(compress_cfg, "rvz_compression", "zstd"))
        rvz_level       = int(getattr(compress_cfg, "rvz_level",    5))
        psp_format      = str(getattr(compress_cfg, "psp_format",   "cso"))

        input_roms = Path(str(self.config.get("paths", "input_roms")))
        if not input_roms.exists():
            self.logger.error(f"Diretório de ROMs não encontrado: {input_roms}")
            return

        # Verifica quais binários estão disponíveis
        available: dict[str, str | None] = {
            "chd": shutil.which(chdman_bin),
            "rvz": shutil.which(dolphin_bin),
            "cso": shutil.which(maxcso_bin),
        }

        for sys_dir in sorted(input_roms.iterdir()):
            if not sys_dir.is_dir():
                continue

            system_name = sys_dir.name.lower()
            if system_name not in _SYSTEM_MAP:
                continue

            fmt, src_exts = _SYSTEM_MAP[system_name]

            if not available[fmt]:
                self.logger.warning(
                    f"Binário para {fmt.upper()} não encontrado ({chdman_bin if fmt == 'chd' else dolphin_bin if fmt == 'rvz' else maxcso_bin}). "
                    f"Pulando sistema: {system_name}"
                )
                self.update_stat("skipped_no_bin")
                continue

            out_base: Path = (
                Path(output_dir_raw) / sys_dir.name if output_dir_raw
                else sys_dir
            )

            for rom_file in sorted(sys_dir.rglob("*")):
                if not rom_file.is_file():
                    continue
                if rom_file.suffix.lower() not in src_exts:
                    continue
                # BIN sem CUE companheiro: aceita. BIN com CUE: será processado pelo CUE
                if rom_file.suffix.lower() == ".bin" and rom_file.with_suffix(".cue").exists():
                    continue

                dest = (out_base / rom_file.relative_to(sys_dir)).with_suffix(f".{fmt}")

                if dest.exists():
                    self.update_stat("skipped_exists")
                    continue

                if self._mode == ExecutionMode.AUDIT:
                    if self._audit is None:
                        self.logger.error("AUDIT mode requer AuditReport injetado no construtor.")
                        return
                    self._audit.record(
                        step=self.name,
                        action=f"compress_{fmt}",
                        source=str(rom_file),
                        dest=str(dest),
                        reason=f"sistema={system_name}",
                    )
                    self.update_stat("audit_recorded")
                    continue

                if self._mode == ExecutionMode.DRY_RUN:
                    self.logger.info(f"[DRY] {fmt.upper()}: {rom_file.name} → {dest.name}")
                    self.update_stat("dry_run")
                    continue

                # NORMAL — cria diretório de saída somente quando necessário
                if output_dir_raw:
                    dest.parent.mkdir(parents=True, exist_ok=True)

                success = self._compress(
                    fmt=fmt,
                    src=rom_file,
                    dest=dest,
                    bin_path=available[fmt],  # type: ignore[arg-type]
                    rvz_compression=rvz_compression,
                    rvz_level=rvz_level,
                    psp_format=psp_format,
                )

                if success:
                    self.update_stat("compressed")
                    if delete_original:
                        self._delete_originals(rom_file)
                else:
                    self.update_stat("error")

        compressed = self.get_stats().get("compressed", 0)
        self.logger.info(f"ROMs comprimidas: {compressed}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compress(
        self,
        fmt: str,
        src: Path,
        dest: Path,
        bin_path: str,
        rvz_compression: str,
        rvz_level: int,
        psp_format: str,
    ) -> bool:
        """Chama a ferramenta de compressão. Retorna True em caso de sucesso."""
        try:
            cmd = self._build_cmd(fmt, src, dest, bin_path, rvz_compression, rvz_level, psp_format)
            if cmd is None:
                return False

            self.logger.info(f"Comprimindo [{fmt.upper()}]: {src.name} → {dest.name}")
            result = subprocess.run(
                cmd, timeout=3600, text=True, capture_output=True,
            )
            if result.returncode != 0:
                self.logger.error(
                    f"Falha ao comprimir {src.name} (código {result.returncode}):\n"
                    f"{result.stderr[-400:]}"
                )
                if dest.exists():
                    dest.unlink()
                return False
            return True

        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout ao comprimir: {src.name}")
            if dest.exists():
                dest.unlink()
            return False
        except FileNotFoundError as exc:
            self.logger.error(f"Binário não encontrado durante execução: {exc}")
            return False
        except Exception as exc:
            self.logger.error(f"Erro inesperado ao comprimir {src.name}: {exc}")
            return False

    def _build_cmd(
        self,
        fmt: str,
        src: Path,
        dest: Path,
        bin_path: str,
        rvz_compression: str,
        rvz_level: int,
        psp_format: str,
    ) -> list[str] | None:
        """Constrói o comando de compressão para o formato solicitado."""
        if fmt == "chd":
            # CUE ou GDI como entry-point quando BIN/track-files acompanham
            input_file = src
            if src.suffix.lower() == ".bin":
                cue = src.with_suffix(".cue")
                if cue.exists():
                    input_file = cue
            return [bin_path, "createcd", "-i", str(input_file), "-o", str(dest)]

        if fmt == "rvz":
            return [
                bin_path, "convert",
                "-f", "rvz",
                "-c", rvz_compression,
                "-l", str(rvz_level),
                "-i", str(src),
                "-o", str(dest),
            ]

        if fmt == "cso":
            if psp_format == "zso":
                return [bin_path, "--zst", str(src), "-o", str(dest)]
            return [bin_path, str(src), "-o", str(dest)]

        self.logger.error(f"Formato de compressão desconhecido: {fmt}")
        return None

    def _delete_originals(self, src: Path) -> None:
        """
        Apaga o arquivo original e companions (BINs de um CUE, tracks de um GDI).
        """
        companions: list[Path] = [src]

        if src.suffix.lower() == ".cue":
            # Lê o CUE e extrai FILE "nome.bin" ...
            for line in src.read_text(errors="ignore").splitlines():
                stripped = line.strip()
                if stripped.upper().startswith("FILE"):
                    parts = stripped.split('"')
                    if len(parts) >= 2:
                        companion = src.parent / parts[1]
                        if companion.exists() and companion not in companions:
                            companions.append(companion)

        elif src.suffix.lower() == ".gdi":
            # GDI: cada linha tem track_num lba type sector_size filename flags
            for line in src.read_text(errors="ignore").splitlines():
                parts = line.split()
                if len(parts) >= 5:
                    track = src.parent / parts[4]
                    if track.exists() and track not in companions:
                        companions.append(track)

        for f in companions:
            try:
                f.unlink()
                self.logger.debug(f"Removido original: {f.name}")
            except OSError as exc:
                self.logger.warning(f"Não foi possível remover {f.name}: {exc}")
