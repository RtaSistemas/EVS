"""
Utilitários compartilhados entre steps.

Funções e constantes que aparecem em dois ou mais módulos ficam aqui
para garantir fonte única de verdade.
"""

from __future__ import annotations

from pathlib import Path

# Tamanho mínimo em bytes para considerar um WebP como válido.
# Usado por WebPConverter (integridade pós-conversão) e
# OriginalCleaner (validação antes de deletar o original).
MIN_WEBP_BYTES: int = 50


def is_valid_webp(path: Path) -> bool:
    """Retorna True se o arquivo WebP existe e tem tamanho mínimo aceitável."""
    return path.exists() and path.stat().st_size >= MIN_WEBP_BYTES
