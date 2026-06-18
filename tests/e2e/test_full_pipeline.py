"""
Testes de fim a fim (E2E) — exercita o pipeline completo com dados sintéticos.

Não requer ferramentas externas (ffmpeg, igir, waifu2x).
Valida o contrato de cada step: entradas, saídas, efeitos colaterais.
Cobre três modos de execução: NORMAL, DRY_RUN, AUDIT.

Estrutura do projeto sintético
───────────────────────────────
source/
  roms/       → ZIPs de ROMs (cps1, neogeo)
  images/     → PNGs referenciando nomes de jogos do DAT
  videos/     → vídeos stub (bytes)
output/
  roms/       → destino do igir (não exercitado — requer igir)
  images/     → destino da organização de imagens
  upscaled/   → destino do upscaling (não exercitado)
reports/      → CSV de KPI, validation_report.txt
dats/         → DATs divididos por driver
ports/        → scripts .sh/.desktop gerados
test.dat      → DAT mestre sintético (FBNeo/ClrMamePro format)
config.yaml   → configuração apontando para os dirs sintéticos
"""

from __future__ import annotations

import csv
import os
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from emupipeline.core.execution_mode import AuditReport, ExecutionMode

# ---------------------------------------------------------------------------
# Fixtures compartilhadas
# ---------------------------------------------------------------------------

_DAT_XML = """\
<?xml version="1.0"?>
<datafile>
  <header>
    <name>FBNeo Test DAT</name>
    <version>20250101</version>
  </header>
  <game name="sf2" sourcefile="cps1.cpp">
    <description>Street Fighter II</description>
    <rom name="sf2.zip" size="1024" crc="aabbccdd"/>
  </game>
  <game name="mslug" sourcefile="neogeo.cpp">
    <description>Metal Slug</description>
    <rom name="mslug.zip" size="2048" crc="11223344"/>
  </game>
  <game name="sf2ce" sourcefile="cps1.cpp" cloneof="sf2">
    <description>Street Fighter II Champion Edition</description>
    <rom name="sf2ce.zip" size="512" crc="55667788"/>
  </game>
  <game name="neobios" sourcefile="neogeo.cpp" isbios="yes">
    <description>Neo-Geo BIOS</description>
    <rom name="neogeo.zip" size="128" crc="99aabbcc"/>
  </game>
</datafile>
"""


