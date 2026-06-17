"""
Testes para StagingTransaction e atomic_write.

Garantem que operações destrutivas são atômicas
e que falhas não corrompem o destino.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from emupipeline.core.transaction import StagingTransaction, atomic_write


class TestStagingTransaction:
    def test_commit_moves_files_to_dest(self, tmp_path):
        dest = tmp_path / "dest"
        dest.mkdir()

        with StagingTransaction(dest) as txn:
            p = txn.stage_path("output.txt")
            p.write_text("hello")
            txn.commit()

        assert (dest / "output.txt").exists()
        assert (dest / "output.txt").read_text() == "hello"

    def test_rollback_on_exception_leaves_dest_clean(self, tmp_path):
        dest = tmp_path / "dest"
        dest.mkdir()

        with pytest.raises(ValueError):
            with StagingTransaction(dest) as txn:
                p = txn.stage_path("output.txt")
                p.write_text("partial")
                raise ValueError("Erro simulado")

        # Destino não deve conter o arquivo parcial
        assert not (dest / "output.txt").exists()

    def test_staging_dir_cleaned_after_commit(self, tmp_path):
        dest = tmp_path / "dest"
        dest.mkdir()

        with StagingTransaction(dest) as txn:
            staging_dir = txn._staging
            txn.stage_path("f.txt").write_text("x")
            txn.commit()

        # Diretório de staging deve ter sido removido
        assert staging_dir is None or not staging_dir.exists()

    def test_staging_dir_cleaned_after_rollback(self, tmp_path):
        dest = tmp_path / "dest"
        dest.mkdir()

        with pytest.raises(RuntimeError):
            with StagingTransaction(dest) as txn:
                staging_dir = txn._staging
                txn.stage_path("f.txt").write_text("x")
                raise RuntimeError("forçado")

        assert staging_dir is None or not staging_dir.exists()

    def test_multiple_files_committed_atomically(self, tmp_path):
        dest = tmp_path / "dest"
        dest.mkdir()

        with StagingTransaction(dest) as txn:
            for i in range(5):
                txn.stage_path(f"file_{i}.txt").write_text(f"content_{i}")
            txn.commit()

        assert len(list(dest.glob("file_*.txt"))) == 5

    def test_empty_staged_file_raises_on_commit(self, tmp_path):
        dest = tmp_path / "dest"
        dest.mkdir()

        with pytest.raises(ValueError, match="vazio"):
            with StagingTransaction(dest) as txn:
                p = txn.stage_path("empty.txt")
                p.write_bytes(b"")   # arquivo vazio
                txn.commit()

    def test_missing_staged_file_skipped_silently(self, tmp_path):
        """Se o arquivo staged não existir, commit pula sem erro."""
        dest = tmp_path / "dest"
        dest.mkdir()

        with StagingTransaction(dest) as txn:
            txn.stage_path("ghost.txt")   # registra mas não cria
            txn.commit()

        assert not (dest / "ghost.txt").exists()

    def test_dest_dir_created_if_not_exists(self, tmp_path):
        dest = tmp_path / "new" / "nested" / "dest"

        with StagingTransaction(dest) as txn:
            txn.stage_path("f.txt").write_text("x")
            txn.commit()

        assert dest.exists()
        assert (dest / "f.txt").exists()


class TestAtomicWrite:
    def test_file_created_on_success(self, tmp_path):
        dest = tmp_path / "result.txt"

        with atomic_write(dest) as tmp:
            tmp.write_text("content")

        assert dest.exists()
        assert dest.read_text() == "content"

    def test_dest_not_created_on_exception(self, tmp_path):
        dest = tmp_path / "result.txt"

        with pytest.raises(RuntimeError):
            with atomic_write(dest) as tmp:
                tmp.write_text("partial")
                raise RuntimeError("Erro no meio")

        assert not dest.exists()

    def test_tmp_file_cleaned_on_exception(self, tmp_path):
        dest = tmp_path / "result.txt"
        captured_tmp = []

        with pytest.raises(RuntimeError):
            with atomic_write(dest) as tmp:
                captured_tmp.append(tmp)
                raise RuntimeError("falha")

        assert not captured_tmp[0].exists()

    def test_overwrites_existing_destination(self, tmp_path):
        dest = tmp_path / "result.txt"
        dest.write_text("old content")

        with atomic_write(dest) as tmp:
            tmp.write_text("new content")

        assert dest.read_text() == "new content"
