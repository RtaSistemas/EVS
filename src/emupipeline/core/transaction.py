"""
Isolamento transacional para operações de escrita.

Dois mecanismos:

  StagingTransaction  → múltiplos arquivos escritos em staging,
                        commit atômico move todos para destino.
                        Falha = rollback automático, destino intocado.

  atomic_write()      → context manager para arquivo único,
                        mais simples quando só um arquivo é gerado.

Limitação: rename atômico só funciona no mesmo filesystem.
Cross-device (ex: staging em /tmp, destino em /mnt/externo) usa
cópia + verificação + deleção como fallback.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


class StagingTransaction:
    """
    Gerencia staging para um conjunto de arquivos.

    Uso:
        with StagingTransaction(dest_dir) as txn:
            tmp = txn.stage_path("video.mp4")
            # escreve em tmp
            txn.commit()
        # Se não chamar commit() ou ocorrer exceção → rollback automático
    """

    def __init__(self, dest_dir: Path, verify_nonempty: bool = True) -> None:
        self._dest_dir = dest_dir
        self._verify = verify_nonempty
        self._staging: Path | None = None
        self._staged: list[tuple[Path, Path]] = []  # (staged, final)
        self._committed = False

    def __enter__(self) -> "StagingTransaction":
        self._dest_dir.mkdir(parents=True, exist_ok=True)
        self._staging = Path(
            tempfile.mkdtemp(prefix=".txn_", dir=self._dest_dir)
        )
        return self

    def __exit__(self, exc_type: type | None, *_: object) -> bool:
        if not self._committed:
            self.rollback()
        return False  # não suprime exceções

    def stage_path(self, filename: str) -> Path:
        """Retorna caminho dentro do staging para escrita."""
        assert self._staging is not None
        staged = self._staging / filename
        final = self._dest_dir / filename
        self._staged.append((staged, final))
        return staged

    def commit(self) -> None:
        """Move todos arquivos staged para destino final."""
        assert self._staging is not None

        for staged, final in self._staged:
            if not staged.exists():
                continue
            if self._verify and staged.stat().st_size == 0:
                raise ValueError(f"Arquivo staged vazio, abortando commit: {staged.name}")
            try:
                staged.replace(final)          # atômico no mesmo fs
            except OSError:
                shutil.copy2(staged, final)    # cross-device fallback
                staged.unlink()

        self._committed = True
        self._cleanup()

    def rollback(self) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        if self._staging and self._staging.exists():
            shutil.rmtree(self._staging, ignore_errors=True)
        self._staging = None


@contextmanager
def atomic_write(dest_path: Path) -> Generator[Path, None, None]:
    """
    Context manager para escrita atômica de arquivo único.

    Uso:
        with atomic_write(output / "result.mp4") as tmp:
            run_ffmpeg(..., output=str(tmp))
        # dest_path só existe após saída sem exceção
    """
    import os
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(
        dir=dest_path.parent,
        prefix=f".tmp_{dest_path.stem}_",
        suffix=dest_path.suffix,
    )
    tmp = Path(tmp_str)
    os.close(fd)
    try:
        yield tmp
        tmp.replace(dest_path)     # atômico no mesmo fs
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
