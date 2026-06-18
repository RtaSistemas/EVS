"""
Step 6b — Limpeza de originais após conversão WebP.

Separado de WebPConverter (Single Responsibility):
  - WebPConverter TRANSFORMA (PNG → WebP)
  - OriginalCleaner DELETA (remove PNG quando WebP existe e é válido)

NUNCA incluído no pipeline automático (pipeline_order=999).
Requer confirmação explícita do usuário mesmo quando chamado via CLI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.processor import BaseProcessor
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta
from emupipeline.core.utils import is_valid_webp


@register
class OriginalCleaner(BaseProcessor):
    meta = StepMeta(
        id="clean_originals",
        menu_number=14,
        label="Limpar originais convertidos (requer confirmação)",
        group="Imagens",
        description="Remove PNG/JPG que já têm versão WebP válida. Irreversível.",
        pipeline_order=999,  # NUNCA no pipeline automático
    )

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        audit: Optional[AuditReport] = None,
    ) -> None:
        super().__init__("OriginalCleaner", mode=mode, audit=audit)
        self._src_exts: set[str] = {".png", ".jpg", ".jpeg", ".bmp"}

    def run(self, **kwargs: Any) -> None:
        source_dir = self.config.get("paths", "output_imgs")
        if not source_dir or not Path(source_dir).exists():
            self.logger.error(f"Diretório não encontrado: {source_dir}")
            return

        # Conta candidatos antes de pedir confirmação
        candidates = self._find_candidates(Path(source_dir))
        if not candidates:
            self.logger.info("Nenhum original com WebP correspondente encontrado.")
            return

        self.logger.info(f"Encontrados {len(candidates)} arquivo(s) com WebP correspondente.")
        self.logger.info(f"Diretório: {source_dir}")
        self.logger.warning("Esta operação é IRREVERSÍVEL.")

        if self._mode == ExecutionMode.DRY_RUN:
            self.logger.info(f"[DRY-RUN] Deletaria {len(candidates)} arquivo(s).")
            return

        if self._mode == ExecutionMode.AUDIT:
            if self._audit is None:
                self.logger.error("AUDIT mode requer AuditReport injetado no construtor.")
                return
            for orig, webp in candidates:
                self._audit.record(
                    step=self.name, action="delete_original",
                    source=str(orig), reason=f"WebP existe: {webp.name}",
                    would_delete=True,
                )
            return

        import sys
        if not sys.stdin.isatty():
            self.logger.error("Confirmação requerida mas stdin não é um terminal. Abortando.")
            return
        confirm = input("\n  Digite 'DELETAR' para confirmar: ").strip()
        if confirm != "DELETAR":
            self.logger.warning("Operação cancelada.")
            return

        for orig, _ in candidates:
            try:
                orig.unlink()
                self.update_stat("deleted")
            except OSError as exc:
                self.logger.error(f"Não foi possível deletar {orig.name}: {exc}")
                self.update_stat("error")

        stats = self.get_stats()
        self.logger.info(f"Deletados: {stats.get('deleted', 0)} | Erros: {stats.get('error', 0)}")

    def _find_candidates(self, directory: Path) -> list[tuple[Path, Path]]:
        """Retorna (original, webp) onde o WebP existe e é válido."""
        result: list[tuple[Path, Path]] = []
        for orig in directory.rglob("*"):
            if orig.suffix.lower() not in self._src_exts:
                continue
            webp = orig.with_suffix(".webp")
            if is_valid_webp(webp):
                result.append((orig, webp))
        return result

    def process_file(self, file_path: Path) -> str:
        """Deleta um original individualmente se WebP correspondente for válido."""
        if file_path.suffix.lower() not in self._src_exts:
            return "skipped_ext"
        webp = file_path.with_suffix(".webp")
        if not is_valid_webp(webp):
            return "no_webp"
        if self._mode == ExecutionMode.DRY_RUN:
            self.logger.debug(f"[DRY] deletaria {file_path.name}")
            return "dry_run"
        if self._mode == ExecutionMode.AUDIT:
            if self._audit is None:
                self.logger.error("AUDIT mode requer AuditReport injetado no construtor.")
                return "error"
            self._audit.record(
                step=self.name, action="delete_original",
                source=str(file_path), reason=f"WebP existe: {webp.name}",
                would_delete=True,
            )
            return "audit_recorded"
        try:
            file_path.unlink()
            return "deleted"
        except OSError as exc:
            self.logger.error(f"Erro ao deletar {file_path.name}: {exc}")
            return "error"
