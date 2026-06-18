"""
Step 6 — Conversão PNG/JPG → WebP.

Responsabilidade ÚNICA: converter imagens. Não deleta nada.
A deleção dos originais é responsabilidade de OriginalCleaner (step_clean.py),
executado separadamente após confirmação explícita.

Mudanças v5:
  - ProcessPoolExecutor: PIL libera GIL mas contorna limitações com processos
  - atomic_write: WebP só existe se conversão 100% bem-sucedida
  - delete_original REMOVIDO deste step (Single Responsibility)
  - ExecutionMode: dry_run e audit
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.processor import BaseProcessor, ExecutorType
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta
from emupipeline.core.transaction import atomic_write
from emupipeline.core.utils import MIN_WEBP_BYTES


@register
class WebPConverter(BaseProcessor):
    meta = StepMeta(
        id="convert_webp",
        menu_number=6,
        label="Converter imagens → WebP",
        group="Imagens",
        description="Converte PNG/JPG para WebP. Não remove originais.",
        pipeline_order=60,
    )

    # Processos separados garantem paralelismo real para PIL (contorna GIL)
    _executor_type = ExecutorType.PROCESS

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        audit: Optional[AuditReport] = None,
    ) -> None:
        super().__init__("WebPConverter", mode=mode, audit=audit)
        self.quality = self.config.get("webp", "quality") or 85
        self._src_exts: set[str] = set(
            self.config.get("webp", "source_extensions") or [".png", ".jpg", ".jpeg", ".bmp"]
        )
        self._source_dir: Optional[Path] = None

    def run(self, **kwargs: Any) -> None:
        source_dir = self.config.get("paths", "output_imgs")
        if not source_dir or not Path(source_dir).exists():
            self.logger.error(f"Diretório de imagens não encontrado: {source_dir}")
            return
        self._source_dir = Path(source_dir)
        files = self.scan(self._source_dir, extensions=self._src_exts)
        self.run_parallel(files)

    def process_file(self, file_path: Path) -> str:
        dest = file_path.with_suffix(".webp")

        if dest.exists():
            return "skipped_exists"

        if self._mode == ExecutionMode.AUDIT:
            if self._audit is None:
                self.logger.error("AUDIT mode requer AuditReport injetado no construtor.")
                return "error"
            self._audit.record(
                step=self.name, action="convert_to_webp",
                source=str(file_path), dest=str(dest),
                reason=f"{file_path.suffix.upper()} → WebP q={self.quality}",
            )
            return "audit_recorded"

        if self._mode == ExecutionMode.DRY_RUN:
            self.logger.debug(f"[DRY] Converteria: {file_path.name}")
            return "dry_run"

        try:
            from PIL import Image
        except ImportError:
            self.logger.error("Pillow não instalado. Execute: pip install emupipeline[images]")
            return "error"

        try:
            with atomic_write(dest) as tmp:
                with Image.open(file_path) as img:
                    # Converte RGBA→RGB se necessário (WebP suporta, mas evita problemas)
                    if img.mode in ("RGBA", "LA"):
                        bg = Image.new("RGB", img.size, (255, 255, 255))
                        if img.mode == "RGBA":
                            bg.paste(img, mask=img.split()[3])
                        else:
                            bg.paste(img)
                        img = bg
                    elif img.mode not in ("RGB", "L"):
                        img = img.convert("RGB")
                    img.save(tmp, "WEBP", quality=self.quality, method=4)

            # Verificação de integridade mínima
            if dest.stat().st_size < MIN_WEBP_BYTES:
                dest.unlink(missing_ok=True)
                self.logger.warning(f"WebP suspeito (< {MIN_WEBP_BYTES} bytes): {file_path.name} — original preservado")
                return "error"

            return "converted"

        except Exception as exc:
            self.logger.error(f"Erro ao converter {file_path.name}: {exc}")
            dest.unlink(missing_ok=True)
            return "error"
