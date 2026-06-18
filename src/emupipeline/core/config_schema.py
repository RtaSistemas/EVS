"""
Validação do config.yaml via Pydantic v2.

Usa Pydantic quando disponível; fallback para validação manual mínima
se não instalado (sem quebrar a aplicação).

Mensagem de erro sempre amigável — sem tracebacks técnicos expostos.

    pip install emupipeline[validation]   # para Pydantic completo
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

try:
    from pydantic import BaseModel, Field, field_validator
    from pydantic.functional_validators import AfterValidator
    from typing import Annotated
    _PYDANTIC = True
except ImportError:  # pragma: no cover
    _PYDANTIC = False


def _expand_path(v: Any) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(str(v)))).resolve()


# ===========================================================================
# SCHEMAS PYDANTIC (quando disponível)
# ===========================================================================
if _PYDANTIC:

    ExpandedPath = Annotated[Path, AfterValidator(_expand_path)]
    CrfValue     = Annotated[int,   Field(ge=0,   le=51)]
    FuzzyThresh  = Annotated[float, Field(ge=0.0, le=1.0)]
    Quality      = Annotated[int,   Field(ge=1,   le=100)]
    ThreadCount  = Annotated[int,   Field(ge=1,   le=64)]

    class GlobalConfig(BaseModel):
        base_dir:           ExpandedPath = Field(default=Path("~/emupipeline"))
        logging_level:      str          = Field(default="INFO",
                                            pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
        threads:            ThreadCount  = 4
        structured_logging: bool         = False

    class PathsConfig(BaseModel):
        dat_file:       ExpandedPath
        catver_ini:     Optional[ExpandedPath] = None
        input_roms:     ExpandedPath
        input_imgs:     ExpandedPath
        output_roms:    ExpandedPath
        output_imgs:    ExpandedPath
        output_xml:     ExpandedPath
        output_dats:    ExpandedPath
        output_reports: ExpandedPath
        output_logs:    ExpandedPath
        videos_dir:     Optional[ExpandedPath] = None
        upscale_input:  Optional[ExpandedPath] = None
        upscale_output: Optional[ExpandedPath] = None
        bin_waifu2x:    Optional[ExpandedPath] = None
        bin_realesrgan: Optional[ExpandedPath] = None

    class RomsConfig(BaseModel):
        enable_igir:        bool       = True
        split_by_driver:    bool       = True
        combined_filename:  str        = "FBNeo_Optimized.dat"
        organize_subfolders:bool       = True
        merge_mode:         str        = Field(default="nonmerged",
                                            pattern="^(nonmerged|split|merged)$")
        filter_regions:     str        = "WORLD,USA"
        threads_io:         int        = Field(default=4, ge=1, le=16)
        generate_bios_file: bool       = False
        bios_filename:      str        = "00_BIOS_Global.dat"
        exclude_clones:     bool       = True
        blacklist:          list[str]  = Field(default_factory=list)

    class ImagesConfig(BaseModel):
        organization_mode: str       = Field(default="subfolders",
                                         pattern="^(subfolders|flat)$")
        mode:              str       = Field(default="symlink",
                                         pattern="^(symlink|copy)$")
        overwrite:         bool      = False
        fuzzy_threshold:   FuzzyThresh = 0.80
        valid_extensions:  list[str] = Field(default=[".png",".jpg",".jpeg",".gif",".webp"])

        @field_validator("valid_extensions")
        @classmethod
        def normalize_extensions(cls, v: list[str]) -> list[str]:
            return [e if e.startswith(".") else f".{e}" for e in v]

    class WebpConfig(BaseModel):
        quality:           Quality    = 85
        delete_original:   bool       = True
        source_extensions: list[str]  = Field(default=[".png",".jpg",".jpeg",".bmp"])

    class VideosConfig(BaseModel):
        codec:           str       = Field(default="libx265",
                                       pattern="^(libx265|libx264)$")
        crf:             CrfValue  = 28
        preset:          str       = Field(default="fast",
                                       pattern="^(ultrafast|superfast|veryfast|faster|fast|medium|slow|slower|veryslow)$")
        delete_original: bool      = True
        smart_skip:      bool      = True
        extensions:      list[str] = Field(default=[".mp4",".avi",".mkv",".mov",".webm"])

    class UpscaleConfig(BaseModel):
        engine:        Optional[str] = None
        scale:         int           = 2
        output_format: str           = Field(default="webp", pattern="^(png|jpg|webp)$")
        workers:       int           = Field(default=2, ge=1, le=8)
        recursive:     bool          = False
        post_process:  bool          = True
        unsharp:       str           = "0x1.0+1.0+0.02"
        noise:         str           = "0.5"

        @field_validator("scale")
        @classmethod
        def must_be_2_or_4(cls, v: int) -> int:
            if v not in (2, 4):
                raise ValueError("scale deve ser 2 ou 4")
            return v

        @field_validator("engine")
        @classmethod
        def valid_engine(cls, v: Optional[str]) -> Optional[str]:
            if v is not None and v not in ("waifu2x", "realesrgan"):
                raise ValueError("engine deve ser 'waifu2x' ou 'realesrgan'")
            return v

    class CompareConfig(BaseModel):
        output_dir:  str  = "output/common_files"
        copy_common: bool = True

    class PortsConfig(BaseModel):
        source_dir:           ExpandedPath    = Field(default=Path("~/Emulation/ports"))
        output_dir:           ExpandedPath    = Field(default=Path("~/Emulation/tools/ports_launchers"))
        rename_plus_folders:  bool            = False
        windows_runner:       str             = "wine"
        enable_gamemode:      bool            = False
        enable_mangohud:      bool            = False
        windows_extensions:   list[str]       = Field(default=[".exe"])
        windows_environment:  dict[str, str]  = Field(default_factory=dict)

    class ConfigSchema(BaseModel):
        global_:  GlobalConfig  = Field(alias="global", default_factory=GlobalConfig)
        paths:    PathsConfig
        roms:     RomsConfig    = Field(default_factory=RomsConfig)
        images:   ImagesConfig  = Field(default_factory=ImagesConfig)
        webp:     WebpConfig    = Field(default_factory=WebpConfig)
        videos:   VideosConfig  = Field(default_factory=VideosConfig)
        upscale:  UpscaleConfig = Field(default_factory=UpscaleConfig)
        compare:  CompareConfig = Field(default_factory=CompareConfig)
        ports:    PortsConfig   = Field(default_factory=PortsConfig)
        model_config = {"populate_by_name": True}

    def load_and_validate(path: Path, raw: dict) -> ConfigSchema:
        from pydantic import ValidationError
        try:
            return ConfigSchema.model_validate(raw)
        except ValidationError as exc:
            lines = [f"\n❌  ERRO DE CONFIGURAÇÃO em {path.name}\n"]
            for err in exc.errors():
                loc = " → ".join(str(x) for x in err["loc"])
                lines.append(f"  Campo : {loc}")
                lines.append(f"  Valor : {err.get('input', '(não fornecido)')!r}")
                lines.append(f"  Erro  : {err['msg']}\n")
            raise SystemExit("\n".join(lines)) from None

# ===========================================================================
# FALLBACK SEM PYDANTIC — validação mínima manual
# ===========================================================================
else:  # pragma: no cover

    def _fail(field: str, value: Any, msg: str) -> None:
        raise SystemExit(
            f"\n❌  ERRO DE CONFIGURAÇÃO\n"
            f"  Campo : {field}\n  Valor : {value!r}\n  Erro  : {msg}\n\n"
            f"  Instale Pydantic para validação completa:\n"
            f"    pip install emupipeline[validation]\n"
        )

    class _NS:
        """Namespace simples que expõe atributos de um dict."""
        def __init__(self, d: dict, base: Path | None = None) -> None:
            for k, v in d.items():
                if isinstance(v, str) and base:
                    if not v.startswith("/") and not v.startswith("~"):
                        v = str((base / v).resolve())
                    setattr(self, k, _expand_path(v))
                else:
                    setattr(self, k, v)
        def __getattr__(self, name: str) -> None:
            raise AttributeError(name)

    class ConfigSchema:  # type: ignore[no-redef]
        def __init__(self, raw: dict) -> None:
            g = raw.get("global", {})
            base = _expand_path(g.get("base_dir", "~/emupipeline"))

            threads = g.get("threads", 4)
            if not isinstance(threads, int) or not (1 <= threads <= 64):
                _fail("global.threads", threads, "deve ser inteiro entre 1 e 64")

            crf = raw.get("videos", {}).get("crf", 28)
            if not isinstance(crf, int) or not (0 <= crf <= 51):
                _fail("videos.crf", crf, "deve ser inteiro entre 0 e 51")

            ft = raw.get("images", {}).get("fuzzy_threshold", 0.80)
            if not isinstance(ft, (int, float)) or not (0.0 <= ft <= 1.0):
                _fail("images.fuzzy_threshold", ft, "deve ser float entre 0.0 e 1.0")

            self.global_ = _NS({**g, "base_dir": base})
            self.paths   = _NS(raw.get("paths", {}), base)
            self.roms    = _NS(raw.get("roms",   {}))
            self.images  = _NS(raw.get("images", {}))
            self.webp    = _NS(raw.get("webp",   {}))
            self.videos  = _NS(raw.get("videos", {}))
            self.upscale = _NS(raw.get("upscale",{}))
            self.compare = _NS(raw.get("compare",{}))
            self.ports   = _NS(raw.get("ports",  {}))

    def load_and_validate(path: Path, raw: dict) -> ConfigSchema:  # type: ignore[misc]
        return ConfigSchema(raw)
