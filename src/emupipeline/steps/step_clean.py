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

        print(f"\n  Encontrados {len(candidates)} arquivo(s) com WebP correspondente.")
        print(f"  Diretório: {source_dir}")
        print(f"\n  ⚠️  Esta operação é IRREVERSÍVEL.")

        if self._mode == ExecutionMode.DRY_RUN:
            print(f"\n  [DRY-RUN] Deletaria {len(candidates)} arquivo(s).")
            return

        if self._mode == ExecutionMode.AUDIT:
            for orig, webp in candidates:
                assert self._audit is not None
                self._audit.record(
                    step=self.name, action="delete_original",
                    source=str(orig), reason=f"WebP existe: {webp.name}",
                    would_delete=True,
                )
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
        """Retorna (original, webp) onde o WebP existe e é válido (> 50 bytes)."""
        result: list[tuple[Path, Path]] = []
        for orig in directory.rglob("*"):
            if orig.suffix.lower() not in self._src_exts:
                continue
            webp = orig.with_suffix(".webp")
            if webp.exists() and webp.stat().st_size > 50:
                result.append((orig, webp))
        return result

    def process_file(self, file_path: Path) -> str:
        # Não usado — este step tem lógica de batch em run()
        raise NotImplementedError
