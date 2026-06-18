"""
Testes para WebPConverter.

Foco em: atomic_write, integridade, ExecutionMode, separação de deleção.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.steps.step_convert import WebPConverter


class TestWebPConverter:
    def test_skips_existing_webp(self, config_factory, tmp_project):
        config_factory()
        img = tmp_project / "source" / "images" / "test.png"
        img.write_bytes(b"fake_png")
        webp = img.with_suffix(".webp")
        webp.write_bytes(b"already_exists")

        converter = WebPConverter(mode=ExecutionMode.NORMAL)
        result = converter.process_file(img)
        assert result == "skipped_exists"

    def test_dry_run_returns_dry_run_status(self, config_factory, tmp_project):
        config_factory()
        img = tmp_project / "source" / "images" / "test.png"
        img.write_bytes(b"fake_png")

        converter = WebPConverter(mode=ExecutionMode.DRY_RUN)
        result = converter.process_file(img)
        assert result == "dry_run"
        assert not img.with_suffix(".webp").exists()

    def test_audit_records_operation(self, config_factory, tmp_project):
        config_factory()
        img = tmp_project / "source" / "images" / "test.png"
        img.write_bytes(b"fake_png")
        audit = AuditReport()

        converter = WebPConverter(mode=ExecutionMode.AUDIT, audit=audit)
        result = converter.process_file(img)
        assert result == "audit_recorded"
        assert audit.total == 1
        entry = audit.entries()[0]
        assert entry.action == "convert_to_webp"
        assert "test.png" in entry.source

    def test_does_not_delete_original(self, config_factory, tmp_project):
        """WebPConverter NÃO deve deletar o original (responsabilidade do OriginalCleaner)."""
        pytest.importorskip("PIL", reason="Pillow não instalado")
        config_factory()
        from PIL import Image

        img = tmp_project / "source" / "images" / "test.png"
        img.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (10, 10), color="red").save(img, "PNG")

        converter = WebPConverter(mode=ExecutionMode.NORMAL)
        converter.process_file(img)

        assert img.exists(), "WebPConverter deletou o original — violação de responsabilidade única!"

    def test_missing_pillow_returns_error(self, config_factory, tmp_project):
        config_factory()
        img = tmp_project / "source" / "images" / "test.png"
        img.write_bytes(b"fake_png")

        # Instancia o converter antes de suprimir PIL (para não afetar __init__)
        converter = WebPConverter(mode=ExecutionMode.NORMAL)

        # Suprime PIL apenas durante process_file — evita interferir com outros imports
        with patch.dict("sys.modules", {"PIL": None, "PIL.Image": None}):
            result = converter.process_file(img)
        assert result == "error"


class TestOriginalCleaner:
    def test_finds_originals_with_webp_pair(self, config_factory, tmp_project):
        config_factory()
        from emupipeline.steps.step_clean import OriginalCleaner

        imgs_dir = tmp_project / "output" / "images"
        imgs_dir.mkdir(parents=True, exist_ok=True)

        png = imgs_dir / "sf2.png"
        png.write_bytes(b"fake_png_content")
        webp = imgs_dir / "sf2.webp"
        webp.write_bytes(b"fake_webp_content" * 10)  # > 50 bytes

        cleaner = OriginalCleaner(mode=ExecutionMode.NORMAL)
        candidates = cleaner._find_candidates(imgs_dir)
        assert len(candidates) == 1
        assert candidates[0][0] == png

    def test_ignores_webp_too_small(self, config_factory, tmp_project):
        config_factory()
        from emupipeline.steps.step_clean import OriginalCleaner

        imgs_dir = tmp_project / "output" / "images"
        imgs_dir.mkdir(parents=True, exist_ok=True)

        png = imgs_dir / "sf2.png"
        png.write_bytes(b"fake")
        webp = imgs_dir / "sf2.webp"
        webp.write_bytes(b"tiny")  # < 50 bytes — suspeito

        cleaner = OriginalCleaner()
        candidates = cleaner._find_candidates(imgs_dir)
        assert len(candidates) == 0

    def test_audit_records_deletions_as_destructive(self, config_factory, tmp_project):
        config_factory()
        from emupipeline.steps.step_clean import OriginalCleaner

        imgs_dir = tmp_project / "output" / "images"
        imgs_dir.mkdir(parents=True, exist_ok=True)
        (imgs_dir / "sf2.png").write_bytes(b"x" * 100)
        (imgs_dir / "sf2.webp").write_bytes(b"w" * 100)

        audit = AuditReport()
        cleaner = OriginalCleaner(mode=ExecutionMode.AUDIT, audit=audit)
        cleaner.run()

        assert audit.destructive_count == 1

    def test_dry_run_does_not_delete(self, config_factory, tmp_project):
        config_factory()
        from emupipeline.steps.step_clean import OriginalCleaner

        imgs_dir = tmp_project / "output" / "images"
        imgs_dir.mkdir(parents=True, exist_ok=True)
        png = imgs_dir / "sf2.png"
        png.write_bytes(b"x" * 100)
        (imgs_dir / "sf2.webp").write_bytes(b"w" * 100)

        cleaner = OriginalCleaner(mode=ExecutionMode.DRY_RUN)
        cleaner.run()

        assert png.exists()  # não deletado
