"""Step 7 — Upscaling com waifu2x / Real-ESRGAN + pós-processamento Pillow."""

from __future__ import annotations

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
            log.error(
                "upscale.engine não configurado. "
                "Defina 'waifu2x' ou 'realesrgan' em config.yaml → upscale.engine"
            )
            return

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

        if post:
            unsharp = getattr(up_cfg, "unsharp", "0x1.0+1.0+0.02")
            self._apply_unsharp_pillow(Path(str(out_dir)), fmt, unsharp)

    def _apply_unsharp_pillow(self, out_dir: Path, fmt: str, spec: str) -> None:
        """Aplica unsharp mask via Pillow (elimina dependência do ImageMagick)."""
        try:
            from PIL import Image, ImageFilter
        except ImportError:
            log.warning("Pillow não instalado — pós-processamento ignorado. pip install emupipeline[images]")
            return

        # Converte spec ImageMagick "{r}x{sigma}+{amount}+{thresh}" → params Pillow
        radius, percent, threshold = 2, 100, 5
        try:
            parts = spec.replace("x", "+").split("+")
            if len(parts) >= 3:
                sigma  = float(parts[1])
                amount = float(parts[2])
                thresh = float(parts[3]) if len(parts) > 3 else 0.02
                radius    = max(1, round(sigma * 2))
                percent   = round(amount * 100)
                threshold = min(255, round(thresh * 255))
        except (ValueError, IndexError):
            pass

        log.info("Aplicando pós-processamento (unsharp mask via Pillow)…")
        errors = 0
        for img_path in out_dir.rglob(f"*.{fmt}"):
            try:
                with Image.open(img_path) as img:
                    sharpened = img.filter(ImageFilter.UnsharpMask(
                        radius=radius, percent=percent, threshold=threshold,
                    ))
                    sharpened.save(img_path)
            except Exception as exc:
                log.warning(f"Unsharp falhou em {img_path.name}: {exc}")
                errors += 1

        processed = self._stats.get("processed", 0)
        self._stats["post_processed"] = max(0, processed - errors)
