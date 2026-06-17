"""
Testes unitários para ConfigLoader e config_schema.

Prioridade P0.
Meta de cobertura: 85%
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml


class TestConfigLoader:
    def test_loads_valid_config(self, config_factory, tmp_project):
        cfg = config_factory()
        assert cfg.get("global", "threads") == 2

    def test_base_dir_is_path(self, config_factory, tmp_project):
        cfg = config_factory()
        assert isinstance(cfg.base_dir, Path)
        assert cfg.base_dir == tmp_project

    def test_paths_are_absolute(self, config_factory):
        cfg = config_factory()
        dat = cfg.get("paths", "dat_file")
        assert Path(str(dat)).is_absolute()

    def test_get_section_returns_object(self, config_factory):
        cfg = config_factory()
        videos = cfg.get("videos")
        assert videos is not None
        assert hasattr(videos, "crf")

    def test_get_default_for_missing_key(self, config_factory):
        cfg = config_factory()
        val = cfg.get("global", "nonexistent_key", "default_value")
        assert val == "default_value"

    def test_singleton_returns_same_instance(self, config_factory):
        cfg1 = config_factory()
        import emupipeline.core.config as m
        cfg2 = m.cfg
        assert cfg1 is cfg2

    def test_reload_resets_singleton(self, config_factory, monkeypatch):
        cfg = config_factory()
        import emupipeline.core.config as m
        first_id = id(m.ConfigLoader._instance)
        m.ConfigLoader._instance = None
        # Re-importa
        cfg2 = m.cfg
        # Após reload, instâncias diferentes mas config igual
        assert cfg2.get("global", "threads") == 2

    def test_env_variable_config_path(self, tmp_project, monkeypatch):
        config_data = {
            "global": {"base_dir": str(tmp_project), "threads": 3},
            "paths": {
                "dat_file": str(tmp_project / "dats" / "test.dat"),
                "input_roms": str(tmp_project / "source" / "roms"),
                "input_imgs": str(tmp_project / "source" / "images"),
                "output_roms": str(tmp_project / "output" / "roms"),
                "output_imgs": str(tmp_project / "output" / "images"),
                "output_xml": str(tmp_project / "output" / "gamelist.xml"),
                "output_dats": str(tmp_project / "output" / "dats"),
                "output_reports": str(tmp_project / "output" / "reports"),
                "output_logs": str(tmp_project / "output" / "logs"),
            },
        }
        cfg_path = tmp_project / "alt_config.yaml"
        cfg_path.write_text(yaml.dump(config_data), encoding="utf-8")
        monkeypatch.setenv("EMUPIPELINE_CONFIG", str(cfg_path))

        import emupipeline.core.config as m
        m.ConfigLoader._instance = None
        cfg = m.ConfigLoader()
        assert cfg.get("global", "threads") == 3

    def test_missing_config_raises(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EMUPIPELINE_CONFIG", str(tmp_path / "nonexistent.yaml"))
        import emupipeline.core.config as m
        m.ConfigLoader._instance = None
        with pytest.raises(FileNotFoundError):
            m.ConfigLoader()


class TestConfigSchemaValidation:
    def test_invalid_crf_type_raises(self, config_factory, tmp_project, monkeypatch):
        """crf deve ser inteiro — string deve falhar na inicialização."""
        import emupipeline.core.config as m
        m.ConfigLoader._instance = None

        config = {
            "global": {"base_dir": str(tmp_project), "threads": 2},
            "paths": {
                "dat_file": str(tmp_project / "dats" / "test.dat"),
                "input_roms": str(tmp_project / "source" / "roms"),
                "input_imgs": str(tmp_project / "source" / "images"),
                "output_roms": str(tmp_project / "output" / "roms"),
                "output_imgs": str(tmp_project / "output" / "images"),
                "output_xml": str(tmp_project / "output" / "gamelist.xml"),
                "output_dats": str(tmp_project / "output" / "dats"),
                "output_reports": str(tmp_project / "output" / "reports"),
                "output_logs": str(tmp_project / "output" / "logs"),
            },
            "videos": {"crf": "twenty_eight"},  # INVÁLIDO
        }
        cfg_path = tmp_project / "bad_config.yaml"
        cfg_path.write_text(yaml.dump(config), encoding="utf-8")
        monkeypatch.setenv("EMUPIPELINE_CONFIG", str(cfg_path))
        m.ConfigLoader._instance = None

        with pytest.raises(SystemExit):
            m.ConfigLoader()

    def test_invalid_fuzzy_threshold_raises(self, tmp_project, monkeypatch):
        import emupipeline.core.config as m
        m.ConfigLoader._instance = None

        config = {
            "global": {"base_dir": str(tmp_project), "threads": 2},
            "paths": {
                "dat_file": str(tmp_project / "dats" / "test.dat"),
                "input_roms": str(tmp_project / "source" / "roms"),
                "input_imgs": str(tmp_project / "source" / "images"),
                "output_roms": str(tmp_project / "output" / "roms"),
                "output_imgs": str(tmp_project / "output" / "images"),
                "output_xml": str(tmp_project / "output" / "gamelist.xml"),
                "output_dats": str(tmp_project / "output" / "dats"),
                "output_reports": str(tmp_project / "output" / "reports"),
                "output_logs": str(tmp_project / "output" / "logs"),
            },
            "images": {"fuzzy_threshold": 1.5},  # INVÁLIDO: > 1.0
        }
        cfg_path = tmp_project / "bad_config2.yaml"
        cfg_path.write_text(yaml.dump(config), encoding="utf-8")
        monkeypatch.setenv("EMUPIPELINE_CONFIG", str(cfg_path))
        m.ConfigLoader._instance = None

        with pytest.raises(SystemExit):
            m.ConfigLoader()
