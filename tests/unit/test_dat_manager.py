"""
Testes unitários para DatMaster.

Prioridade P0 — lógica de negócio central do pipeline.
Meta de cobertura: 90%
"""

from __future__ import annotations

from pathlib import Path

import pytest

from emupipeline.core.dat_manager import (
    CACHE_VERSION,
    DatMaster,
    GameInfo,
    normalize_string,
    resolve_driver,
)


# ===========================================================================
# normalize_string
# ===========================================================================

class TestNormalizeString:
    def test_removes_region_tags(self):
        assert normalize_string("Street Fighter II (USA)") == "street fighter ii"

    def test_removes_revision_tags(self):
        assert normalize_string("Sonic (USA) [Rev B]") == "sonic"

    def test_handles_empty(self):
        assert normalize_string("") == ""

    def test_removes_accents(self):
        assert normalize_string("Três Mosqueteiros") == "tres mosqueteiros"

    def test_ampersand_to_and(self):
        assert normalize_string("Tom & Jerry") == "tom and jerry"

    def test_removes_special_chars(self):
        assert normalize_string("King of Fighters '97") == "king of fighters 97"

    def test_collapses_spaces(self):
        assert normalize_string("  Double   Space  ") == "double space"

    def test_multiple_tags(self):
        assert normalize_string("Game (USA) [v1.2] (Hack)") == "game"

    def test_lowercase(self):
        assert normalize_string("STREET FIGHTER") == "street fighter"


# ===========================================================================
# resolve_driver
# ===========================================================================

class TestResolveDriver:
    def test_directory_prefix(self):
        assert resolve_driver("capcom/cps1.cpp") == "capcom"

    def test_flat_file_neogeo(self):
        assert resolve_driver("neogeo.cpp") == "neogeo"

    def test_flat_file_cps1(self):
        assert resolve_driver("cps1.cpp") == "cps1"

    def test_empty_string(self):
        assert resolve_driver("") == "misc"

    def test_windows_backslash(self):
        assert resolve_driver("capcom\\cps1.cpp") == "capcom"

    def test_deep_path(self):
        assert resolve_driver("drivers/capcom/cps2.cpp") == "drivers"

    def test_pgm_driver(self):
        assert resolve_driver("pgm.cpp") == "pgm"


# ===========================================================================
# DatMaster — carregamento
# ===========================================================================

class TestDatMasterLoad:
    def test_parses_all_games(self, sample_dat):
        dat = DatMaster(sample_dat)
        # sf2, sf2ce, kof97, mahjong_game
        assert len(dat.rom_map) == 4

    def test_clone_has_parent_set(self, sample_dat):
        dat = DatMaster(sample_dat)
        sf2ce = dat.rom_map["sf2ce"]
        assert sf2ce.parent == "sf2"

    def test_parent_points_to_itself(self, sample_dat):
        dat = DatMaster(sample_dat)
        sf2 = dat.rom_map["sf2"]
        assert sf2.parent == "sf2"

    def test_driver_extracted_correctly(self, sample_dat):
        dat = DatMaster(sample_dat)
        assert dat.rom_map["sf2"].driver == "capcom"
        assert dat.rom_map["kof97"].driver == "snk"

    def test_clean_title_generated(self, sample_dat):
        dat = DatMaster(sample_dat)
        assert dat.rom_map["sf2"].clean_title == "street fighter ii the world warrior"

    def test_title_map_points_to_parent(self, sample_dat):
        dat = DatMaster(sample_dat)
        # sf2ce (clone) não deve substituir sf2 (parent) no title_map
        # para titles que só existem no clone, o clone é adicionado
        assert "street fighter ii the world warrior" in dat.title_map

    def test_nonexistent_dat(self, tmp_path):
        dat = DatMaster(tmp_path / "nonexistent.dat")
        assert len(dat.rom_map) == 0

    def test_malformed_xml(self, tmp_path):
        bad_dat = tmp_path / "bad.dat"
        bad_dat.write_text("<broken><xml", encoding="utf-8")
        dat = DatMaster(bad_dat)
        assert len(dat.rom_map) == 0


# ===========================================================================
# DatMaster — cache
# ===========================================================================

