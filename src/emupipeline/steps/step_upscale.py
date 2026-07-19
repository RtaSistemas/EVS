"""Step 7 — Upscaling com waifu2x / Real-ESRGAN + pós-processamento Pillow.
Herda BaseProcessor (arquitetura consistente).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.processor import BaseProcessor, WholeRunStep
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta


@register
class Upscaler(WholeRunStep):
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
        super().__init__("Upscaler", mode=mode, audit=audit)

    def run(self, **kwargs: Any) -> None:
        up_cfg = self.config.get("upscale")
        engine = getattr(up_cfg, "engine", None)

        if not engine:
            self.logger.error(
                "upscale.engine não configurado. "
                "Defina 'waifu2x' ou 'realesrgan' em config.yaml → upscale.engine"
            )
            return

        bin_attr = "bin_waifu2x" if engine == "waifu2x" else "bin_realesrgan"
        bin_path = self.config.get("paths", bin_attr)

        if not bin_path or not Path(str(bin_path)).exists():
            self.logger.error(f"Binário '{engine}' não encontrado: {bin_path}")
            self.logger.error(f"Configure paths.{bin_attr} no config.yaml")
            return

        src_dir = self._resolve_dir(self.config.get("paths", "upscale_input"), "Diretório de entrada (upscale_input)")
        out_dir = self.config.get("paths", "upscale_output")
        scale   = getattr(up_cfg, "scale",         2)
        workers = getattr(up_cfg, "workers",        2)
        fmt     = getattr(up_cfg, "output_format", "webp")
        post    = getattr(up_cfg, "post_process",  True)

        if src_dir is None:
            return

        images = [
            p for p in src_dir.rglob("*")
            if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
            and not str(p).startswith(str(out_dir))
        ]

        if not images:
            self.logger.info("Nenhuma imagem encontrada para upscaling.")
            return

        if self._mode == ExecutionMode.AUDIT:
            if not self._require_audit():
                return
            for img in images:
                self._audit.record(
                    step=self.name, action=f"upscale_{engine}",
                    source=str(img),
                    dest=str(Path(str(out_dir)) / img.name),
                    reason=f"x{scale} → {fmt}",
                )
            return

        if self._mode == ExecutionMode.DRY_RUN:
            self.logger.info(f"[DRY] Processaria {len(images)} imagens com {engine} x{scale}")
            return

        # NORMAL: cria diretório de saída e executa upscaler
        Path(str(out_dir)).mkdir(parents=True, exist_ok=True)

        self.logger.info(f"Upscaling {len(images)} imagens com {engine} x{scale}…")
        cmd = [
            str(bin_path), "-i", str(src_dir), "-o", str(out_dir),
            "-s", str(scale), "-f", fmt, "-j", f"1:{workers}:1",
        ]

        if self.run_subprocess(cmd, timeout=21600, src_name=engine):
            self.update_stat("processed", len(images))
        else:
            self.update_stat("error")
            return

        if post:
            unsharp = getattr(up_cfg, "unsharp", "0x1.0+1.0+0.02")
            self._apply_unsharp_pillow(Path(str(out_dir)), fmt, unsharp)

    def _apply_unsharp_pillow(self, out_dir: Path, fmt: str, spec: str) -> None:
        """Aplica unsharp mask via Pillow (elimina dependência do ImageMagick)."""
        try:
            from PIL import Image, ImageFilter
        except ImportError:
            self.logger.warning("Pillow não instalado — pós-processamento ignorado. pip install emupipeline[images]")
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
            self.logger.warning(
                f"Spec unsharp inválida {spec!r} — usando defaults (radius={radius}, "
                f"percent={percent}, threshold={threshold}). "
                "Formato esperado: RxSIGMA+AMOUNT+THRESH"
            )

        self.logger.info("Aplicando pós-processamento (unsharp mask via Pillow)…")
        errors = 0
        for img_path in out_dir.rglob(f"*.{fmt}"):
            try:
                with Image.open(img_path) as img:
                    sharpened = img.filter(ImageFilter.UnsharpMask(
                        radius=radius, percent=percent, threshold=threshold,
                    ))
                    sharpened.save(img_path)
            except Exception as exc:
                self.logger.warning(f"Unsharp falhou em {img_path.name}: {exc}")
                errors += 1

        processed = self.get_stats().get("processed", 0)
        self.update_stat("post_processed", max(0, processed - errors))
