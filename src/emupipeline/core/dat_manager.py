"""
DatMaster v5 — Parser e índice de DATs XML (FBNeo/MAME).

Melhorias em relação à v4:
  - Hash MD5 64KB substituído por SHA-256 híbrido (primeiros 512KB + últimos 64KB)
    → detecta adições no final do XML, que é onde FBNeo adiciona novos jogos
  - CACHE_VERSION: bump invalida cache automaticamente após mudança de schema
  - normalize_string() e resolve_driver() permanecem como funções de módulo
    para reutilização em steps
"""

from __future__ import annotations

import difflib
import hashlib
import pickle
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from emupipeline.core.logger import setup_logger

log = setup_logger("DatMaster")

# Bump quando GameInfo ou o formato do cache mudar
CACHE_VERSION = "5.0"


# ---------------------------------------------------------------------------
# Funções utilitárias de módulo (reutilizáveis em steps)
# ---------------------------------------------------------------------------

def normalize_string(text: str) -> str:
    """
    Normaliza título para comparação case-insensitive sem tags regionais.

    'Street Fighter II (USA) [Rev B]' → 'street fighter ii'
    """
    if not text:
        return ""
    text = re.sub(r"\s*[\(\[].*?[\)\]]", "", text)
    text = unicodedata.normalize("NFKD", text).encode("ASCII", "ignore").decode("ASCII")
    text = text.lower().replace("&", "and")
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def resolve_driver(sourcefile: str) -> str:
    """
    Determina o grupo a partir do atributo sourcefile do DAT.

    'capcom/cps1.cpp' → 'capcom'
    'neogeo.cpp'      → 'neogeo'
    ''                → 'misc'
    """
    if not sourcefile:
        return "misc"
    sf = sourcefile.replace("\\", "/")
    if "/" in sf:
        return sf.split("/")[0]
    stem = sf.split(".")[0]
    _ALIASES = {
        "cps1": "cps1", "cps2": "cps2", "cps3": "cps3",
        "neogeo": "neogeo", "pgm": "pgm", "cave": "cave",
    }
    for key, val in _ALIASES.items():
        if key in stem:
            return val
    return stem or "misc"


# ---------------------------------------------------------------------------
# Modelo de dados
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class GameInfo:
    name:        str   # ROM name lowercase
    parent:      str   # nome do parent (ou próprio se raiz)
    description: str   # título legível original
    driver:      str   # grupo/driver
    clean_title: str = field(init=False)

    def __post_init__(self) -> None:
        self.clean_title = normalize_string(self.description)


# ---------------------------------------------------------------------------
# DatMaster
# ---------------------------------------------------------------------------

