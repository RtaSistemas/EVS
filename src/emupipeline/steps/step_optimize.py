"""
Step 8 — Otimização de vídeos com FFmpeg H.265/H.264.

Mudanças v5:
  - atomic_write: arquivo corrompido nunca substitui o original
  - smart_skip via ffprobe antes de qualquer processamento
  - Controle de oversubscription: python_workers = global_threads // 2
    para deixar metade dos cores para os processos ffmpeg
  - Deleção do original SEPARADA e APÓS commit bem-sucedido
  - Timeout de processo com kill de grupo (sem zombies)
  - ExecutionMode: dry_run e audit
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.processor import BaseProcessor
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta
from emupipeline.core.transaction import atomic_write

# Mapeamento codec → nome que o ffprobe retorna
_CODEC_NAMES: dict[str, set[str]] = {
    "libx265": {"hevc", "h265"},
    "libx264": {"h264", "avc"},
}


@register
class VideoOptimizer(BaseProcessor):
    meta = StepMeta(
        id="optimize_videos",
        menu_number=8,
        label="Otimizar vídeos (FFmpeg H.265)",
        group="Vídeo & Metadados",
        description="Reencoda vídeos para H.265/H.264 com smart-skip.",
        pipeline_order=80,
    )

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        audit: Optional[AuditReport] = None,
    ) -> None:
        super().__init__("VideoOptimizer", mode=mode, audit=audit)

        vid = self.config.get("videos")
        self.codec           = getattr(vid, "codec",          "libx265")
        self.crf             = getattr(vid, "crf",            28)
        self.preset          = getattr(vid, "preset",         "fast")
        self.smart_skip      = getattr(vid, "smart_skip",     True)
        self.delete_original = getattr(vid, "delete_original",True)
        self._extensions: set[str] = set(
            getattr(vid, "extensions", [".mp4", ".avi", ".mkv", ".mov", ".webm"])
        )
        self._target_codecs = _CODEC_NAMES.get(self.codec, set())

        # Controle de oversubscription:
        # Python usa metade dos workers; ffmpeg usa a outra metade
        global_threads = self.config.get("global", "threads", 4)
        self._python_workers = max(1, global_threads // 2)
        self._ffmpeg_threads = str(max(1, global_threads // self._python_workers))

    def run(self, **kwargs: Any) -> None:
        videos_dir = self.config.get("paths", "videos_dir")
        if not videos_dir or not Path(videos_dir).exists():
            self.logger.error(f"Diretório de vídeos não encontrado: {videos_dir}")
            return
        files = self.scan(Path(videos_dir), extensions=self._extensions)
        self.run_parallel(files, threads=self._python_workers)

    def process_file(self, file_path: Path) -> str:
        # Smart-skip: verifica codec atual via ffprobe
        if self.smart_skip:
            current = self._probe_codec(file_path)
            if current and current.lower() in self._target_codecs:
                return "skipped_codec"

        final_out = file_path.with_suffix(".mp4")

        if self._mode == ExecutionMode.AUDIT:
            assert self._audit is not None
            self._audit.record(
                step=self.name, action="reencode",
                source=str(file_path), dest=str(final_out),
                reason=f"→ {self.codec} crf={self.crf}",
                would_delete=self.delete_original and file_path != final_out,
            )
            return "audit_recorded"

        if self._mode == ExecutionMode.DRY_RUN:
            self.logger.debug(f"[DRY] Reencodaria: {file_path.name}")
            return "dry_run"

        try:
            with atomic_write(final_out) as tmp:
                self._run_ffmpeg(file_path, tmp)

            # Deleção SEPARADA e APÓS commit bem-sucedido
            if self.delete_original and file_path != final_out:
                if final_out.exists() and final_out.stat().st_size > 0:
                    file_path.unlink(missing_ok=True)

            return "optimized"

        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout ao processar: {file_path.name}")
            return "error"
        except RuntimeError as exc:
            self.logger.error(str(exc))
            return "error"
        except Exception as exc:
            self.logger.error(f"Erro inesperado em {file_path.name}: {exc}", exc_info=True)
            return "error"

    def _probe_codec(self, path: Path) -> Optional[str]:
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=codec_name",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                capture_output=True, text=True, timeout=30,
            )
            return r.stdout.strip() or None
        except Exception:
            return None

    def _run_ffmpeg(self, src: Path, tmp: Path) -> None:
        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-c:v", self.codec,
            "-crf", str(self.crf),
            "-preset", self.preset,
            "-threads", self._ffmpeg_threads,
            "-c:a", "copy",
            str(tmp),
        ]
        self.logger.debug(f"ffmpeg: {' '.join(cmd)}")

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            start_new_session=True,   # grupo de processo separado
        )
        try:
            _, stderr = proc.communicate(timeout=3600)
        except subprocess.TimeoutExpired:
            # Mata todo o grupo de processo (evita zombies)
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            raise

        if proc.returncode != 0:
            err_msg = (stderr or b"").decode(errors="replace")[-300:]
            raise RuntimeError(f"ffmpeg falhou ({proc.returncode}): {err_msg}")
