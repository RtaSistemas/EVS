"""
Testes para WebPConverter.

Foco em: atomic_write, integridade, ExecutionMode, separação de deleção.
"""

from __future__ import annotations

from unittest.mock import patch

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

    def test_audit_without_report_returns_error(self, config_factory, tmp_project):
        """AUDIT sem AuditReport injetado retorna 'error' em vez de crash."""
        config_factory()
        img = tmp_project / "source" / "images" / "test.png"
        img.write_bytes(b"fake_png")

        converter = WebPConverter(mode=ExecutionMode.AUDIT, audit=None)
        result = converter.process_file(img)
        assert result == "error"

    def test_conversion_exception_returns_error(self, config_factory, tmp_project):
        """Exceção durante conversão retorna 'error' e não deixa arquivo corrompido."""
        pytest.importorskip("PIL", reason="Pillow não instalado")
        config_factory()
        img = tmp_project / "source" / "images" / "test.png"
        img.write_bytes(b"not_a_valid_png")

        converter = WebPConverter(mode=ExecutionMode.NORMAL)
        result = converter.process_file(img)
        assert result == "error"
        assert not img.with_suffix(".webp").exists()

    def test_rgba_image_converts_without_error(self, config_factory, tmp_project):
        """Imagem RGBA deve ser convertida sem erro (composite em fundo branco)."""
        pytest.importorskip("PIL", reason="Pillow não instalado")
        from PIL import Image

        config_factory()
        img = tmp_project / "source" / "images" / "test.png"
        img.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (10, 10), (255, 0, 0, 128)).save(img, "PNG")

        converter = WebPConverter(mode=ExecutionMode.NORMAL)
        result = converter.process_file(img)
        assert result == "converted"
        assert img.with_suffix(".webp").exists()


class TestOriginalCleanerRun:
    def test_run_missing_dir_returns_early(self, config_factory, tmp_project):
        """run() com diretório inexistente retorna sem crash."""
        import shutil

        config_factory()
        from emupipeline.steps.step_clean import OriginalCleaner

        # Remove o diretório de output/images para forçar o early return
        shutil.rmtree(tmp_project / "output" / "images", ignore_errors=True)

        cleaner = OriginalCleaner(mode=ExecutionMode.NORMAL)
        cleaner.run()  # não deve levantar exceção
        assert cleaner.get_stats() == {}

    def test_run_no_candidates_returns_early(self, config_factory, tmp_project):
        """run() sem candidatos (sem WebP correspondente) retorna sem fazer nada."""
        config_factory()
        from emupipeline.steps.step_clean import OriginalCleaner

        imgs = tmp_project / "output" / "images"
        imgs.mkdir(parents=True, exist_ok=True)
        (imgs / "sf2.png").write_bytes(b"only_png_no_webp")

        cleaner = OriginalCleaner(mode=ExecutionMode.NORMAL)
        cleaner.run()
        assert cleaner.get_stats().get("deleted", 0) == 0

    def test_run_user_cancels_preserves_files(self, config_factory, tmp_project):
        """Quando usuário digita algo diferente de 'DELETAR', arquivos são preservados."""
        config_factory()
        from unittest.mock import patch

        from emupipeline.steps.step_clean import OriginalCleaner

        imgs = tmp_project / "output" / "images"
        imgs.mkdir(parents=True, exist_ok=True)
        png = imgs / "sf2.png"
        png.write_bytes(b"x" * 100)
        (imgs / "sf2.webp").write_bytes(b"w" * 100)

        cleaner = OriginalCleaner(mode=ExecutionMode.NORMAL)
        with patch("sys.stdin.isatty", return_value=True), \
             patch("builtins.input", return_value="nao"):
            cleaner.run()

        assert png.exists()


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

    def test_audit_without_report_returns_error(self, config_factory, tmp_project):
        """AUDIT sem AuditReport injetado retorna 'error' em vez de crash."""
        config_factory()
        from emupipeline.steps.step_clean import OriginalCleaner

        imgs_dir = tmp_project / "output" / "images"
        imgs_dir.mkdir(parents=True, exist_ok=True)
        (imgs_dir / "sf2.png").write_bytes(b"x" * 100)
        (imgs_dir / "sf2.webp").write_bytes(b"w" * 100)

        cleaner = OriginalCleaner(mode=ExecutionMode.AUDIT, audit=None)
        cleaner.run()  # não deve lançar exceção
        assert cleaner.get_stats().get("deleted", 0) == 0

    def test_aborts_in_non_interactive_environment(self, config_factory, tmp_project):
        """Em ambiente não-interativo (stdin não é tty), não deleta e aborta."""
        config_factory()
        from unittest.mock import patch  # noqa: PLC0415

        from emupipeline.steps.step_clean import OriginalCleaner

        imgs_dir = tmp_project / "output" / "images"
        imgs_dir.mkdir(parents=True, exist_ok=True)
        png = imgs_dir / "sf2.png"
        png.write_bytes(b"x" * 100)
        (imgs_dir / "sf2.webp").write_bytes(b"w" * 100)

        cleaner = OriginalCleaner(mode=ExecutionMode.NORMAL)
        with patch("sys.stdin.isatty", return_value=False):
            cleaner.run()

        assert png.exists()  # não deve ter sido deletado