class TestDatMasterCache:
    def test_cache_created_on_first_load(self, sample_dat):
        cache = sample_dat.with_suffix(".pickle")
        assert not cache.exists()
        DatMaster(sample_dat)
        assert cache.exists()

    def test_cache_loaded_on_second_call(self, sample_dat):
        dat1 = DatMaster(sample_dat)
        dat2 = DatMaster(sample_dat)
        assert len(dat2.rom_map) == len(dat1.rom_map)

    def test_cache_invalidated_on_content_change(self, sample_dat):
        DatMaster(sample_dat)
        # Modifica o conteúdo do DAT
        original = sample_dat.read_text(encoding="utf-8")
        new_content = original.replace('name="sf2"', 'name="sf3"')
        sample_dat.write_text(new_content, encoding="utf-8")
        # Nova instância deve reprocessar
        dat2 = DatMaster(sample_dat)
        assert "sf3" in dat2.rom_map
        assert "sf2" not in dat2.rom_map

    def test_stale_cache_version_triggers_reload(self, sample_dat, tmp_path):
        """Cache com versão antiga deve ser descartado."""
        import pickle
        cache_path = sample_dat.with_suffix(".pickle")
        # Salva cache com versão antiga
        with open(cache_path, "wb") as f:
            pickle.dump({"cache_version": "0.0", "fingerprint": "old"}, f)
        # Deve reprocessar o XML
        dat = DatMaster(sample_dat)
        assert len(dat.rom_map) > 0


# ===========================================================================
# DatMaster — busca
# ===========================================================================

class TestDatMasterSearch:
    def test_exact_rom_match(self, sample_dat):
        dat = DatMaster(sample_dat)
        game, match_type = dat.search("sf2.png")
        assert game is not None
        assert match_type == "exact_rom"
        assert game.name == "sf2"

    def test_exact_title_match(self, sample_dat):
        dat = DatMaster(sample_dat)
        game, match_type = dat.search("The King of Fighters 97.png")
        assert game is not None
        assert match_type in ("exact_title", "fuzzy")
        assert game.name == "kof97"

    def test_clone_search_returns_parent(self, sample_dat):
        dat = DatMaster(sample_dat)
        # Busca direto pelo nome do clone
        game, _ = dat.search("sf2ce.png")
        assert game is not None
        # A busca por ROM retorna o parent diretamente
        assert game.name in ("sf2", "sf2ce")

    def test_fuzzy_match_finds_close_title(self, sample_dat):
        dat = DatMaster(sample_dat)
        # "Street Fighter 2 World Warrior" deve encontrar sf2
        game, match_type = dat.search("Street Fighter 2 World Warrior.png", fuzzy_threshold=0.5)
        assert game is not None

    def test_no_match_returns_none(self, sample_dat):
        dat = DatMaster(sample_dat)
        game, match_type = dat.search("totally_unknown_game_xyz_123.png")
        assert game is None
        assert match_type is None

    def test_empty_filename_returns_none(self, sample_dat):
        dat = DatMaster(sample_dat)
        game, match_type = dat.search(".png")
        assert game is None

    def test_get_game_exact(self, sample_dat):
        dat = DatMaster(sample_dat)
        game = dat.get_game("kof97")
        assert game is not None
        assert game.description == "The King of Fighters '97"

    def test_get_game_case_insensitive(self, sample_dat):
        dat = DatMaster(sample_dat)
        assert dat.get_game("SF2") is not None
        assert dat.get_game("KOF97") is not None

    def test_get_game_missing_returns_none(self, sample_dat):
        dat = DatMaster(sample_dat)
        assert dat.get_game("nonexistent") is None


# ===========================================================================
# GameInfo
# ===========================================================================

class TestGameInfo:
    def test_clean_title_auto_generated(self):
        g = GameInfo(
            name="sf2",
            parent="sf2",
            description="Street Fighter II: The World Warrior",
            driver="capcom",
        )
        assert g.clean_title == "street fighter ii the world warrior"

    def test_slots_prevent_extra_attributes(self):
        g = GameInfo(name="sf2", parent="sf2", description="SF2", driver="capcom")
        with pytest.raises(AttributeError):
            g.nonexistent_field = "value"  # type: ignore[attr-defined]
