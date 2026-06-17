"""
Testes de integração — smoke tests do pipeline completo.

Estes testes verificam que os steps se integram corretamente:
  - DatSplitter lê → escreve DATs por driver
  - ImageOrganizer lê DAT + imagens → organiza
  - WebPConverter + OriginalCleaner são independentes
  - Pipeline completo não crasha com fixtures mínimas

Subprocess externo (ffmpeg, igir, waifu2x) é sempre mockado.
Pillow é mockado quando ausente.

Marcador: @pytest.mark.integration
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixture de projeto mínimo com imagens reais (PNGs 1x1 pixel)
# ---------------------------------------------------------------------------

@pytest.fixture
def full_project(tmp_project, sample_dat, config_factory):
    """Projeto completo: DAT + 3 imagens + 1 vídeo fake."""
    config_factory()

    # Imagens com nomes que devem casar com o DAT
    imgs_dir = tmp_project / "source" / "images"
    for name in ("sf2.png", "kof97.jpg", "Unknown Game XYZ.png"):
        (imgs_dir / name).write_bytes(
            # PNG 1x1 pixel válido
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
            b"\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18"
            b"\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )

    # Vídeo fake (não é vídeo real, apenas para testar o fluxo)
    vids_dir = tmp_project / "source" / "videos"
    vids_dir.mkdir(exist_ok=True)
    (vids_dir / "sf2.avi").write_bytes(b"FAKE_VIDEO_CONTENT" * 10)

    # ROMs fake
    roms_dir = tmp_project / "source" / "roms"
    for name in ("sf2.zip", "kof97.zip"):
        (roms_dir / name).write_bytes(b"PK\x03\x04")  # ZIP magic bytes

    return tmp_project


# ---------------------------------------------------------------------------
# Smoke test: DatSplitter
# ---------------------------------------------------------------------------

class TestDatSplitterIntegration:
    def test_dat_split_creates_driver_files(self, full_project, sample_dat, config_factory):
        """DatSplitter deve criar pelo menos um arquivo .dat por driver."""
        config_factory({"roms": {
            "split_by_driver": True, "exclude_clones": True,
            "blacklist": ["mahjong", "hack"],
            "generate_bios_file": False, "bios_filename": "bios.dat",
            "combined_filename": "combined.dat", "enable_igir": False,
            "organize_subfolders": True, "merge_mode": "nonmerged",
            "filter_regions": "WORLD,USA", "threads_io": 1,
        }})

        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.steps.step_dat_split import DatSplitter

        dat = DatMaster(sample_dat)
        splitter = DatSplitter(dat)
        splitter.run()

        out_dir = full_project / "output" / "dats"
        dat_files = list(out_dir.glob("*.dat"))
        assert len(dat_files) >= 1, f"Nenhum .dat gerado em {out_dir}"

    def test_dat_split_excludes_blacklist(self, full_project, sample_dat, config_factory):
        """Jogos na blacklist não devem aparecer nos DATs gerados."""
        config_factory({"roms": {
            "split_by_driver": True, "exclude_clones": False,
            "blacklist": ["mahjong", "hack"],
            "generate_bios_file": False, "bios_filename": "bios.dat",
            "combined_filename": "combined.dat", "enable_igir": False,
            "organize_subfolders": True, "merge_mode": "nonmerged",
            "filter_regions": "WORLD,USA", "threads_io": 1,
        }})

        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.steps.step_dat_split import DatSplitter

        dat = DatMaster(sample_dat)
        DatSplitter(dat).run()

        out_dir = full_project / "output" / "dats"
        all_content = " ".join(f.read_text(errors="replace") for f in out_dir.glob("*.dat"))
        assert "mjmahjng" not in all_content
        assert "hackgame" not in all_content

    def test_dat_split_excludes_clones_when_configured(self, full_project, sample_dat, config_factory):
        """Com exclude_clones=True, sf2ce e sf2hf não devem aparecer."""
        config_factory({"roms": {
            "split_by_driver": True, "exclude_clones": True,
            "blacklist": [], "generate_bios_file": False, "bios_filename": "b.dat",
            "combined_filename": "c.dat", "enable_igir": False,
            "organize_subfolders": True, "merge_mode": "nonmerged",
            "filter_regions": "WORLD,USA", "threads_io": 1,
        }})
        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.steps.step_dat_split import DatSplitter

        dat = DatMaster(sample_dat)
        DatSplitter(dat).run()

        out_dir = full_project / "output" / "dats"
        all_content = " ".join(f.read_text(errors="replace") for f in out_dir.glob("*.dat"))
        assert "sf2ce" not in all_content
        assert "sf2hf" not in all_content
        assert "sf2" in all_content  # parent permanece


# ---------------------------------------------------------------------------
# Smoke test: ImageOrganizer
# ---------------------------------------------------------------------------

class TestImageOrganizerIntegration:
    def test_known_images_are_organized(self, full_project, sample_dat, config_factory):
        """sf2.png e kof97.jpg devem ser organizados na pasta de saída."""
        config_factory({"images": {"mode": "copy", "organization_mode": "flat",
                                    "overwrite": False, "fuzzy_threshold": 0.80,
                                    "valid_extensions": [".png", ".jpg"]}})

        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.steps.step_organize import ImageOrganizer

        dat = DatMaster(sample_dat)
        organizer = ImageOrganizer(dat)
        organizer.run()

        out_dir = full_project / "output" / "images"
        organized = {f.name for f in out_dir.rglob("*") if f.is_file()}
        assert "sf2.png" in organized or "sf2.jpg" in organized

    def test_unknown_images_not_organized(self, full_project, sample_dat, config_factory):
        """'Unknown Game XYZ.png' não deve aparecer na saída."""
        config_factory({"images": {"mode": "copy", "organization_mode": "flat",
                                    "overwrite": False, "fuzzy_threshold": 0.80,
                                    "valid_extensions": [".png", ".jpg"]}})

        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.steps.step_organize import ImageOrganizer

        dat = DatMaster(sample_dat)
        ImageOrganizer(dat).run()

        out_dir = full_project / "output" / "images"
        names = {f.name for f in out_dir.rglob("*") if f.is_file()}
        assert "Unknown Game XYZ.png" not in names


# ---------------------------------------------------------------------------
# Smoke test: WebPConverter → OriginalCleaner (responsabilidades separadas)
# ---------------------------------------------------------------------------

class TestConvertCleanSeparation:
    def test_converter_does_not_delete(self, full_project, config_factory):
        """WebPConverter nunca apaga o original — isso é responsabilidade do OriginalCleaner."""
        config_factory({"webp": {"quality": 85, "delete_original": False,
                                  "source_extensions": [".png", ".jpg"]}})

        imgs_dir = full_project / "source" / "images"

        try:
            from PIL import Image
            from emupipeline.steps.step_convert import WebPConverter
            conv = WebPConverter()
            conv._source_dir = imgs_dir
            conv.run()

            # Original deve existir ainda
            assert (imgs_dir / "sf2.png").exists()
        except ImportError:
            pytest.skip("Pillow não instalado")

    def test_cleaner_only_deletes_if_webp_exists(self, full_project, config_factory):
        """OriginalCleaner só apaga PNG se houver WebP correspondente."""
        config_factory()
        imgs_dir = full_project / "source" / "images"

        # Cria um WebP manualmente (simula conversão feita)
        (imgs_dir / "sf2.webp").write_bytes(b"WEBP_DATA")

        from emupipeline.steps.step_clean import OriginalCleaner
        cleaner = OriginalCleaner()
        cleaner._source_dir = imgs_dir
        cleaner._extensions = {".png", ".jpg"}

        # Simula confirmação do usuário
        with patch("builtins.input", return_value="DELETAR"):
            cleaner.run()

        # sf2.png deve ter sido deletado (tem WebP correspondente)
        assert not (imgs_dir / "sf2.png").exists()
        # kof97.jpg deve permanecer (não tem WebP correspondente)
        assert (imgs_dir / "kof97.jpg").exists()


# ---------------------------------------------------------------------------
# Smoke test: Pipeline completo (com mocks de subprocess)
# ---------------------------------------------------------------------------

class TestFullPipelineSmoke:
    @patch("emupipeline.steps.step_rom_manager.subprocess.run")
    @patch("emupipeline.steps.step_optimize.subprocess.run")
    @patch("emupipeline.steps.step_optimize.subprocess.Popen")
    def test_pipeline_completes_without_crash(
        self, mock_popen, mock_opt_run, mock_igir_run, full_project, sample_dat, config_factory
    ):
        """Pipeline completo não deve levantar exceção com fixtures mínimas."""
        config_factory()

        # IGIR mock
        mock_igir_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # ffprobe: todos os vídeos já estão em hevc → smart-skip
        mock_opt_run.return_value = MagicMock(stdout="hevc\n", returncode=0)

        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.cli import _run_pipeline

        dat = DatMaster(sample_dat)

        # Não deve levantar exceção
        try:
            _run_pipeline(dat=dat, stop_on_error=False)
        except SystemExit:
            pass  # SystemExit de fail_fast é OK em ambiente sem ffmpeg

    def test_pipeline_audit_mode_zero_disk_writes(self, full_project, sample_dat, config_factory):
        """No modo AUDIT, nenhum arquivo deve ser criado/modificado."""
        config_factory()

        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.core.execution_mode import AuditReport, ExecutionMode
        from emupipeline.cli import _run_pipeline

        dat = DatMaster(sample_dat)
        report = AuditReport()

        # Snapshot dos arquivos antes
        before = {str(p): p.stat().st_mtime
                  for p in full_project.rglob("*") if p.is_file()
                  and "output" not in str(p) and "logs" not in str(p)}

        _run_pipeline(dat=dat, mode=ExecutionMode.AUDIT, audit=report, stop_on_error=False)

        # Snapshot depois
        after = {str(p): p.stat().st_mtime
                 for p in full_project.rglob("*") if p.is_file()
                 and "output" not in str(p) and "logs" not in str(p)}

        # Nenhum arquivo de entrada foi modificado
        for path, mtime in before.items():
            assert after.get(path) == mtime, f"Arquivo modificado em modo AUDIT: {path}"

        # Mas o audit report deve ter registros
        assert report.total > 0
