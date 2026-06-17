"""
Fixtures globais para todos os testes.

Design:
  - config_factory: cria config.yaml mínimo em tmp_path e aponta o singleton
  - sample_dat: DAT XML com 3 jogos (sf2 parent, sf2ce clone, kof97)
  - tmp_project: estrutura de diretórios do projeto
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Cria estrutura mínima de diretórios do projeto."""
    for d in [
        "dats", "source/roms", "source/images", "source/videos",
        "output/roms", "output/images", "output/dats",
        "output/reports", "output/logs",
    ]:
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


@pytest.fixture
def sample_dat(tmp_project: Path) -> Path:
    """DAT XML mínimo com 3 jogos para testes."""
    content = textwrap.dedent("""\
        <?xml version="1.0"?>
        <datafile>
          <header><n>TestDAT</n><version>1.0</version></header>
          <game name="sf2" sourcefile="capcom/cps1.cpp">
            <description>Street Fighter II: The World Warrior</description>
            <rom name="sf2.zip" size="1000" crc="deadbeef"/>
          </game>
          <game name="sf2ce" cloneof="sf2" sourcefile="capcom/cps1.cpp">
            <description>Street Fighter II': Champion Edition</description>
            <rom name="sf2ce.zip" size="900" crc="cafebabe"/>
          </game>
          <game name="kof97" sourcefile="snk/neogeo.cpp">
            <description>The King of Fighters '97</description>
            <rom name="kof97.zip" size="2000" crc="12345678"/>
          </game>
          <game name="mahjong_game" sourcefile="misc.cpp">
            <description>Super Mahjong Tournament</description>
            <rom name="mahjong.zip" size="500" crc="aabbccdd"/>
          </game>
        </datafile>
    """)
    dat_path = tmp_project / "dats" / "test.dat"
    dat_path.write_text(content, encoding="utf-8")
    return dat_path


@pytest.fixture
def config_factory(tmp_project: Path, monkeypatch: pytest.MonkeyPatch):
    """
    Fábrica de config.yaml para testes.

    Uso:
        def test_foo(config_factory):
            cfg = config_factory()          # config padrão
            cfg = config_factory({"videos": {"crf": 20}})  # com override
    """
    def _make(overrides: dict | None = None) -> object:
        base = tmp_project

        config: dict = {
            "global": {
                "base_dir":           str(base),
                "logging_level":      "DEBUG",
                "threads":            2,
                "structured_logging": False,
            },
            "paths": {
                "dat_file":       str(base / "dats" / "test.dat"),
                "catver_ini":     str(base / "dats" / "catver.ini"),
                "input_roms":     str(base / "source" / "roms"),
                "input_imgs":     str(base / "source" / "images"),
                "output_roms":    str(base / "output" / "roms"),
                "output_imgs":    str(base / "output" / "images"),
                "output_xml":     str(base / "output" / "gamelist.xml"),
                "output_dats":    str(base / "output" / "dats"),
                "output_reports": str(base / "output" / "reports"),
                "output_logs":    str(base / "output" / "logs"),
                "videos_dir":     str(base / "source" / "videos"),
                "upscale_input":  str(base / "source" / "images"),
                "upscale_output": str(base / "output" / "upscaled"),
                "bin_waifu2x":    "/usr/bin/false",
                "bin_realesrgan": "/usr/bin/false",
            },
            "roms": {
                "enable_igir":         False,
                "split_by_driver":     True,
                "exclude_clones":      True,
                "generate_bios_file":  False,
                "blacklist":           ["mahjong"],
                "merge_mode":          "nonmerged",
                "filter_regions":      "WORLD,USA",
                "threads_io":          2,
            },
            "images": {
                "organization_mode": "subfolders",
                "mode":              "copy",
                "overwrite":         False,
                "fuzzy_threshold":   0.80,
                "valid_extensions":  [".png", ".jpg", ".jpeg", ".webp"],
            },
            "webp": {
                "quality":           85,
                "delete_original":   False,   # seguro para testes
                "source_extensions": [".png", ".jpg"],
            },
            "videos": {
                "codec":           "libx265",
                "crf":             28,
                "preset":          "fast",
                "delete_original": False,   # seguro para testes
                "smart_skip":      True,
                "extensions":      [".mp4", ".avi"],
            },
            "upscale": {
                "engine":        None,
                "scale":         2,
                "output_format": "webp",
                "workers":       1,
                "post_process":  False,
            },
            "compare": {"output_dir": "output/common_files", "copy_common": False},
            "ports": {
                "source_dir":         str(base / "ports"),
                "output_dir":         str(base / "output" / "ports_launchers"),
                "windows_runner":     "wine",
                "enable_gamemode":    False,
                "enable_mangohud":    False,
                "windows_extensions": [".exe"],
                "windows_environment": {},
            },
        }

        if overrides:
            for section, values in overrides.items():
                if isinstance(values, dict) and section in config:
                    config[section].update(values)
                else:
                    config[section] = values

        cfg_path = tmp_project / "config.yaml"
        cfg_path.write_text(yaml.dump(config), encoding="utf-8")
        monkeypatch.setenv("EMUPIPELINE_CONFIG", str(cfg_path))

        # Reseta o singleton e atualiza a variável de módulo para que
        # importações via `from emupipeline.core.config import cfg`
        # recebam a nova instância que lê o arquivo de config correto.
        import emupipeline.core.config as cfg_module
        cfg_module.ConfigLoader._instance = None
        new_cfg = cfg_module.ConfigLoader()   # lê o novo config.yaml via EMUPIPELINE_CONFIG
        cfg_module.cfg = new_cfg              # atualiza referência do módulo
        return cfg_module.cfg

    return _make