class DatMaster:
    """
    Carrega DAT XML, constrói índices em memória e responde consultas.

    Índices:
      rom_map   : {rom_name_lower: GameInfo}
      title_map : {clean_title:   GameInfo}   (aponta para parent)
      _bigrams  : {bigram: set[title]}        (aceleração fuzzy)
    """

    def __init__(self, dat_path: str | Path) -> None:
        self.dat_path    = Path(dat_path)
        self._cache_path = self.dat_path.with_suffix(".pickle")
        self.rom_map:   dict[str, GameInfo]       = {}
        self.title_map: dict[str, GameInfo]       = {}
        self._bigrams:  dict[str, set[str]]       = defaultdict(set)
        self._load()

    # ------------------------------------------------------------------
    # Fingerprint e cache
    # ------------------------------------------------------------------

    def _fingerprint(self) -> str:
        """
        SHA-256 híbrido: mtime + tamanho + início + fim do arquivo.

        Para DATs FBNeo/MAME:
          - Novos jogos são adicionados ao FINAL do XML
          - Hash só do início (v4) ignoraria essas adições
        """
        stat = self.dat_path.stat()
        h = hashlib.sha256()
        h.update(f"{stat.st_size}:{stat.st_mtime_ns}".encode())

        with open(self.dat_path, "rb") as f:
            if stat.st_size < 10 * 1024 * 1024:
                h.update(f.read())           # < 10MB: hash completo
            else:
                h.update(f.read(512 * 1024)) # primeiros 512KB
                f.seek(-65536, 2)
                h.update(f.read())           # últimos 64KB

        return h.hexdigest()

    def _load(self) -> None:
        if self._cache_path.exists():
            try:
                with open(self._cache_path, "rb") as f:
                    cached = pickle.load(f)
                if (cached.get("cache_version") == CACHE_VERSION
                        and cached.get("fingerprint") == self._fingerprint()):
                    log.info("Cache válido — carregamento instantâneo.")
                    self.rom_map   = cached["rom_map"]
                    self.title_map = cached["title_map"]
                    self._bigrams  = cached["bigrams"]
                    return
                log.info("Cache desatualizado — reconstruindo índices…")
            except Exception as exc:
                log.warning(f"Cache inválido ({exc}), reconstruindo…")

        self._parse_xml()

    def _parse_xml(self) -> None:
        if not self.dat_path.exists():
            log.error(f"DAT não encontrado: {self.dat_path}")
            return

        log.info(f"Lendo XML: {self.dat_path.name} …")
        try:
            raw = self.dat_path.read_bytes()
            raw = raw.lstrip(b"\xef\xbb\xbf").replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            log.error(f"Erro de parse XML: {exc}")
            return

        for machine in root:
            if machine.tag not in ("game", "machine"):
                continue
            name = machine.get("name")
            if not name:
                continue

            clone_of  = machine.get("cloneof")
            parent    = clone_of.lower() if clone_of else name.lower()
            desc_el   = machine.find("description")
            desc      = desc_el.text if desc_el is not None else name
            driver    = resolve_driver(machine.get("sourcefile", ""))

            game = GameInfo(
                name=name.lower(), parent=parent,
                description=desc,  driver=driver,
            )
            self.rom_map[game.name] = game

            # title_map prioriza o parent
            if game.clean_title and (
                game.clean_title not in self.title_map or not clone_of
            ):
                self.title_map[game.clean_title] = game

        self._build_bigram_index()
        self._save_cache()
        log.info(f"Índice: {len(self.rom_map)} ROMs, {len(self.title_map)} títulos.")

    def _build_bigram_index(self) -> None:
        self._bigrams = defaultdict(set)
        for title in self.title_map:
            for bg in self._bigrams_of(title):
                self._bigrams[bg].add(title)

    @staticmethod
    def _bigrams_of(s: str) -> list[str]:
        padded = f" {s} "
        return [padded[i:i+2] for i in range(len(padded) - 1)]

    def _save_cache(self) -> None:
        try:
            with open(self._cache_path, "wb") as f:
                pickle.dump({
                    "cache_version": CACHE_VERSION,
                    "fingerprint":   self._fingerprint(),
                    "rom_map":       self.rom_map,
                    "title_map":     self.title_map,
                    "bigrams":       self._bigrams,
                }, f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as exc:
            log.warning(f"Não foi possível salvar cache: {exc}")

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def get_game(self, name: str) -> Optional[GameInfo]:
        return self.rom_map.get(name.lower())

    def search(
        self,
        filename: str,
        fuzzy_threshold: float = 0.80,
    ) -> tuple[Optional[GameInfo], Optional[str]]:
        """
        Busca em 3 camadas: exata ROM → exata título → fuzzy.
        Retorna (GameInfo, match_type) ou (None, None).
        """
        stem = normalize_string(Path(filename).stem)
        if not stem:
            return None, None

        # 1. Match exato pelo nome da ROM
        if stem in self.rom_map:
            game = self.rom_map[stem]
            return self.rom_map.get(game.parent, game), "exact_rom"

        # 2. Match exato pelo título limpo
        if stem in self.title_map:
            return self.title_map[stem], "exact_title"

        # 3. Fuzzy com pré-filtragem por bi-gramas
        candidates = self._fuzzy_candidates(stem, fuzzy_threshold)
        if candidates:
            best = max(
                candidates,
                key=lambda t: difflib.SequenceMatcher(None, stem, t).ratio(),
            )
            return self.title_map[best], "fuzzy"

        return None, None

    def _fuzzy_candidates(self, stem: str, threshold: float) -> list[str]:
        stem_bgs = set(self._bigrams_of(stem))
        if not stem_bgs:
            return []

        scores: dict[str, int] = defaultdict(int)
        for bg in stem_bgs:
            for title in self._bigrams.get(bg, set()):
                scores[title] += 1

        n_stem = len(stem_bgs)
        rough = [
            t for t, cnt in scores.items()
            if cnt / (n_stem + len(self._bigrams_of(t)) - cnt) >= 0.5
        ]
        return [
            t for t in rough
            if difflib.SequenceMatcher(None, stem, t).ratio() >= threshold
        ]
