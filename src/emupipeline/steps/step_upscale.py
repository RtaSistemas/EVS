"""Step 7 — Upscaling com waifu2x / Real-ESRGAN + pós-processamento ImageMagick."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.logger import setup_logger
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta

log = setup_logger("Upscaler")


@register
class Upscaler:
    meta = StepMeta(
        id="upscale_images",
        menu_number=7,
        label="Upscaling de imagens (waifu2x / Real-ESRGAN)",
        group="Imagens",
        description="Aumenta resolução de imagens com redes neurais.",
        pipeline_order=999,
    )

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        audit: Optional[AuditReport] = None,
    ) -> None:
        from emupipeline.core.config import cfg
        self._cfg   = cfg
        self._mode  = mode
        self._stats: dict[str, int] = {}

    def get_stats(self) -> dict[str, int]:
        return dict(self._stats)

    def run(self, **kwargs: Any) -> None:
        up_cfg = self._cfg.get("upscale")
        engine = getattr(up_cfg, "engine", None)

        if not engine:
            print("\n  Escolha o engine de upscaling:")
            print("  1. waifu2x-ncnn-vulkan (arte 2D, pixel art, retro)")
            print("  2. Real-ESRGAN (renders 3D, fotografias)")
            choice = input("  Opção (1/2): ").strip()
            engine = "waifu2x" if choice == "1" else "realesrgan"

        bin_attr = "bin_waifu2x" if engine == "waifu2x" else "bin_realesrgan"
        bin_path = self._cfg.get("paths", bin_attr)

        if not bin_path or not Path(str(bin_path)).exists():
            log.error(f"Binário '{engine}' não encontrado: {bin_path}")
            log.error(f"Configure paths.{bin_attr} no config.yaml")
            return

        src_dir = self._cfg.get("paths", "upscale_input")
        out_dir = self._cfg.get("paths", "upscale_output")
        scale   = getattr(up_cfg, "scale",         2)
        workers = getattr(up_cfg, "workers",        2)
        fmt     = getattr(up_cfg, "output_format", "webp")
        post    = getattr(up_cfg, "post_process",  True)

        if not src_dir or not Path(str(src_dir)).exists():
            log.error(f"Diretório de entrada não encontrado: {src_dir}")
            return

        Path(str(out_dir)).mkdir(parents=True, exist_ok=True)

        images = [
            p for p in Path(str(src_dir)).rglob("*")
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            and not str(p).startswith(str(out_dir))
        ]

        if not images:
            log.info("Nenhuma imagem encontrada para upscaling.")
            return

        if self._mode == ExecutionMode.DRY_RUN:
            log.info(f"[DRY] Processaria {len(images)} imagens com {engine} x{scale}")
            return

        log.info(f"Upscaling {len(images)} imagens com {engine} x{scale}…")
        cmd = [
            str(bin_path), "-i", str(src_dir), "-o", str(out_dir),
            "-s", str(scale), "-f", fmt, "-j", f"1:{workers}:1",
        ]

        try:
            subprocess.run(cmd, timeout=21600, check=True)
            self._stats["processed"] = len(images)
        except subprocess.CalledProcessError as exc:
            log.error(f"Upscaler falhou: {exc}")
            self._stats["error"] = 1
            return

        if post and shutil.which("magick"):
            unsharp = getattr(up_cfg, "unsharp", "0x1.0+1.0+0.02")
            log.info("Aplicando pós-processamento ImageMagick…")
            magick_errors = 0
            for img in Path(str(out_dir)).rglob(f"*.{fmt}"):
                try:
                    subprocess.run(
                        ["magick", str(img), "-unsharp", unsharp, str(img)],
                        capture_output=True,
                        check=True,
                    )
                except subprocess.CalledProcessError as exc:
                    log.warning(
                        f"ImageMagick falhou em {img.name}: "
                        f"{exc.stderr.decode(errors='replace').strip()}"
                    )
                    magick_errors += 1
            processed = self._stats.get("processed", 0)
            self._stats["post_processed"] = max(0, processed - magick_errors)
