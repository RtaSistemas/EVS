"""
Testes para step_optimize (VideoOptimizer).

Cobertura alvo: 80%
Foco em:
  - smart_skip via ffprobe (não chamar ffmpeg desnecessariamente)
  - montagem correta do comando ffmpeg
  - atomic_write — arquivo corrompido não substitui o original
  - dry-run e audit-mode
  - controle de oversubscription (python_workers = threads // 2)
  - timeout de processo com killpg
"""

from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import pytest

from emupipeline.core.execution_mode import AuditReport, ExecutionMode


@pytest.fixture
def optimizer(config_factory):
    config_factory()
    from emupipeline.steps.step_optimize import VideoOptimizer
    return VideoOptimizer()


@pytest.fixture
def optimizer_audit(config_factory):
    config_factory()
    from emupipeline.steps.step_optimize import VideoOptimizer
    report = AuditReport()
    return VideoOptimizer(mode=ExecutionMode.AUDIT, audit=report), report


# ---------------------------------------------------------------------------
# Smart-skip via ffprobe
# ---------------------------------------------------------------------------

class TestSmartSkip:
    @patch("emupipeline.steps.step_optimize.subprocess.run")
    def test_skips_file_already_in_target_codec(self, mock_run, optimizer, tmp_path):
        """Arquivo já em hevc deve ser pulado sem chamar ffmpeg."""
        mock_run.return_value = MagicMock(stdout="hevc\n", returncode=0)

        video = tmp_path / "game.mp4"
        video.write_bytes(b"X" * 100)

        result = optimizer.process_file(video)

        assert result == "skipped_codec"
        # ffprobe chamado, ffmpeg NÃO chamado
        assert mock_run.call_count == 1
        assert "ffprobe" in str(mock_run.call_args)

    @patch("emupipeline.steps.step_optimize.subprocess.run")
    def test_does_not_skip_different_codec(self, mock_run, optimizer, tmp_path):
        """Arquivo em mpeg4 deve ser processado."""
        mock_run.return_value = MagicMock(stdout="mpeg4\n", returncode=0)

        video = tmp_path / "game.avi"
        video.write_bytes(b"X" * 100)
        dummy_out = tmp_path / ".tmp_game.mp4"
        dummy_out.write_bytes(b"X" * 100)

        with patch("emupipeline.steps.step_optimize.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 0
            mock_proc.pid = 9999
            mock_popen.return_value = mock_proc

            with patch("emupipeline.steps.step_optimize.atomic_write",
                       side_effect=lambda p: nullcontext(dummy_out)):
                optimizer.process_file(video)

        assert mock_popen.called, "ffmpeg deve ser chamado para arquivo não-hevc"

    @patch("emupipeline.steps.step_optimize.subprocess.run")
    def test_smart_skip_disabled_always_processes(self, mock_run, optimizer, tmp_path):
        """Com smart_skip=False, processa mesmo se já estiver no codec correto."""
        optimizer.smart_skip = False
        mock_run.return_value = MagicMock(stdout="hevc\n", returncode=0)

        video = tmp_path / "game.mp4"
        video.write_bytes(b"X" * 100)
        dummy_out = tmp_path / ".tmp_game_out.mp4"
        dummy_out.write_bytes(b"X" * 100)

        with patch("emupipeline.steps.step_optimize.subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.communicate.return_value = (b"", b"")
            mock_proc.returncode = 0
            mock_proc.pid = 9999
            mock_popen.return_value = mock_proc

            with patch("emupipeline.steps.step_optimize.atomic_write",
                       side_effect=lambda p: nullcontext(dummy_out)):
                optimizer.process_file(video)

        assert mock_popen.called


# ---------------------------------------------------------------------------
# Montagem do comando ffmpeg
# ---------------------------------------------------------------------------

class TestCommandConstruction:
    def test_codec_in_command(self, optimizer):
        assert optimizer.codec == "libx265"

    def test_crf_in_command(self, optimizer):
        assert optimizer.crf == 28

    def test_target_codec_names_hevc(self, optimizer):
        assert "hevc" in optimizer._target_codec_names

    def test_target_codec_names_h264(self, config_factory):
        config_factory({"videos": {"codec": "libx264", "crf": 23, "smart_skip": True,
                                    "delete_original": False, "extensions": [".mp4"],
                                    "preset": "fast"}})
        from emupipeline.steps.step_optimize import VideoOptimizer
        opt = VideoOptimizer()
        assert "h264" in opt._target_codec_names or "avc" in opt._target_codec_names

    def test_oversubscription_control(self, config_factory):
        """Workers Python deve ser threads // 2 para não disputar CPU com ffmpeg."""
        config_factory({"global": {"base_dir": "%(base_dir)s", "threads": 8,
                                    "logging_level": "DEBUG"}})
        from emupipeline.steps.step_optimize import VideoOptimizer
        # Não podemos instanciar sem paths, mas validamos a fórmula
        assert VideoOptimizer._python_workers_formula(8) == 4

    def test_oversubscription_minimum_one(self, config_factory):
        config_factory()
        from emupipeline.steps.step_optimize import VideoOptimizer
        assert VideoOptimizer._python_workers_formula(1) == 1


# ---------------------------------------------------------------------------
# Atomic write — integridade
# ---------------------------------------------------------------------------

class TestAtomicWrite:
    @patch("emupipeline.steps.step_optimize.subprocess.run")
    @patch("emupipeline.steps.step_optimize.subprocess.Popen")
    def test_zero_byte_output_not_committed(self, mock_popen, mock_ffprobe, optimizer, tmp_path):
        """Se ffmpeg gerar arquivo vazio, o original deve ser preservado."""
        mock_ffprobe.return_value = MagicMock(stdout="mpeg4\n", returncode=0)

        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0
        mock_proc.pid = 9999
        mock_popen.return_value = mock_proc

        original = tmp_path / "game.avi"
        original.write_bytes(b"original_content")

        # stat() retorna 0 bytes para o arquivo temporário
        with patch("pathlib.Path.stat") as mock_stat:
            mock_stat.return_value = MagicMock(st_size=0)
            result = optimizer.process_file(original)

        assert result == "error"
        # Original intacto
        assert original.exists()
        assert original.read_bytes() == b"original_content"

    @patch("emupipeline.steps.step_optimize.subprocess.run")
    @patch("emupipeline.steps.step_optimize.subprocess.Popen")
    def test_ffmpeg_nonzero_return_is_error(self, mock_popen, mock_ffprobe, optimizer, tmp_path):
        """Returncode != 0 do ffmpeg deve resultar em 'error'."""
        mock_ffprobe.return_value = MagicMock(stdout="mpeg4\n", returncode=0)

        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"", b"ffmpeg error message")
        mock_proc.returncode = 1
        mock_proc.pid = 9999
        mock_popen.return_value = mock_proc

        video = tmp_path / "broken.avi"
        video.write_bytes(b"data")

        result = optimizer.process_file(video)
        assert result == "error"


# ---------------------------------------------------------------------------
# Dry-run e Audit
# ---------------------------------------------------------------------------

class TestExecutionModes:
    def test_dry_run_skips_io(self, config_factory, tmp_path):
        config_factory()
        from emupipeline.steps.step_optimize import VideoOptimizer
        opt = VideoOptimizer(mode=ExecutionMode.DRY_RUN)

        video = tmp_path / "game.mp4"
        video.write_bytes(b"X" * 100)

        with patch("emupipeline.steps.step_optimize.subprocess.run") as mock_run:
            result = opt.process_file(video)

        assert result == "dry_run"
        mock_run.assert_not_called()

    def test_audit_records_operation(self, optimizer_audit, tmp_path):
        opt, report = optimizer_audit
        video = tmp_path / "game.avi"
        video.write_bytes(b"X" * 100)

        result = opt.process_file(video)

        assert result == "audit_recorded"
        assert report.total == 1
        entry = report.entries()[0]
        assert entry.action == "optimize_video"
        assert entry.step == "VideoOptimizer"

    def test_audit_marks_delete_when_configured(self, config_factory, tmp_path):
        config_factory({"videos": {"codec": "libx265", "crf": 28, "smart_skip": True,
                                    "delete_original": True, "extensions": [".mp4"],
                                    "preset": "fast"}})
        from emupipeline.steps.step_optimize import VideoOptimizer
        report = AuditReport()
        opt = VideoOptimizer(mode=ExecutionMode.AUDIT, audit=report)

        video = tmp_path / "game.avi"
        video.write_bytes(b"X" * 100)
        opt.process_file(video)

        assert report.destructive_count == 1

    def test_audit_without_report_returns_error(self, config_factory, tmp_path):
        """AUDIT sem AuditReport deve retornar 'error' sem levantar exceção."""
        config_factory()
        from emupipeline.steps.step_optimize import VideoOptimizer
        opt = VideoOptimizer(mode=ExecutionMode.AUDIT, audit=None)
        video = tmp_path / "game.mp4"
        video.write_bytes(b"X" * 100)
        result = opt.process_file(video)
        assert result == "error"


# ---------------------------------------------------------------------------
# run() — early return quando videos_dir ausente
# ---------------------------------------------------------------------------

class TestRunEarlyReturn:
    def test_run_missing_videos_dir_returns_early(self, config_factory, tmp_project):
        """run() não deve processar nada quando o diretório de vídeos não existe."""
        import shutil
        config_factory()
        shutil.rmtree(tmp_project / "source" / "videos", ignore_errors=True)

        from emupipeline.steps.step_optimize import VideoOptimizer
        opt = VideoOptimizer()
        with patch("emupipeline.steps.step_optimize.subprocess.Popen") as mock_popen:
            opt.run()
            mock_popen.assert_not_called()

    def test_run_missing_videos_dir_stat_empty(self, config_factory, tmp_project):
        import shutil
        config_factory()
        shutil.rmtree(tmp_project / "source" / "videos", ignore_errors=True)

        from emupipeline.steps.step_optimize import VideoOptimizer
        opt = VideoOptimizer()
        opt.run()
        assert opt.get_stats() == {}


# ---------------------------------------------------------------------------
# delete_original após conversão bem-sucedida
# ---------------------------------------------------------------------------

class TestDeleteOriginalAfterSuccess:
    @patch("emupipeline.steps.step_optimize.subprocess.run")
    @patch("emupipeline.steps.step_optimize.subprocess.Popen")
    def test_delete_original_removes_source_on_success(self, mock_popen, mock_ffprobe, config_factory, tmp_path):
        config_factory({"videos": {"codec": "libx265", "crf": 28, "smart_skip": True,
                                    "delete_original": True, "extensions": [".avi"],
                                    "preset": "fast"}})
        from emupipeline.steps.step_optimize import VideoOptimizer
        opt = VideoOptimizer()

        mock_ffprobe.return_value = MagicMock(stdout="mpeg4\n", returncode=0)
        mock_proc = MagicMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0
        mock_proc.pid = 9999
        mock_popen.return_value = mock_proc

        original = tmp_path / "game.avi"
        original.write_bytes(b"A" * 200)
        dummy_out = tmp_path / "game.mp4"
        dummy_out.write_bytes(b"X" * 200)

        from contextlib import nullcontext
        with patch("emupipeline.steps.step_optimize.atomic_write",
                   side_effect=lambda p: nullcontext(dummy_out)):
            result = opt.process_file(original)

        assert result == "optimized"
        assert not original.exists()


# ---------------------------------------------------------------------------
# _probe_codec — exception silenciada
# ---------------------------------------------------------------------------

class TestProbeCodec:
    def test_probe_codec_returns_none_on_exception(self, config_factory, tmp_path):
        config_factory()
        from emupipeline.steps.step_optimize import VideoOptimizer
        opt = VideoOptimizer()

        video = tmp_path / "game.mp4"
        video.write_bytes(b"X" * 100)

        with patch("emupipeline.steps.step_optimize.subprocess.run", side_effect=OSError("no ffprobe")):
            result = opt._probe_codec(video)

        assert result is None


# ---------------------------------------------------------------------------
# _run_ffmpeg — timeout mata grupo de processos
# ---------------------------------------------------------------------------

class TestRunFfmpegTimeout:
    @patch("emupipeline.steps.step_optimize.subprocess.run")
    def test_timeout_kills_process_group(self, mock_ffprobe, config_factory, tmp_path):
        mock_ffprobe.return_value = MagicMock(stdout="mpeg4\n", returncode=0)
        config_factory()
        import signal
        import subprocess as sp

        from emupipeline.steps.step_optimize import VideoOptimizer

        opt = VideoOptimizer()

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.communicate.side_effect = sp.TimeoutExpired("ffmpeg", 3600)

        with (
            patch("emupipeline.steps.step_optimize.subprocess.Popen", return_value=mock_proc),
            patch("emupipeline.steps.step_optimize.os.killpg") as mock_killpg,
            patch("emupipeline.steps.step_optimize.os.getpgid", return_value=12345),
        ):
            video = tmp_path / "game.avi"
            video.write_bytes(b"X" * 100)
            result = opt.process_file(video)

        assert result == "error"
        mock_killpg.assert_called_once_with(12345, signal.SIGKILL)