class TestOriginalCleanerProcessFile:
    def test_skips_non_image_extension(self, config_factory, tmp_project):
        """Arquivos com extensão não suportada retornam 'skipped_ext'."""
        config_factory()
        from emupipeline.steps.step_clean import OriginalCleaner

        f = tmp_project / "output" / "images" / "sf2.webp"
        f.write_bytes(b"data")

        cleaner = OriginalCleaner(mode=ExecutionMode.NORMAL)
        assert cleaner.process_file(f) == "skipped_ext"

    def test_returns_no_webp_when_missing(self, config_factory, tmp_project):
        """Retorna 'no_webp' quando não há WebP correspondente."""
        config_factory()
        from emupipeline.steps.step_clean import OriginalCleaner

        f = tmp_project / "output" / "images" / "sf2.png"
        f.write_bytes(b"data")

        cleaner = OriginalCleaner(mode=ExecutionMode.NORMAL)
        assert cleaner.process_file(f) == "no_webp"

    def test_dry_run_does_not_delete_file(self, config_factory, tmp_project):
        """Em DRY_RUN, process_file não apaga o arquivo."""
        config_factory()
        from emupipeline.steps.step_clean import OriginalCleaner

        imgs = tmp_project / "output" / "images"
        imgs.mkdir(parents=True, exist_ok=True)
        png = imgs / "sf2.png"
        png.write_bytes(b"x" * 100)
        (imgs / "sf2.webp").write_bytes(b"w" * 100)

        cleaner = OriginalCleaner(mode=ExecutionMode.DRY_RUN)
        result = cleaner.process_file(png)
        assert result == "dry_run"
        assert png.exists()

    def test_audit_without_report_returns_error(self, config_factory, tmp_project):
        """process_file em AUDIT sem AuditReport retorna 'error'."""
        config_factory()
        from emupipeline.steps.step_clean import OriginalCleaner

        imgs = tmp_project / "output" / "images"
        imgs.mkdir(parents=True, exist_ok=True)
        png = imgs / "sf2.png"
        png.write_bytes(b"x" * 100)
        (imgs / "sf2.webp").write_bytes(b"w" * 100)

        cleaner = OriginalCleaner(mode=ExecutionMode.AUDIT, audit=None)
        result = cleaner.process_file(png)
        assert result == "error"

    def test_audit_records_deletion(self, config_factory, tmp_project):
        """process_file em AUDIT registra operação no AuditReport."""
        config_factory()
        from emupipeline.steps.step_clean import OriginalCleaner

        imgs = tmp_project / "output" / "images"
        imgs.mkdir(parents=True, exist_ok=True)
        png = imgs / "sf2.png"
        png.write_bytes(b"x" * 100)
        (imgs / "sf2.webp").write_bytes(b"w" * 100)

        audit = AuditReport()
        cleaner = OriginalCleaner(mode=ExecutionMode.AUDIT, audit=audit)
        result = cleaner.process_file(png)
        assert result == "audit_recorded"
        assert audit.total == 1
        assert audit.entries()[0].action == "delete_original"

    def test_normal_deletes_original(self, config_factory, tmp_project):
        """Em NORMAL com WebP válido, process_file deleta o original."""
        config_factory()
        from emupipeline.steps.step_clean import OriginalCleaner

        imgs = tmp_project / "output" / "images"
        imgs.mkdir(parents=True, exist_ok=True)
        png = imgs / "sf2.png"
        png.write_bytes(b"x" * 100)
        (imgs / "sf2.webp").write_bytes(b"w" * 100)

        cleaner = OriginalCleaner(mode=ExecutionMode.NORMAL)
        result = cleaner.process_file(png)
        assert result == "deleted"
        assert not png.exists()