@pytest.fixture
def e2e_env(tmp_path, monkeypatch):
    """
    Cria estrutura de diretórios, arquivos sintéticos e config.yaml.
    Retorna dict com paths e o path do config.
    """
    dirs: dict[str, Path] = {
        "input_roms":     tmp_path / "source" / "roms",
        "output_roms":    tmp_path / "output" / "roms",
        "input_imgs":     tmp_path / "source" / "images",
        "output_imgs":    tmp_path / "output" / "images",
        "upscale_input":  tmp_path / "source" / "upscale",
        "upscale_output": tmp_path / "output" / "upscaled",
        "videos_dir":     tmp_path / "source" / "videos",
        "output_reports": tmp_path / "reports",
        "output_dats":    tmp_path / "dats",
        "ports_dir":      tmp_path / "ports",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    # DAT mestre
    dat_path = tmp_path / "test.dat"
    dat_path.write_text(_DAT_XML, encoding="utf-8")

    # ROMs: zips para sf2 e mslug (sf2ce excluído como clone)
    for name in ("sf2", "mslug"):
        zp = dirs["input_roms"] / f"{name}.zip"
        with zipfile.ZipFile(zp, "w") as z:
            z.writestr(f"{name}.bin", b"ROM" * 64)

    # Imagens: PNGs nomeadas igual aos jogos
    try:
        from PIL import Image
        for name in ("sf2", "mslug", "unknown_game"):
            img = Image.new("RGB", (100, 100), color=(255, 0, 0))
            img.save(dirs["input_imgs"] / f"{name}.png", "PNG")
    except ImportError:
        for name in ("sf2", "mslug", "unknown_game"):
            (dirs["input_imgs"] / f"{name}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    # Vídeos stub
    (dirs["videos_dir"] / "sf2_gameplay.mp4").write_bytes(b"\x00" * 256)

    # Ports: subdiretório com script executável (PortsAutomator itera subdirs)
    ports_src = tmp_path / "source" / "ports"
    ports_src.mkdir(parents=True, exist_ok=True)
    mygame_dir = ports_src / "mygame"
    mygame_dir.mkdir()
    (mygame_dir / "mygame.sh").write_text("#!/bin/bash\n./mygame\n", encoding="utf-8")

    config_yaml = f"""\
global:
  base_dir: {tmp_path}
  threads: 2
  logging_level: WARNING

paths:
  dat_file:        {dat_path}
  input_roms:      {dirs["input_roms"]}
  output_roms:     {dirs["output_roms"]}
  input_imgs:      {dirs["input_imgs"]}
  output_imgs:     {dirs["output_imgs"]}
  upscale_input:   {dirs["upscale_input"]}
  upscale_output:  {dirs["upscale_output"]}
  videos_dir:      {dirs["videos_dir"]}
  output_reports:  {dirs["output_reports"]}
  output_dats:     {dirs["output_dats"]}
  output_xml:      {tmp_path / "output" / "gamelist.xml"}
  output_logs:     {tmp_path / "logs"}
  bin_waifu2x:     /nonexistent/waifu2x
  bin_realesrgan:  /nonexistent/realesrgan

roms:
  blacklist:          []
  exclude_clones:     true
  split_by_driver:    true
  generate_bios_file: false
  combined_filename:  FBNeo_Optimized.dat
  bios_filename:      00_BIOS_Global.dat
  merge_mode:         nonmerged
  filter_regions:     WORLD,USA
  enable_igir:        false

images:
  mode:              copy
  organization_mode: subfolders
  overwrite:         false
  fuzzy_threshold:   0.80

upscale:
  engine:        waifu2x
  scale:         2
  workers:       1
  output_format: webp
  post_process:  false

videos:
  codec:          libx265
  crf:            28
  preset:         fast
  smart_skip:     true
  delete_original: false
  extensions:     [".mp4", ".avi"]

ports:
  source_dir:      {ports_src}
  output_dir:      {dirs["ports_dir"]}
  enable_gamemode: false
  enable_mangohud: false
  windows_runner:  wine

metadata:
  gamelist_path: {dirs["output_imgs"]}/gamelist.xml
  image_subdir:  images

kpi:
  enabled: true
"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(config_yaml, encoding="utf-8")

    monkeypatch.setenv("EMUPIPELINE_CONFIG", str(cfg_path))
    import emupipeline.core.config as cfg_mod
    cfg_mod.ConfigLoader._instance = None
    fresh = cfg_mod.ConfigLoader()
    cfg_mod.cfg = fresh

    return {"dirs": dirs, "dat_path": dat_path, "cfg_path": cfg_path, "tmp": tmp_path}


# ---------------------------------------------------------------------------
# Step 1 — DatSplitter
# ---------------------------------------------------------------------------

class TestDatSplitterE2E:
    def test_splits_dat_by_driver(self, e2e_env):
        """DatSplitter cria um .dat por driver com jogos não-clone."""
        from emupipeline.steps.step_dat_split import DatSplitter
        step = DatSplitter()
        step.run()

        dats_dir = e2e_env["dirs"]["output_dats"]
        created = list(dats_dir.glob("*.dat"))
        assert len(created) >= 2, "Deve criar DATs para cps1 e neogeo"

        names = {d.stem for d in created}
        assert "cps1" in names
        assert "neogeo" in names

    def test_excludes_clones(self, e2e_env):
        """sf2ce (clone de sf2) não deve aparecer em nenhum DAT."""
        from emupipeline.steps.step_dat_split import DatSplitter
        DatSplitter().run()

        dats_dir = e2e_env["dirs"]["output_dats"]
        for dat_file in dats_dir.glob("*.dat"):
            content = dat_file.read_text(encoding="utf-8")
            assert "sf2ce" not in content, f"{dat_file.name} não deve conter clone sf2ce"

    def test_excludes_bios(self, e2e_env):
        """neobios (isbios=yes) não deve aparecer quando generate_bios_file=false."""
        from emupipeline.steps.step_dat_split import DatSplitter
        DatSplitter().run()

        dats_dir = e2e_env["dirs"]["output_dats"]
        for dat_file in dats_dir.glob("*.dat"):
            content = dat_file.read_text(encoding="utf-8")
            assert "neobios" not in content

    def test_dry_run_writes_nothing(self, e2e_env):
        """DRY_RUN não cria nenhum arquivo em dats/."""
        from emupipeline.steps.step_dat_split import DatSplitter
        step = DatSplitter(mode=ExecutionMode.DRY_RUN)
        step.run()

        dats_dir = e2e_env["dirs"]["output_dats"]
        assert list(dats_dir.glob("*.dat")) == []

    def test_audit_records_operations_without_writing(self, e2e_env):
        """AUDIT registra criação de DATs mas não escreve em disco."""
        from emupipeline.steps.step_dat_split import DatSplitter
        report = AuditReport()
        step = DatSplitter(mode=ExecutionMode.AUDIT, audit=report)
        step.run()

        dats_dir = e2e_env["dirs"]["output_dats"]
        assert list(dats_dir.glob("*.dat")) == [], "AUDIT não deve criar arquivos"
        assert report.total >= 2, "Deve registrar pelo menos 2 operações (cps1, neogeo)"
        assert all(e.action == "create_dat" for e in report.entries())

    def test_stats_count_dats(self, e2e_env):
        """Stats devem contar os DATs criados."""
        from emupipeline.steps.step_dat_split import DatSplitter
        step = DatSplitter()
        step.run()
        assert step.get_stats().get("dats_created", 0) >= 2


# ---------------------------------------------------------------------------
# Step 3 — RomValidator
# ---------------------------------------------------------------------------

class TestRomValidatorE2E:
    def test_detects_found_and_missing(self, e2e_env):
        """RomValidator detecta ROMs presentes e ausentes corretamente."""
        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.steps.step_validate import RomValidator

        dat = DatMaster(str(e2e_env["dat_path"]))
        step = RomValidator(mode=ExecutionMode.NORMAL)
        step.run(dat=dat)

        stats = step.get_stats()
        # sf2 e mslug estão presentes; sf2ce e neobios podem ou não aparecer no dat_map
        assert stats["found"] >= 2
        assert "missing" in stats
        assert "extras" in stats

    def test_dry_run_does_not_write_report(self, e2e_env):
        """DRY_RUN não cria validation_report.txt."""
        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.steps.step_validate import RomValidator

        dat = DatMaster(str(e2e_env["dat_path"]))
        RomValidator(mode=ExecutionMode.DRY_RUN).run(dat=dat)

        report = e2e_env["dirs"]["output_reports"] / "validation_report.txt"
        assert not report.exists()

    def test_normal_mode_writes_report(self, e2e_env):
        """NORMAL cria validation_report.txt com conteúdo."""
        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.steps.step_validate import RomValidator

        dat = DatMaster(str(e2e_env["dat_path"]))
        RomValidator(mode=ExecutionMode.NORMAL).run(dat=dat)

        report = e2e_env["dirs"]["output_reports"] / "validation_report.txt"
        assert report.exists()
        content = report.read_text(encoding="utf-8")
        assert "FALTANTES" in content
        assert "EXTRAS" in content


# ---------------------------------------------------------------------------
# Step 10 — KpiReporter
# ---------------------------------------------------------------------------

class TestKpiReporterE2E:
    def test_generates_csv_in_normal_mode(self, e2e_env):
        """KpiReporter cria kpi.csv com colunas corretas em modo NORMAL."""
        from emupipeline.steps.step_kpi import KpiReporter
        KpiReporter(mode=ExecutionMode.NORMAL).run()

        csv_path = e2e_env["dirs"]["output_reports"] / "kpi.csv"
        assert csv_path.exists()

        rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
        assert len(rows) >= 1
        assert "local" in rows[0]
        assert "arquivos" in rows[0]
        assert "tamanho_mb" in rows[0]

    def test_dry_run_does_not_write_csv(self, e2e_env):
        """DRY_RUN não cria kpi.csv."""
        from emupipeline.steps.step_kpi import KpiReporter
        KpiReporter(mode=ExecutionMode.DRY_RUN).run()

        csv_path = e2e_env["dirs"]["output_reports"] / "kpi.csv"
        assert not csv_path.exists()

    def test_audit_does_not_write_csv(self, e2e_env):
        """AUDIT não cria kpi.csv."""
        from emupipeline.steps.step_kpi import KpiReporter
        KpiReporter(mode=ExecutionMode.AUDIT).run()

        csv_path = e2e_env["dirs"]["output_reports"] / "kpi.csv"
        assert not csv_path.exists()

    def test_stats_count_directories(self, e2e_env):
        """get_stats() retorna contagem de diretórios analisados."""
        from emupipeline.steps.step_kpi import KpiReporter
        step = KpiReporter()
        step.run()
        assert step.get_stats().get("directories_analyzed", 0) >= 1


# ---------------------------------------------------------------------------
# Step 9 — MetadataGenerator (gamelist.xml)
# ---------------------------------------------------------------------------

class TestMetadataWriterE2E:
    def test_generates_gamelist_xml(self, e2e_env):
        """MetadataGenerator cria gamelist.xml para EmulationStation."""
        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.steps.step_metadata import MetadataGenerator

        dat = DatMaster(str(e2e_env["dat_path"]))

        # Popula output_roms para que MetadataGenerator encontre ROMs
        out_roms = e2e_env["dirs"]["output_roms"]
        for name in ("sf2", "mslug"):
            zp = out_roms / f"{name}.zip"
            with zipfile.ZipFile(zp, "w") as z:
                z.writestr(f"{name}.bin", b"ROM" * 64)

        step = MetadataGenerator()
        step.run(dat=dat)

        # output_xml = {tmp_path}/output/gamelist.xml
        gamelist = e2e_env["tmp"] / "output" / "gamelist.xml"
        assert gamelist.exists()

        tree = ET.parse(gamelist)
        games = tree.findall(".//game")
        assert len(games) >= 1

    def test_dry_run_skips_write(self, e2e_env):
        """DRY_RUN não cria gamelist.xml."""
        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.steps.step_metadata import MetadataGenerator

        dat = DatMaster(str(e2e_env["dat_path"]))
        MetadataGenerator(mode=ExecutionMode.DRY_RUN).run(dat=dat)

        gamelist = e2e_env["tmp"] / "output" / "gamelist.xml"
        assert not gamelist.exists()


# ---------------------------------------------------------------------------
# Step 5 — ImageOrganizer (cópia + fuzzy match)
# ---------------------------------------------------------------------------

class TestOrganizeImagesE2E:
    def test_copies_matching_images(self, e2e_env):
        """ImageOrganizer copia imagens cujo nome bate com o DAT."""
        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.steps.step_organize import ImageOrganizer

        dat = DatMaster(str(e2e_env["dat_path"]))
        step = ImageOrganizer()
        step.run(dat=dat)

        out_imgs = e2e_env["dirs"]["output_imgs"]
        # Imagens ficam em subpastas (organization_mode=subfolders)
        copied = list(out_imgs.rglob("*.*"))
        names = {f.stem for f in copied}
        assert "sf2" in names or any("sf2" in n for n in names)

    def test_dry_run_copies_nothing(self, e2e_env):
        """DRY_RUN não copia nem linka nenhum arquivo."""
        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.steps.step_organize import ImageOrganizer

        dat = DatMaster(str(e2e_env["dat_path"]))
        ImageOrganizer(mode=ExecutionMode.DRY_RUN).run(dat=dat)

        out_imgs = e2e_env["dirs"]["output_imgs"]
        assert list(out_imgs.rglob("*.*")) == []

    def test_audit_records_without_writing(self, e2e_env):
        """AUDIT registra cópias sem escrever em disco."""
        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.steps.step_organize import ImageOrganizer

        dat = DatMaster(str(e2e_env["dat_path"]))
        report = AuditReport()
        ImageOrganizer(mode=ExecutionMode.AUDIT, audit=report).run(dat=dat)

        out_imgs = e2e_env["dirs"]["output_imgs"]
        # Nenhum arquivo E nenhum diretório deve ser criado
        assert list(out_imgs.rglob("*")) == [], "AUDIT não deve criar arquivos nem diretórios"
        assert report.total >= 1


# ---------------------------------------------------------------------------
# Step 6 — WebPConverter (PNG → WebP)
# ---------------------------------------------------------------------------

class TestWebPConverterE2E:
    def test_converts_png_to_webp(self, e2e_env):
        """WebPConverter converte PNGs válidos para WebP."""
        pytest.importorskip("PIL", reason="Pillow não instalado")

        from PIL import Image
        from emupipeline.core.processor import ExecutorType
        from emupipeline.steps.step_convert import WebPConverter

        # Cria imagens reais no output_imgs
        out_imgs = e2e_env["dirs"]["output_imgs"]
        for name in ("sf2", "mslug"):
            Image.new("RGB", (32, 32), color="blue").save(out_imgs / f"{name}.png", "PNG")

        # Usa ThreadPoolExecutor para evitar problema de pickle do ConfigLoader singleton
        with patch.object(WebPConverter, "_executor_type", ExecutorType.THREAD):
            WebPConverter().run()

        webps = list(out_imgs.glob("*.webp"))
        assert len(webps) >= 2

    def test_dry_run_converts_nothing(self, e2e_env):
        """DRY_RUN não cria nenhum WebP."""
        from emupipeline.core.processor import ExecutorType
        from emupipeline.steps.step_convert import WebPConverter

        out_imgs = e2e_env["dirs"]["output_imgs"]
        (out_imgs / "sf2.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        with patch.object(WebPConverter, "_executor_type", ExecutorType.THREAD):
            WebPConverter(mode=ExecutionMode.DRY_RUN).run()
        assert list(out_imgs.glob("*.webp")) == []


# ---------------------------------------------------------------------------
# Step 11 — PortsAutomator (launchers .sh)
# ---------------------------------------------------------------------------

class TestPortsCreatorE2E:
    def test_creates_linux_launchers(self, e2e_env):
        """PortsAutomator cria script .sh para cada jogo em source_dir."""
        from emupipeline.steps.step_ports import PortsAutomator

        PortsAutomator().run()

        ports_dir = e2e_env["dirs"]["ports_dir"]
        scripts = list(ports_dir.rglob("*.sh"))
        assert len(scripts) >= 1

    def test_dry_run_creates_nothing(self, e2e_env):
        """DRY_RUN não cria nenhum script."""
        from emupipeline.steps.step_ports import PortsAutomator

        PortsAutomator(mode=ExecutionMode.DRY_RUN).run()
        ports_dir = e2e_env["dirs"]["ports_dir"]
        assert list(ports_dir.rglob("*")) == []


# ---------------------------------------------------------------------------
# Pipeline completo — DRY_RUN end-to-end
# ---------------------------------------------------------------------------

class TestFullPipelineDryRun:
    """Roda cada step em sequência no modo DRY_RUN e verifica que nenhuma
    escrita de arquivo ocorre nos diretórios de saída (exceto DAT que precisa
    existir para steps seguintes — validado individualmente acima)."""

    STEPS_NEED_DAT = {"validate_roms", "organize_images", "write_metadata"}

    def test_no_output_files_created(self, e2e_env):
        """Nenhum step em DRY_RUN deve criar arquivos de saída."""
        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.core.processor import ExecutorType
        from emupipeline.core.registry import autodiscover, get_pipeline_steps

        autodiscover()
        dat = DatMaster(str(e2e_env["dat_path"]))

        output_dirs = [
            e2e_env["dirs"]["output_imgs"],
            e2e_env["dirs"]["output_dats"],
            e2e_env["dirs"]["output_reports"],
            e2e_env["dirs"]["ports_dir"],
        ]

        def files_in(dirs: list[Path]) -> set[Path]:
            result = set()
            for d in dirs:
                result.update(f for f in d.rglob("*") if f.is_file())
            return result

        before = files_in(output_dirs)

        from emupipeline.steps import step_convert
        with patch.object(step_convert.WebPConverter, "_executor_type", ExecutorType.THREAD):
            for cls in get_pipeline_steps():
                try:
                    if cls.meta.requires_dat:
                        step = cls(mode=ExecutionMode.DRY_RUN)  # type: ignore[call-arg]
                        step.run(dat=dat)
                    else:
                        step = cls(mode=ExecutionMode.DRY_RUN)  # type: ignore[call-arg]
                        step.run()
                except Exception:
                    pass  # step pode não suportar instanciação direta (ex: sem binary)

        after = files_in(output_dirs)
        new_files = after - before
        assert new_files == set(), f"DRY_RUN criou arquivos inesperados: {new_files}"


# ---------------------------------------------------------------------------
# Pipeline completo — AUDIT end-to-end
# ---------------------------------------------------------------------------

class TestFullPipelineAudit:
    """Roda steps auditáveis em modo AUDIT e verifica integridade do relatório."""

    def test_audit_captures_all_operations(self, e2e_env):
        """Cada step auditável deve produzir ao menos uma entrada no AuditReport."""
        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.steps.step_dat_split import DatSplitter
        from emupipeline.steps.step_organize import ImageOrganizer

        dat = DatMaster(str(e2e_env["dat_path"]))
        report = AuditReport()

        DatSplitter(mode=ExecutionMode.AUDIT, audit=report).run()
        ImageOrganizer(mode=ExecutionMode.AUDIT, audit=report).run(dat=dat)

        assert report.total >= 3  # ≥2 DATs + ≥1 imagem organizada
        actions = {e.action for e in report.entries()}
        assert "create_dat" in actions

    def test_audit_no_disk_writes(self, e2e_env):
        """AUDIT não deve criar nenhum arquivo nas saídas."""
        from emupipeline.core.dat_manager import DatMaster
        from emupipeline.steps.step_dat_split import DatSplitter
        from emupipeline.steps.step_organize import ImageOrganizer
        from emupipeline.steps.step_validate import RomValidator

        dat = DatMaster(str(e2e_env["dat_path"]))
        report = AuditReport()

        DatSplitter(mode=ExecutionMode.AUDIT, audit=report).run()
        ImageOrganizer(mode=ExecutionMode.AUDIT, audit=report).run(dat=dat)
        RomValidator(mode=ExecutionMode.AUDIT).run(dat=dat)

        for d in [e2e_env["dirs"]["output_dats"],
                  e2e_env["dirs"]["output_imgs"],
                  e2e_env["dirs"]["output_reports"]]:
            items = list(d.rglob("*"))
            assert items == [], f"AUDIT criou item inesperado em {d}: {items}"

    def test_audit_report_entries_schema(self, e2e_env):
        """Cada entrada do AuditReport tem step, action, source preenchidos."""
        from emupipeline.steps.step_dat_split import DatSplitter

        report = AuditReport()
        DatSplitter(mode=ExecutionMode.AUDIT, audit=report).run()

        for entry in report.entries():
            assert entry.step, "step não pode ser vazio"
            assert entry.action, "action não pode ser vazio"
            assert entry.source, "source não pode ser vazio"


# ---------------------------------------------------------------------------
# EnvironmentChecker E2E
# ---------------------------------------------------------------------------

class TestEnvironmentCheckerE2E:
    def test_check_all_returns_results(self, e2e_env):
        """check_all() retorna lista de DepStatus com ao menos as ferramentas essenciais."""
        from emupipeline.core.config import cfg
        from emupipeline.core.env_checker import EnvironmentChecker

        checker = EnvironmentChecker(cfg.schema)
        results = checker.check_all()

        names = {r.name for r in results}
        assert "ffmpeg" in names
        assert "ffprobe" in names
        assert "igir" in names

    def test_check_path_binary_found(self, e2e_env, tmp_path):
        """_check_path_binary detecta binário existente."""
        from emupipeline.core.config import cfg
        from emupipeline.core.env_checker import EnvironmentChecker

        binary = tmp_path / "my_tool"
        binary.write_bytes(b"ELF")

        checker = EnvironmentChecker(cfg.schema)
        checker._check_path_binary("my_tool", binary)
        result = checker._results[-1]
        assert result.found is True
        assert result.name == "my_tool"

    def test_check_path_binary_missing(self, e2e_env, tmp_path):
        """_check_path_binary detecta binário ausente."""
        from emupipeline.core.config import cfg
        from emupipeline.core.env_checker import EnvironmentChecker

        checker = EnvironmentChecker(cfg.schema)
        checker._check_path_binary("waifu2x", tmp_path / "nonexistent")
        result = checker._results[-1]
        assert result.found is False

    def test_report_is_readable_string(self, e2e_env):
        """report() retorna string legível sem exceções."""
        from emupipeline.core.config import cfg
        from emupipeline.core.env_checker import EnvironmentChecker

        checker = EnvironmentChecker(cfg.schema)
        checker.check_all()
        report = checker.report()
        assert isinstance(report, str)
        assert len(report) > 0


# ---------------------------------------------------------------------------
# AuditReport unitário
# ---------------------------------------------------------------------------

class TestAuditReportE2E:
    def test_total_matches_records(self):
        report = AuditReport()
        report.record(step="s", action="a", source="/f1")
        report.record(step="s", action="b", source="/f2", dest="/f3", would_delete=True)
        assert report.total == 2

    def test_destructive_count(self):
        report = AuditReport()
        report.record(step="s", action="a", source="/f", would_delete=True)
        report.record(step="s", action="b", source="/g", would_delete=False)
        assert report.destructive_count == 1

    def test_entries_immutable(self):
        report = AuditReport()
        report.record(step="s", action="a", source="/f")
        entries = report.entries()
        entries.clear()
        assert report.total == 1  # original não afetado

    def test_thread_safe_concurrent_records(self):
        """AuditReport deve ser thread-safe."""
        import threading

        report = AuditReport()
        errors: list[Exception] = []

        def add_records() -> None:
            try:
                for i in range(100):
                    report.record(step="t", action="x", source=f"/f{i}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=add_records) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert report.total == 500
