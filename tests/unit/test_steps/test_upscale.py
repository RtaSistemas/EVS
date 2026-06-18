"""
Testes para step_upscale (Upscaler).

Foco em:
  - Binário não encontrado → retorna early com log de erro
  - Sem imagens → retorna early sem chamar subprocess
  - Dry-run → não chama subprocess
  - Sucesso: subprocess chamado com args corretos, stats["processed"] setado
  - CalledProcessError → stats["error"] = 1
  - Pós-processamento Pillow: UnsharpMask chamado por imagem, erros individuais logados
  - Pillow ausente → post-processing ignorado com warning
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from emupipeline.core.execution_mode import ExecutionMode

# Caminho real que existe no Linux mas não é waifu2x (binary check passa)
_REAL_BIN = "/usr/bin/false"
# Caminho que definitivamente não existe
_FAKE_BIN = "/nonexistent/waifu2x_never_exists"


# ---------------------------------------------------------------------------
# Binário não encontrado
# ---------------------------------------------------------------------------

class TestBinaryNotFound:
    def test_missing_binary_does_not_call_subprocess(self, config_factory, tmp_project):
        config_factory({
            "upscale": {"engine": "waifu2x", "scale": 2,
                        "output_format": "webp", "workers": 1, "post_process": False},
            "paths": {"bin_waifu2x": _FAKE_BIN},
        })
        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler()

        with patch("emupipeline.steps.step_upscale.subprocess.run") as mock_run:
            upscaler.run()
            mock_run.assert_not_called()

    def test_missing_binary_error_stat_not_set(self, config_factory, tmp_project):
        config_factory({
            "upscale": {"engine": "realesrgan", "scale": 2,
                        "output_format": "webp", "workers": 1, "post_process": False},
            "paths": {"bin_realesrgan": _FAKE_BIN},
        })
        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler()
        upscaler.run()
        # binary não encontrado → retorna antes de marcar error
        assert upscaler.get_stats() == {}


# ---------------------------------------------------------------------------
# Sem imagens no diretório
# ---------------------------------------------------------------------------

class TestNoImages:
    def test_empty_directory_returns_early(self, config_factory, tmp_project):
        # source/images existe mas está vazio
        config_factory({
            "upscale": {"engine": "waifu2x", "scale": 2,
                        "output_format": "webp", "workers": 1, "post_process": False},
            "paths": {"bin_waifu2x": _REAL_BIN},
        })
        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler()

        with patch("emupipeline.steps.step_upscale.subprocess.run") as mock_run:
            upscaler.run()
            mock_run.assert_not_called()

    def test_empty_directory_leaves_stats_empty(self, config_factory, tmp_project):
        config_factory({
            "upscale": {"engine": "waifu2x", "scale": 2,
                        "output_format": "webp", "workers": 1, "post_process": False},
            "paths": {"bin_waifu2x": _REAL_BIN},
        })
        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler()
        upscaler.run()
        assert upscaler.get_stats() == {}


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_does_not_call_subprocess(self, config_factory, tmp_project):
        img = tmp_project / "source" / "images" / "sf2.png"
        img.write_bytes(b"PNG")

        config_factory({
            "upscale": {"engine": "waifu2x", "scale": 2,
                        "output_format": "webp", "workers": 1, "post_process": False},
            "paths": {"bin_waifu2x": _REAL_BIN},
        })
        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler(mode=ExecutionMode.DRY_RUN)

        with patch("emupipeline.steps.step_upscale.subprocess.run") as mock_run:
            upscaler.run()
            mock_run.assert_not_called()

    def test_dry_run_leaves_stats_empty(self, config_factory, tmp_project):
        img = tmp_project / "source" / "images" / "sf2.png"
        img.write_bytes(b"PNG")

        config_factory({
            "upscale": {"engine": "waifu2x", "scale": 2,
                        "output_format": "webp", "workers": 1, "post_process": False},
            "paths": {"bin_waifu2x": _REAL_BIN},
        })
        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler(mode=ExecutionMode.DRY_RUN)
        upscaler.run()
        stats = upscaler.get_stats()
        assert "processed" not in stats
        assert "error" not in stats


# ---------------------------------------------------------------------------
# Sucesso — subprocess chamado corretamente
# ---------------------------------------------------------------------------

class TestSuccessfulUpscale:
    def test_calls_subprocess_with_scale_arg(self, config_factory, tmp_project):
        img = tmp_project / "source" / "images" / "sf2.png"
        img.write_bytes(b"PNG")

        config_factory({
            "upscale": {"engine": "waifu2x", "scale": 4,
                        "output_format": "webp", "workers": 2, "post_process": False},
            "paths": {"bin_waifu2x": _REAL_BIN},
        })
        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler()

        with patch("emupipeline.steps.step_upscale.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            upscaler.run()

        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert "-s" in cmd
        assert "4" in cmd

    def test_calls_subprocess_with_format_arg(self, config_factory, tmp_project):
        img = tmp_project / "source" / "images" / "sf2.png"
        img.write_bytes(b"PNG")

        config_factory({
            "upscale": {"engine": "waifu2x", "scale": 2,
                        "output_format": "webp", "workers": 1, "post_process": False},
            "paths": {"bin_waifu2x": _REAL_BIN},
        })
        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler()

        with patch("emupipeline.steps.step_upscale.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            upscaler.run()

        cmd = mock_run.call_args[0][0]
        assert "-f" in cmd
        assert "webp" in cmd

    def test_processed_stat_set_on_success(self, config_factory, tmp_project):
        img = tmp_project / "source" / "images" / "sf2.png"
        img.write_bytes(b"PNG")

        config_factory({
            "upscale": {"engine": "waifu2x", "scale": 2,
                        "output_format": "webp", "workers": 1, "post_process": False},
            "paths": {"bin_waifu2x": _REAL_BIN},
        })
        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler()

        with patch("emupipeline.steps.step_upscale.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            upscaler.run()

        assert upscaler.get_stats().get("processed", 0) >= 1

    def test_uses_realesrgan_bin_when_engine_is_realesrgan(self, config_factory, tmp_project):
        img = tmp_project / "source" / "images" / "sf2.png"
        img.write_bytes(b"PNG")

        config_factory({
            "upscale": {"engine": "realesrgan", "scale": 2,
                        "output_format": "webp", "workers": 1, "post_process": False},
            "paths": {"bin_realesrgan": _REAL_BIN},
        })
        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler()

        with patch("emupipeline.steps.step_upscale.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            upscaler.run()

        assert mock_run.called
        cmd_str = str(mock_run.call_args[0][0])
        assert _REAL_BIN in cmd_str


# ---------------------------------------------------------------------------
# CalledProcessError
# ---------------------------------------------------------------------------

class TestUpscalerError:
    def test_called_process_error_sets_error_stat(self, config_factory, tmp_project):
        import subprocess

        img = tmp_project / "source" / "images" / "sf2.png"
        img.write_bytes(b"PNG")

        config_factory({
            "upscale": {"engine": "waifu2x", "scale": 2,
                        "output_format": "webp", "workers": 1, "post_process": False},
            "paths": {"bin_waifu2x": _REAL_BIN},
        })
        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler()

        with patch("emupipeline.steps.step_upscale.subprocess.run",
                   side_effect=subprocess.CalledProcessError(1, "waifu2x")):
            upscaler.run()

        assert upscaler.get_stats().get("error") == 1

    def test_called_process_error_does_not_propagate(self, config_factory, tmp_project):
        import subprocess

        img = tmp_project / "source" / "images" / "sf2.png"
        img.write_bytes(b"PNG")

        config_factory({
            "upscale": {"engine": "waifu2x", "scale": 2,
                        "output_format": "webp", "workers": 1, "post_process": False},
            "paths": {"bin_waifu2x": _REAL_BIN},
        })
        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler()

        # Não deve levantar exceção
        with patch("emupipeline.steps.step_upscale.subprocess.run",
                   side_effect=subprocess.CalledProcessError(1, "waifu2x")):
            upscaler.run()  # sem assert, só verificamos que não propagou


# ---------------------------------------------------------------------------
# Pós-processamento Pillow (UnsharpMask)
# ---------------------------------------------------------------------------

class TestPillowPostProcess:
    def _setup(self, config_factory, tmp_project, post_process: bool):
        img = tmp_project / "source" / "images" / "sf2.png"
        img.write_bytes(b"PNG")
        out_dir = tmp_project / "output" / "upscaled"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "sf2.webp").write_bytes(b"webp_data_here")
        config_factory({
            "upscale": {"engine": "waifu2x", "scale": 2,
                        "output_format": "webp", "workers": 1, "post_process": post_process},
            "paths": {"bin_waifu2x": _REAL_BIN},
        })

    def test_unsharp_called_when_post_process_true(self, config_factory, tmp_project):
        self._setup(config_factory, tmp_project, post_process=True)
        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler()

        with patch.object(Upscaler, "_apply_unsharp_pillow") as mock_apply:
            with patch("emupipeline.steps.step_upscale.subprocess.run",
                       return_value=MagicMock(returncode=0)):
                upscaler.run()

        mock_apply.assert_called_once()

    def test_unsharp_not_called_when_post_process_false(self, config_factory, tmp_project):
        self._setup(config_factory, tmp_project, post_process=False)
        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler()

        with patch.object(Upscaler, "_apply_unsharp_pillow") as mock_apply:
            with patch("emupipeline.steps.step_upscale.subprocess.run",
                       return_value=MagicMock(returncode=0)):
                upscaler.run()

        mock_apply.assert_not_called()

    def test_pillow_open_error_does_not_abort(self, config_factory, tmp_project):
        """_apply_unsharp_pillow trata OSError por imagem sem propagar."""
        config_factory({
            "upscale": {"engine": "waifu2x", "scale": 2, "output_format": "webp",
                        "workers": 1, "post_process": True},
            "paths": {"bin_waifu2x": _REAL_BIN},
        })
        out_dir = tmp_project / "output" / "upscaled"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "test.webp").write_bytes(b"data")

        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler()

        from PIL import Image as _PILImage
        with patch.object(_PILImage, "open", side_effect=OSError("leitura falhou")):
            upscaler._apply_unsharp_pillow(out_dir, "webp", "0x1.0+1.0+0.02")

    def test_pillow_absent_skips_gracefully(self, config_factory, tmp_project):
        """Quando PIL não está instalado, _apply_unsharp_pillow retorna sem crash."""
        config_factory({
            "upscale": {"engine": "waifu2x", "scale": 2, "output_format": "webp",
                        "workers": 1, "post_process": True},
            "paths": {"bin_waifu2x": _REAL_BIN},
        })
        out_dir = tmp_project / "output" / "upscaled"
        out_dir.mkdir(parents=True, exist_ok=True)

        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler()

        import sys
        # Bloqueia PIL simulando ausência (sys.modules[key]=None → ImportError)
        pil_backup = {k: sys.modules.pop(k) for k in list(sys.modules) if k == "PIL" or k.startswith("PIL.")}
        sys.modules["PIL"] = None  # type: ignore[assignment]
        try:
            upscaler._apply_unsharp_pillow(out_dir, "webp", "0x1.0+1.0+0.02")
        finally:
            del sys.modules["PIL"]
            sys.modules.update(pil_backup)

    def test_post_processed_stat_set_after_success(self, config_factory, tmp_project):
        self._setup(config_factory, tmp_project, post_process=True)
        out_dir = tmp_project / "output" / "upscaled"

        # Cria imagem WebP real para PIL conseguir abrir
        from PIL import Image as _PIL
        _PIL.new("RGB", (2, 2), color="red").save(out_dir / "sf2.webp", "WEBP")

        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler()

        with patch("emupipeline.steps.step_upscale.subprocess.run",
                   return_value=MagicMock(returncode=0)):
            upscaler.run()

        assert "post_processed" in upscaler.get_stats()


# ---------------------------------------------------------------------------
# get_stats
# ---------------------------------------------------------------------------

class TestGetStats:
    def test_initial_stats_empty(self, config_factory):
        config_factory()
        from emupipeline.steps.step_upscale import Upscaler
        assert Upscaler().get_stats() == {}

    def test_stats_returns_copy(self, config_factory):
        config_factory()
        from emupipeline.steps.step_upscale import Upscaler
        upscaler = Upscaler()
        stats = upscaler.get_stats()
        stats["injected"] = 999
        assert "injected" not in upscaler.get_stats()
