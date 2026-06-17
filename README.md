# EmuPipeline v5.0

> **Pipeline Python 3.10+ modular para padronização, organização e otimização de bibliotecas de emulação**
> Plataforma alvo: Bazzite / Linux · EmuDeck · Steam Deck · FBNeo / MAME Arcade

[![CI](https://github.com/rtasistemas/evs/actions/workflows/ci.yml/badge.svg)](https://github.com/rtasistemas/evs/actions)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Steps](https://img.shields.io/badge/pipeline%20steps-12-green)](#6-steps-do-pipeline)
[![Tests](https://img.shields.io/badge/testes-170%2B-brightgreen)](#10-testes)

---

## Índice

1. [Visão Geral](#1-visão-geral)
2. [Arquitetura do Sistema](#2-arquitetura-do-sistema)
3. [Fluxo do Pipeline](#3-fluxo-do-pipeline)
4. [Requisitos e Instalação](#4-requisitos-e-instalação)
5. [Configuração — config.yaml](#5-configuração--configyaml)
6. [Steps do Pipeline](#6-steps-do-pipeline)
7. [Módulos Core](#7-módulos-core)
8. [Modos de Execução](#8-modos-de-execução)
9. [CLI — Interface de Linha de Comando](#9-cli--interface-de-linha-de-comando)
10. [Testes](#10-testes)
11. [Troubleshooting](#11-troubleshooting)
12. [Glossário](#12-glossário)

---

## 1. Visão Geral

O **EmuPipeline** automatiza todas as etapas para montar uma biblioteca de emulação organizada, padronizada e otimizada — do DAT XML bruto até o `gamelist.xml` pronto para o EmulationStation.

### O problema que resolve

```
ANTES                              DEPOIS
─────────────────────────          ─────────────────────────────────
ROMs espalhadas sem padrão    →    ROMs organizadas por driver/sistema
Imagens com nomes variados    →    Imagens renomeadas e linkadas ao ROM
PNGs pesados e lentos         →    WebP otimizado (≈70% menor)
Vídeos sem codec padrão       →    H.265/H.264 com smart-skip
Sem gamelist.xml              →    gamelist.xml para EmulationStation
Launchers de ports manuais    →    .desktop automático com gamemode/wine
```

### Capacidades principais

| Capacidade | Tecnologia |
|---|---|
| Organização de ROMs | IGIR + DAT XML |
| Match de imagens | Fuzzy search (bigram + SequenceMatcher) |
| Conversão de imagens | Pillow (ProcessPool — bypassa GIL) |
| Upscaling | waifu2x / Real-ESRGAN + ImageMagick |
| Otimização de vídeo | ffmpeg + ffprobe smart-skip |
| Metadados | gamelist.xml EmulationStation |
| Ports/Launchers | .desktop + autorun.sh (Linux/Wine) |
| Execução segura | DRY_RUN / AUDIT sem I/O real |
| Atomicidade | StagingTransaction (sem arquivos corrompidos) |

---

## 2. Arquitetura do Sistema

### 2.1 Visão de camadas

```mermaid
graph TB
    subgraph CLI["🖥️  CLI (cli.py)"]
        MENU[Menu Interativo]
        PIPE[Pipeline Automático]
        ARGS[Argumentos --config / --dry-run / --audit]
    end

    subgraph REGISTRY["📦  Registry (registry.py)"]
        AUTO[Auto-discovery pkgutil]
        PLUG[Plugin entry_points]
        DEC["@register decorator"]
    end

    subgraph STEPS["🔧  Steps (12 módulos)"]
        direction LR
        S1[DatSplitter]
        S2[RomManager]
        S3[ImageOrganizer]
        S4[WebPConverter]
        S5[VideoOptimizer]
        S6[MetadataGenerator]
        S7[KpiReporter]
        S8[Upscaler]
        S9[PortsAutomator]
        S10[RomValidator]
        S11[FolderComparator]
        S12[OriginalCleaner]
    end

    subgraph CORE["⚙️  Core Modules"]
        CFG[ConfigLoader\nSingleton + Pydantic]
        DAT[DatMaster\nParser + Fuzzy Index]
        PROC[BaseProcessor\nThreadPool / ProcessPool]
        MODE[ExecutionMode\nNORMAL / DRY_RUN / AUDIT]
        TXN[StagingTransaction\nAtomic writes]
        AUDIT[AuditReport\nThread-safe log]
        ENV[EnvironmentChecker\nDependency validator]
    end

    CLI --> REGISTRY
    REGISTRY --> STEPS
    STEPS --> CORE
    PROC --> TXN
    MODE --> AUDIT

    style CLI fill:#1a1a2e,color:#e0e0e0,stroke:#4a90d9
    style REGISTRY fill:#16213e,color:#e0e0e0,stroke:#4a90d9
    style STEPS fill:#0f3460,color:#e0e0e0,stroke:#4a90d9
    style CORE fill:#533483,color:#e0e0e0,stroke:#9b59b6
```

### 2.2 Diagrama de classes principal

```mermaid
classDiagram
    class StepProtocol {
        <<Protocol>>
        +meta: StepMeta
        +run(**kwargs) None
        +get_stats() dict
    }

    class StepMeta {
        +id: str
        +menu_number: int
        +label: str
        +group: str
        +description: str
        +requires_dat: bool
        +pipeline_order: int
    }

    class BaseProcessor {
        <<Abstract>>
        +name: str
        +config: ConfigLoader
        +_mode: ExecutionMode
        +_audit: AuditReport
        +_stats: dict
        +run_parallel(files, threads)
        +scan(dir, extensions) list
        +update_stat(key, delta)
        +get_stats() dict
        +process_file(Path)* str
    }

    class ExecutionMode {
        <<Enum>>
        NORMAL
        DRY_RUN
        AUDIT
    }

    class ConfigLoader {
        <<Singleton>>
        -_instance: ConfigLoader
        +base_dir: Path
        +get(section, key, default) Any
        -_find_config() Path
        -_load() None
    }

    class DatMaster {
        -rom_map: dict
        -title_map: dict
        -_bigrams: dict
        +search(filename, threshold) GameInfo
        +normalize_string(s) str
    }

    class AuditReport {
        -_entries: list
        -_lock: Lock
        +record(step, action, ...) None
        +export_json() str
        +export_html() str
        +destructive_count: int
    }

    class StagingTransaction {
        -_tmp_dir: Path
        -_ops: list
        +stage(content, dest)
        +commit()
        +rollback()
    }

    BaseProcessor ..|> StepProtocol
    BaseProcessor --> ConfigLoader
    BaseProcessor --> ExecutionMode
    BaseProcessor --> AuditReport
    BaseProcessor --> StagingTransaction
    DatMaster --> StepProtocol : injetado via run(dat=)
    StepMeta --> StepProtocol
```

### 2.3 Sistema de Registry e plugins

```mermaid
flowchart LR
    subgraph Registro
        DEC["@register\ndecorator"]
        REG[_REGISTRY\ndict interno]
        EP["entry_points\n'emupipeline.steps'"]
    end

    subgraph Queries
        GM[get_by_menu_number]
        GA[get_all_steps]
        GP[get_pipeline_steps\npipeline_order < 999]
        GS[get_step by id]
    end

    subgraph Fontes
        INT[Steps internos\npkgutil scan]
        PLG[Plugins externos\npyproject.toml]
    end

    INT --> DEC --> REG
    PLG --> EP --> REG
    REG --> GM & GA & GP & GS
```

---

## 3. Fluxo do Pipeline

### 3.1 Pipeline automático (ordem de execução)

```mermaid
flowchart TD
    START([▶ Início do Pipeline]) --> ENV

    ENV{{"🔍 EnvironmentChecker\nverifica dependências"}}
    ENV -- "falha crítica" --> ABORT([❌ Abort])
    ENV -- "OK" --> S10

    S10["**Step 1** · pipeline_order=10\n🗂️ DatSplitter\nSplit do DAT mestre por driver\nAplica blacklist e filtro de clones"]
    S10 --> S20

    S20["**Step 2** · pipeline_order=20\n📦 RomManager\nChama IGIR para organizar ROMs\n(nonmerged / merged / split)"]
    S20 --> S50

    S50["**Step 5** · pipeline_order=50\n🖼️ ImageOrganizer\nFuzzy match imagens → DAT\nCria symlinks ou cópias"]
    S50 --> S60

    S60["**Step 6** · pipeline_order=60\n🔄 WebPConverter\nPNG/JPG → WebP via Pillow\nProcessPoolExecutor (GIL bypass)"]
    S60 --> S80

    S80["**Step 8** · pipeline_order=80\n🎬 VideoOptimizer\nffprobe smart-skip + ffmpeg H.265\nAtomic write por arquivo"]
    S80 --> S90

    S90["**Step 9** · pipeline_order=90\n📋 MetadataGenerator\ngamelist.xml EmulationStation\nCategoria do catver.ini"]
    S90 --> S100

    S100["**Step 10** · pipeline_order=100\n📊 KpiReporter\nContagem de arquivos + uso de disco\nExporta kpi.csv"]
    S100 --> END

    END([✅ Pipeline concluído])

    style START fill:#27ae60,color:#fff
    style END fill:#27ae60,color:#fff
    style ABORT fill:#e74c3c,color:#fff
    style ENV fill:#f39c12,color:#fff
```

### 3.2 Steps manuais (excluídos do pipeline automático)

```mermaid
flowchart LR
    subgraph MANUAL["🔧 Steps pipeline_order = 999 (manuais)"]
        V["**validate_roms**\nRomValidator\nCompara ROMs locais vs DAT\nGera relatórios missing/extra"]
        C["**compare_folders**\nFolderComparator\nDiferença entre dois diretórios"]
        U["**upscale_images**\nUpscaler\nwaifu2x / Real-ESRGAN\n+ ImageMagick unsharp"]
        P["**ports_launchers**\nPortsAutomator\nLaunchers .desktop + autorun.sh\nLinux / Wine + gamemode"]
        CL["**clean_originals**\nOriginalCleaner\nRemove PNG/JPG após confirmar WebP\n⚠️ Irreversível"]
    end
```

### 3.3 Fluxo de dados de imagens

```mermaid
flowchart LR
    RAW["🗂️ Imagens brutas\n*.png, *.jpg, *.\n(nomes variados)"]

    subgraph MATCH["ImageOrganizer"]
        E1{Extensão\nválida?}
        E2{Match\nexato ROM?}
        E3{Match\nexato título?}
        E4{Fuzzy match\n≥ threshold?}
        LINK["symlink relativo\nou cópia"]
        MISS[unmatched_images.txt]
    end

    subgraph CONV["WebPConverter"]
        PIL[Pillow encode\nqualidade configurável]
        WEBP["*.webp\n(≈70% menor)"]
    end

    subgraph UP["Upscaler (opcional)"]
        ENG{Engine}
        W2X[waifu2x-ncnn-vulkan]
        RESR[realesrgan-ncnn-vulkan]
        MAGICK["ImageMagick\nunsharp mask"]
        OUT2["upscaled/*.webp\n2x / 4x"]
    end

    RAW --> E1
    E1 -- Sim --> E2
    E1 -- Não --> SKIP[skipped_ext]
    E2 -- Sim --> LINK
    E2 -- Não --> E3
    E3 -- Sim --> LINK
    E3 -- Não --> E4
    E4 -- Sim --> LINK
    E4 -- Não --> MISS
    LINK --> PIL --> WEBP
    WEBP --> ENG
    ENG -- waifu2x --> W2X --> MAGICK
    ENG -- realesrgan --> RESR --> MAGICK
    MAGICK --> OUT2
```

### 3.4 Fluxo de otimização de vídeo

```mermaid
flowchart TD
    VIN["🎬 Vídeos de entrada\n*.mp4, *.avi, ..."]

    PROBE["ffprobe\ndetecta codec atual"]

    SKIP{smart_skip\nativado?}
    CODEC{Já é\nh265/h264?}
    ENCODE["ffmpeg\n-c:v libx265 -crf 28\n-preset fast\n-c:a copy"]
    ATOMIC["StagingTransaction\natual → temp → replace"]
    DONE["✅ Vídeo otimizado\nH.265 CRF 28"]
    SKIPPED["⏭️ skipped_codec\n(já está correto)"]
    DEL{delete_original?}
    ORIG_DEL["🗑️ Remove original"]

    VIN --> PROBE --> SKIP
    SKIP -- Sim --> CODEC
    SKIP -- Não --> ENCODE
    CODEC -- Sim --> SKIPPED
    CODEC -- Não --> ENCODE
    ENCODE --> ATOMIC --> DONE --> DEL
    DEL -- Sim --> ORIG_DEL
    DEL -- Não --> FIM([fim])
    ORIG_DEL --> FIM

    style SKIPPED fill:#27ae60,color:#fff
    style ORIG_DEL fill:#e74c3c,color:#fff
```

---

## 4. Requisitos e Instalação

### 4.1 Dependências Python

```bash
pip install emupipeline                  # mínimo
pip install emupipeline[images]          # + Pillow (WebP)
pip install emupipeline[validation]      # + Pydantic v2
pip install emupipeline[kpi]             # + pandas, openpyxl
pip install emupipeline[all]             # tudo
```

### 4.2 Ferramentas externas

| Ferramenta | Versão mínima | Usado por | Obrigatório |
|---|---|---|---|
| Python | 3.10 | tudo | ✅ |
| ffmpeg | qualquer | VideoOptimizer | apenas vídeo |
| ffprobe | qualquer | VideoOptimizer smart-skip | apenas vídeo |
| igir | 1.8+ | RomManager | apenas ROMs |
| ImageMagick | 7+ (`magick`) | Upscaler pós-proc | opcional |
| waifu2x-ncnn-vulkan | qualquer | Upscaler | opcional |
| realesrgan-ncnn-vulkan | qualquer | Upscaler | opcional |

### 4.3 Instalação rápida

```bash
# Clone
git clone https://github.com/rtasistemas/evs.git
cd evs

# Instale em modo editável (desenvolvimento)
pip install -e ".[all]"

# Copie e ajuste o config de exemplo
cp config.yaml.example config.yaml
$EDITOR config.yaml

# Verifique o ambiente
emupipeline --check-env

# Execute o pipeline completo
emupipeline --pipeline
```

---

## 5. Configuração — config.yaml

### 5.1 Estrutura de seções

```mermaid
mindmap
  root((config.yaml))
    global
      base_dir
      logging_level
      threads
      structured_logging
    paths
      dat_file
      catver_ini
      input_roms
      input_imgs
      output_roms
      output_imgs
      output_xml
      output_dats
      output_reports
      output_logs
      videos_dir
      upscale_input
      upscale_output
      bin_waifu2x
      bin_realesrgan
    roms
      enable_igir
      split_by_driver
      merge_mode
      filter_regions
      exclude_clones
      blacklist
      threads_io
    images
      mode symlink|copy
      organization_mode
      fuzzy_threshold
      valid_extensions
    webp
      quality
      delete_original
      source_extensions
    videos
      codec
      crf
      preset
      delete_original
      smart_skip
      extensions
    upscale
      engine
      scale
      output_format
      workers
      post_process
      unsharp
    compare
      output_dir
      copy_common
    ports
      source_dir
      output_dir
      windows_runner
      enable_gamemode
      enable_mangohud
      windows_extensions
      windows_environment
```

### 5.2 config.yaml completo comentado

```yaml
global:
  base_dir: ~/emupipeline        # raiz — todos os paths relativos resolvem aqui
  logging_level: INFO            # DEBUG | INFO | WARNING | ERROR
  threads: 4                     # workers padrão (1-64)
  structured_logging: false      # true → JSON lines para ingestão em log system

paths:
  dat_file: ./FBNeo.dat          # DAT XML mestre (FBNeo, MAME, Redump…)
  catver_ini: ./catver.ini       # Categorias de jogos (usado em gamelist.xml)
  input_roms: ~/roms_input       # ROMs brutas (fonte)
  input_imgs: ~/images_input     # Imagens brutas (fonte)
  output_roms: ~/roms_organized  # ROMs após IGIR
  output_imgs: ~/images_organized
  output_xml: ~/gamelist.xml
  output_dats: ~/dats_split      # DATs por driver gerados pelo DatSplitter
  output_reports: ~/reports
  output_logs: ~/logs
  videos_dir: ~/videos
  upscale_input: ~/images_organized   # entrada do upscaler
  upscale_output: ~/images_upscaled   # saída do upscaler
  bin_waifu2x: /opt/waifu2x/waifu2x-ncnn-vulkan
  bin_realesrgan: /opt/realesrgan/realesrgan-ncnn-vulkan

roms:
  enable_igir: true
  split_by_driver: true          # divide DAT por sourcefile (driver)
  merge_mode: nonmerged          # nonmerged | merged | split
  filter_regions: "WORLD,USA"    # regiões mantidas; vazio = todas
  exclude_clones: true           # remove jogos com <cloneof>
  generate_bios_file: false      # inclui entradas de BIOS
  blacklist:                     # ROMs cujo driver contém esses termos são removidos
    - adult
    - mahjong
    - quiz
  threads_io: 4                  # threads do IGIR

images:
  mode: symlink                  # symlink | copy
  organization_mode: subfolders  # subfolders (por driver) | flat
  overwrite: false
  fuzzy_threshold: 0.80          # [0.0-1.0] precisão do match fuzzy
  valid_extensions:
    - .png
    - .jpg
    - .jpeg
    - .gif
    - .webp

webp:
  quality: 85                    # [1-100]
  delete_original: false         # use step clean_originals para deletar
  source_extensions:
    - .png
    - .jpg

videos:
  codec: libx265                 # libx265 | libx264
  crf: 28                        # [0-51] qualidade (menor = melhor)
  preset: fast                   # ultrafast|superfast|veryfast|faster|fast|medium|slow
  delete_original: false
  smart_skip: true               # pula vídeos já no codec correto
  extensions:
    - .mp4
    - .avi
    - .mkv

upscale:
  engine: waifu2x                # waifu2x | realesrgan
  scale: 2                       # 2 | 4
  output_format: webp
  workers: 2                     # processos paralelos do binário
  post_process: true             # aplica unsharp mask via ImageMagick
  unsharp: "0x1.0+1.0+0.02"     # parâmetro -unsharp do ImageMagick

compare:
  output_dir: output/common_files
  copy_common: false

ports:
  source_dir: ~/ports            # cada subdir é um port
  output_dir: ~/ports_launchers  # destino dos .desktop
  windows_runner: wine           # wine | proton | bottles
  enable_gamemode: false         # prefixar com gamemoderun
  enable_mangohud: false         # prefixar com mangohud
  windows_extensions:
    - .exe
    - .bat
  windows_environment: {}        # WINEPREFIX etc.
```

### 5.3 Resolução de configuração

```mermaid
flowchart LR
    ENV_VAR["$EMUPIPELINE_CONFIG\n(env var)"]
    CWD["./config.yaml\n(diretório atual)"]
    PKG["config.yaml\n(raiz do pacote)"]
    ERR["FileNotFoundError"]

    ENV_VAR -- existe --> LOAD[ConfigLoader.\_load]
    ENV_VAR -- não existe --> CWD
    CWD -- existe --> LOAD
    CWD -- não existe --> PKG
    PKG -- existe --> LOAD
    PKG -- não existe --> ERR

    LOAD --> PYDANTIC{Pydantic v2\ndisponível?}
    PYDANTIC -- Sim --> VAL[Validação completa\ncom tipos e limites]
    PYDANTIC -- Não --> FALLBACK[Validação manual\nmínima]
    VAL & FALLBACK --> SINGLETON[cfg = ConfigLoader()\nSingleton global]
```

---

## 6. Steps do Pipeline

### 6.1 Mapa completo de steps

```mermaid
graph LR
    subgraph ROMS["🗂️ ROMs & DATs"]
        DS["**1** DatSplitter\ndat_split\npipeline_order=10"]
        RM["**2** RomManager\nrom_manager\npipeline_order=20"]
        RV["**3** RomValidator\nvalidate_roms\npipeline_order=999"]
        FC["**4** FolderComparator\ncompare_folders\npipeline_order=999"]
    end

    subgraph IMGS["🖼️ Imagens"]
        IO["**5** ImageOrganizer\norganize_images\npipeline_order=50\nBaseProcessor+DAT"]
        WC["**6** WebPConverter\nconvert_webp\npipeline_order=60\nBaseProcessor+ProcessPool"]
        UP["**7** Upscaler\nupscale_images\npipeline_order=999"]
        OC["**12** OriginalCleaner\nclean_originals\npipeline_order=999\nBaseProcessor"]
    end

    subgraph VID["🎬 Vídeo & Metadados"]
        VO["**8** VideoOptimizer\noptimize_videos\npipeline_order=80\nBaseProcessor"]
        MG["**9** MetadataGenerator\ngenerate_metadata\npipeline_order=90\nrequer DAT"]
        KR["**10** KpiReporter\nkpi_report\npipeline_order=100"]
    end

    subgraph EXTRA["🕹️ Extras"]
        PA["**11** PortsAutomator\nports_launchers\npipeline_order=999"]
    end

    DS -->|"DATs por driver"| RM
    RM -->|"ROMs organizados"| IO
    IO -->|"imagens linkadas"| WC
    WC -->|"*.webp"| UP
    IO --> MG
    WC --> MG
    VO --> MG
    MG -->|"gamelist.xml"| KR

    style ROMS fill:#1a1a2e,color:#e0e0e0,stroke:#3498db
    style IMGS fill:#16213e,color:#e0e0e0,stroke:#9b59b6
    style VID fill:#0f3460,color:#e0e0e0,stroke:#e67e22
    style EXTRA fill:#1a1a2e,color:#e0e0e0,stroke:#2ecc71
```

---

### 6.2 Step 1 — DatSplitter

**Classe:** `DatSplitter` · **ID:** `dat_split` · **Grupo:** ROMs & DATs · **Menu:** 1

Lê o DAT XML mestre e gera um arquivo `.dat` separado por driver de hardware (ex: `capcom.dat`, `snk.dat`). Aplica filtros configuráveis antes de gravar.

```mermaid
flowchart LR
    DAT["FBNeo.dat\n(DAT mestre XML)"]
    PARSE["Parse XML\nLê todos os <game>"]
    BL{Blacklist\nmatch?}
    CL{É clone\n& exclude_clones?}
    DR{split_by_driver?}
    GROUP["Agrupa por\ngame.driver"]
    FLAT["Arquivo único\nall_games.dat"]
    WRITE["Grava *.dat\npor driver"]

    DAT --> PARSE --> BL
    BL -- Sim → exclui --> SKIP1[blacklisted++]
    BL -- Não --> CL
    CL -- Sim → exclui --> SKIP2[clone_excluded++]
    CL -- Não --> DR
    DR -- Sim --> GROUP --> WRITE
    DR -- Não --> FLAT

    WRITE --> STATS["Stats:\ndats_created\nblacklisted\nclone_excluded"]
```

**Configuração relevante:** `roms.split_by_driver`, `roms.blacklist`, `roms.exclude_clones`, `roms.generate_bios_file`

---

### 6.3 Step 2 — RomManager

**Classe:** `RomManager` · **ID:** `rom_manager` · **Grupo:** ROMs & DATs · **Menu:** 2

Invoca o **IGIR** para verificar, renomear e organizar ROMs contra os DATs gerados pelo DatSplitter. Suporta os três modos de merge do MAME.

```mermaid
flowchart TD
    IGIR_CHECK{igir\ndisponível?}
    IGIR_CHECK -- Não --> ERR["error++ / log"]
    IGIR_CHECK -- Sim --> BUILD

    BUILD["Constrói comando IGIR\n--dat ./dats_split/*.dat\n--input input_roms\n--output output_roms\n--merge-mode nonmerged\n--region-filter WORLD,USA"]

    RUN["subprocess.run(igir ...)"]
    OK{returncode\n== 0?}
    SUCCESS["success = 1"]
    FAIL["error = 1"]

    BUILD --> RUN --> OK
    OK -- Sim --> SUCCESS
    OK -- Não --> FAIL
```

**Modos de merge:**

| Modo | Descrição |
|---|---|
| `nonmerged` | Cada ROM é um arquivo completo independente |
| `merged` | Parent contém todos os clones dentro |
| `split` | Clones contêm apenas os arquivos diferentes do parent |

---

### 6.4 Step 5 — ImageOrganizer

**Classe:** `ImageOrganizer` · **ID:** `organize_images` · **Grupo:** Imagens · **Menu:** 5

Associa imagens de nomes variados aos ROMs correspondentes no DAT usando três camadas de match progressivo. Cria **symlinks relativos** ou **cópias** na pasta organizada.

```mermaid
flowchart TD
    SCAN["scan(input_imgs)\n*.png, *.jpg, *.jpeg, *.webp"]
    PAR["run_parallel(files)\nThreadPoolExecutor"]

    subgraph MATCH["_match_and_place(file, out_dir)"]
        EXT{Extensão\nválida?}
        E1{Exact ROM\nname match}
        E2{Exact título\nnormalizado}
        E3{"Fuzzy match\n≥ threshold"}
        NOMATCH[no_match]
    end

    PLACE["Destino:\nout_dir/driver/rom_name.ext\nou out_dir/rom_name.ext"]
    OW{Existe\n& overwrite=false?}
    DRY{DRY_RUN?}
    AUDIT{AUDIT?}
    LINK["symlink_to(relpath)"]
    COPY["shutil.copy2"]
    RECORD["AuditReport.record"]

    SCAN --> PAR --> EXT
    EXT -- Não --> SKIP["skipped_ext"]
    EXT -- Sim --> E1
    E1 -- Sim --> PLACE
    E1 -- Não --> E2
    E2 -- Sim --> PLACE
    E2 -- Não --> E3
    E3 -- Sim --> PLACE
    E3 -- Não --> NOMATCH

    PLACE --> OW
    OW -- Sim --> SKIP2["skipped_exists"]
    OW -- Não --> DRY
    DRY -- Sim --> DRY2["dry_run"]
    DRY -- Não --> AUDIT
    AUDIT -- Sim --> RECORD
    AUDIT -- Não --> MODE{mode_img}
    MODE -- symlink --> LINK
    MODE -- copy --> COPY
```

**Normalização para fuzzy match:**
- Remove tags de região: `(USA)`, `[!]`, `(Europe)` etc.
- Lowercase + ASCII-safe
- Remove pontuação e espaços extras
- Índice de bigramas para pré-filtrar candidatos em O(1)

---

### 6.5 Step 6 — WebPConverter

**Classe:** `WebPConverter` · **ID:** `convert_webp` · **Grupo:** Imagens · **Menu:** 6

Converte PNG/JPG em WebP usando Pillow com **ProcessPoolExecutor** (bypassa o GIL do Python para conversão real em paralelo).

```mermaid
flowchart LR
    SCAN["scan(input_imgs)\n*.png, *.jpg"]
    POOL["ProcessPoolExecutor\n(CPU-bound, bypassa GIL)"]
    CHECK{"*.webp já\nexiste?"}
    SKIP["skipped_exists"]
    OPEN["Image.open(src)"]
    CONV["img.save(dest, 'WEBP'\nquality=85)"]
    DONE["converted++"]

    SCAN --> POOL --> CHECK
    CHECK -- Sim --> SKIP
    CHECK -- Não --> OPEN --> CONV --> DONE
```

> **Por que ProcessPool?** Pillow é CPU-bound (compressão de imagem). O GIL do CPython impede paralelismo real com threads — o ProcessPool resolve isso criando processos separados.

---

### 6.6 Step 7 — Upscaler

**Classe:** `Upscaler` · **ID:** `upscale_images` · **Grupo:** Imagens · **Menu:** 7

Aumenta a resolução de imagens 2× ou 4× usando redes neurais. Pós-processa com **ImageMagick unsharp mask** para nitidez. Robusto: erros por imagem são logados individualmente, não abortam o processo.

```mermaid
flowchart TD
    BIN{Binário\nexiste?}
    BIN -- Não --> EARLYRET["retorna (log error)"]
    BIN -- Sim --> IMGS

    IMGS{Imagens\nno diretório?}
    IMGS -- Não --> EARLYRET2["retorna"]
    IMGS -- Sim --> DRYC

    DRYC{DRY_RUN?}
    DRYC -- Sim --> EARLYRET3["retorna (log)"]
    DRYC -- Não --> RUN

    RUN["subprocess.run(\n  [bin, -i input_dir,\n   -o output_dir,\n   -s scale, -f webp,\n   -j workers]\n)"]

    ERR{CalledProcess\nError?}
    ERR -- Sim --> ESTAT["error = 1"]
    ERR -- Não --> PSTAT["processed++"]

    PSTAT --> POST{post_process\n&& magick OK?}
    POST -- Não --> FIM([fim])
    POST -- Sim --> LOOP

    subgraph LOOP["Para cada *.webp no output"]
        MAG["magick img -unsharp\n0x1.0+1.0+0.02 img"]
        MERR{CalledProcess\nError?}
        MERR -- Sim --> WLOG["log.warning(stderr)"]
        MERR -- Não --> MSTAT["post_processed++"]
    end

    RUN --> ERR
    LOOP --> FIM
```

**Stats produzidas:** `processed`, `post_processed`, `error`

---

### 6.7 Step 8 — VideoOptimizer

**Classe:** `VideoOptimizer` · **ID:** `optimize_videos` · **Grupo:** Vídeo & Metadados · **Menu:** 8

Re-encoda vídeos para H.265 (ou H.264) com **ffmpeg**. O modo **smart-skip** usa **ffprobe** para verificar o codec atual e evitar re-encodings desnecessários. Usa `StagingTransaction` para escrita atômica.

```mermaid
sequenceDiagram
    participant V as Vídeo
    participant P as ffprobe
    participant F as ffmpeg
    participant T as StagingTransaction
    participant D as Disco

    V->>P: codec_name?
    P-->>V: hevc / h264 / mpeg4 / ...

    alt smart_skip=true e codec == alvo
        V->>D: skipped_codec (sem mudança)
    else
        V->>T: stage(tmp_file)
        T->>F: -c:v libx265 -crf 28 -preset fast
        F-->>T: tmp_file pronto
        T->>D: rename(tmp → original) atômico
        D-->>V: optimized++
    end
```

**Controle de oversubscription:** O VideoOptimizer divide os `threads` pela metade — metade como workers Python, metade entregue ao ffmpeg via `-threads N`. Isso evita trashing quando muitos ffmpeg rodam em paralelo.

---

### 6.8 Step 9 — MetadataGenerator

**Classe:** `MetadataGenerator` · **ID:** `generate_metadata` · **Grupo:** Vídeo & Metadados · **Menu:** 9

Gera o `gamelist.xml` no formato EmulationStation combinando ROMs, imagens, vídeos e categorias do `catver.ini`.

```mermaid
flowchart TD
    ROMS["output_roms/*.zip"] & IMGS["output_imgs/**"] & CATVER["catver.ini"] & DAT["DatMaster"] --> GEN

    GEN["MetadataGenerator.run()"]

    subgraph XML["gamelist.xml"]
        GAME["<game>\n  <path>./roms/sf2.zip</path>\n  <name>Street Fighter II</name>\n  <image>./images/sf2.png</image>\n  <genre>Versus Fighting</genre>\n  <video>./videos/sf2.mp4</video>\n</game>"]
    end

    GEN --> STAT["Stats: entries"]
    GEN --> XML
```

---

### 6.9 Step 10 — KpiReporter

**Classe:** `KpiReporter` · **ID:** `kpi_report` · **Grupo:** Vídeo & Metadados · **Menu:** 10

Mede e reporta uso de disco e contagem de arquivos em todos os diretórios relevantes do projeto. Exporta `kpi.csv` com `csv.writer` (quoting correto para labels com vírgulas).

**Diretórios analisados:** ROMs entrada, ROMs saída, Imagens entrada, Imagens saída, Vídeos.

---

### 6.10 Step 11 — PortsAutomator

**Classe:** `PortsAutomator` · **ID:** `ports_launchers` · **Grupo:** Extras · **Menu:** 11

Gera launchers para ports (jogos Linux nativos ou Windows via Wine). Para cada subdiretório em `ports.source_dir`, detecta o executável principal e cria `autorun.sh` + `game.desktop`.

```mermaid
flowchart TD
    SCAN["scan(source_dir)\n1 subdir = 1 port"]

    subgraph DETECT["_find_executable(port_dir)"]
        LX["Busca executável Linux\n(bit x, sem extensão .exe)"]
        SH["Busca *.sh"]
        EX["Busca *.exe / *.bat\n(Windows)"]
        NONE["None → skipped_no_exec"]
    end

    subgraph LINUX["Port Linux"]
        LSCRIPT["autorun.sh\n#!/bin/bash\n[gamemoderun] [mangohud]\n./game_executable"]
        LDESK[".desktop\nExec=bash autorun.sh"]
    end

    subgraph WINDOWS["Port Windows"]
        WSCRIPT["autorun.sh\n#!/bin/bash\nexport WINEPREFIX=...\n[gamemoderun] wine ./game.exe"]
        WDESK[".desktop\nExec=bash autorun.sh"]
    end

    SCAN --> DETECT
    LX -- encontrado --> LINUX
    SH -- encontrado --> LINUX
    EX -- encontrado --> WINDOWS
    LINUX & WINDOWS -->|"chmod +x autorun.sh"| WRITE
    WRITE["created++"]

    DETECT -- falhou --> NONE
```

**Wrappers suportados:** `gamemoderun` (CPU governor), `mangohud` (overlay FPS), `wine` / `proton` / `bottles`.

---

### 6.11 Step 12 — OriginalCleaner

**Classe:** `OriginalCleaner` · **ID:** `clean_originals` · **Grupo:** Imagens · **Menu:** 12

> ⚠️ **Operação irreversível** — exclui arquivos PNG/JPG originais. Execute apenas após confirmar que os WebPs estão corretos.

Remove arquivos PNG/JPG **somente se** um `.webp` correspondente de tamanho maior que zero existir no mesmo diretório. Usa `BaseProcessor` com ThreadPool.

---

## 7. Módulos Core

### 7.1 Visão de dependências entre módulos

```mermaid
graph TD
    CLI[cli.py] --> REG[registry.py]
    CLI --> ENV[env_checker.py]
    CLI --> MODE[execution_mode.py]

    REG --> STEPS["steps/*.py"]
    STEPS --> PROC[processor.py]
    STEPS --> CFG[config.py]
    STEPS --> DAT[dat_manager.py]
    STEPS --> MODE

    PROC --> CFG
    PROC --> MODE
    PROC --> TXN[transaction.py]
    PROC --> METRICS[metrics.py]

    CFG --> SCHEMA[config_schema.py]
    CFG --> LOG[logger.py]

    MODE --> AUDIT_MOD["AuditReport\n(em execution_mode.py)"]

    style CLI fill:#e74c3c,color:#fff
    style CFG fill:#f39c12,color:#fff
    style PROC fill:#9b59b6,color:#fff
    style DAT fill:#27ae60,color:#fff
```

### 7.2 ConfigLoader — Singleton e validação

```mermaid
stateDiagram-v2
    [*] --> Uninitialized

    Uninitialized --> Loading : primeira instância\n(ConfigLoader.__new__)
    Loading --> SearchEnv : EMUPIPELINE_CONFIG?
    SearchEnv --> Found : env var existe
    SearchEnv --> SearchCWD : não existe
    SearchCWD --> Found : config.yaml em ./
    SearchCWD --> SearchPkg : não existe
    SearchPkg --> Found : config.yaml no pacote
    SearchPkg --> Error : não existe

    Found --> Validating : _load()
    Validating --> PydanticV2 : pydantic disponível
    Validating --> ManualVal : pydantic ausente
    PydanticV2 --> Ready
    ManualVal --> Ready

    Error --> [*] : FileNotFoundError

    Ready --> Ready : get(section, key)\nretorna do cache
    Ready --> Uninitialized : _instance = None\n(reset em testes)
```

### 7.3 DatMaster — Busca fuzzy de 3 camadas

```mermaid
flowchart TD
    Q["search(filename, threshold)"] --> PREP["Extrai stem:\n'sf2.png' → 'sf2'"]

    PREP --> L1{Layer 1:\nrom_map[stem]}
    L1 -- hit --> R1[("GameInfo\n(exact_rom)")]
    L1 -- miss --> L2

    L2["normalize(stem)"] --> L2C{Layer 2:\ntitle_map[normalized]}
    L2C -- hit --> R2[("GameInfo\n(exact_title)")]
    L2C -- miss --> L3

    L3["bigram_candidates(normalized)\n→ pré-filtra O(1)"] --> SM["SequenceMatcher\nsobre candidatos"]
    SM --> THR{score\n≥ threshold?}
    THR -- Sim --> R3[("GameInfo\n(fuzzy)")]
    THR -- Não --> R4[("None\n(no_match)")]
```

**Hash híbrido do DAT** (para cache):
- Lê 512 KB do início + 64 KB do fim do arquivo
- Detecta adições ao final (frequentes em atualizações do FBNeo)
- Cache pickled com version + fingerprint — invalida automaticamente quando o DAT muda

### 7.4 StagingTransaction — Atomicidade

```mermaid
sequenceDiagram
    participant S as Step
    participant T as StagingTransaction
    participant FS as Sistema de Arquivos

    S->>T: __enter__()
    Note over T: cria tmp_dir em TMPDIR

    loop para cada arquivo
        S->>T: stage(content, dest_path)
        T->>FS: escreve em tmp_dir/hash
    end

    S->>T: commit()
    loop para cada (tmp, dest)
        T->>FS: os.replace(tmp → dest)\n[atômico no mesmo FS]
        Note over T: fallback: shutil.copy2\n+ unlink se cross-FS
    end
    T-->>S: OK

    alt Exceção
        S->>T: __exit__(exc)
        T->>T: rollback()
        T->>FS: rmtree(tmp_dir)
    end
```

### 7.5 ExecutionMode e AuditReport

```mermaid
stateDiagram-v2
    direction LR
    [*] --> NORMAL : padrão
    [*] --> DRY_RUN : --dry-run
    [*] --> AUDIT : --audit

    state NORMAL {
        [*] --> IO_Real
        IO_Real : Leitura + Escrita\nnormais
    }

    state DRY_RUN {
        [*] --> Simula
        Simula : log.debug "would do X"\nZero I/O
    }

    state AUDIT {
        [*] --> Grava
        Grava : AuditReport.record()\nZero I/O de dados
        Grava --> Export : fim do step
        Export : JSON / HTML\n(summary impresso)
    }
```

---

## 8. Modos de Execução

| Modo | Flag CLI | I/O real | Arquivo gerado | Uso |
|---|---|---|---|---|
| `NORMAL` | *(padrão)* | ✅ | — | Produção |
| `DRY_RUN` | `--dry-run` | ❌ | — | Validar antes de executar |
| `AUDIT` | `--audit` | ❌ | `audit_report.json` + `.html` | Revisão de operações destrutivas |

### Injeção de modo nos steps

```python
# CLI instancia cada step com o modo correto
upscaler = Upscaler(mode=ExecutionMode.DRY_RUN)
upscaler.run()
# → nenhum subprocess é chamado, nenhum arquivo criado
```

O modo é passado ao construtor — nunca modificado externamente (sem monkey-patching). Isso garante thread-safety e testabilidade.

---

## 9. CLI — Interface de Linha de Comando

```mermaid
flowchart TD
    START(["emupipeline [options]"]) --> PARSE["argparse\n--config, --dry-run,\n--audit, --pipeline,\n--check-env, --step N"]

    PARSE --> CHECK_ENV{--check-env?}
    CHECK_ENV -- Sim --> ENV_REPORT["EnvironmentChecker.report()\nimprime tabela de deps"]
    CHECK_ENV -- Não --> LOAD_CFG

    LOAD_CFG["ConfigLoader()\n(singleton via env ou CWD)"]

    LOAD_CFG --> PIPE{--pipeline?}
    PIPE -- Sim --> AUTO["get_pipeline_steps()\nordenado por pipeline_order"]
    PIPE -- Não --> STEP{--step N?}
    STEP -- Sim --> ONE["get_by_menu_number(N)"]
    STEP -- Não --> MENU["Menu interativo\n(grupos + numeração)"]

    AUTO & ONE --> EXEC
    MENU -->|"usuário escolhe"| EXEC

    EXEC["Instancia step(mode=mode, audit=audit)\nChama step.run(**kwargs)\nImprime get_stats()"]
```

### Exemplos de uso

```bash
# Pipeline completo em modo real
emupipeline --pipeline

# Simular o pipeline sem modificar nada
emupipeline --pipeline --dry-run

# Auditar apenas a organização de imagens
emupipeline --step 5 --audit

# Usar config alternativo
emupipeline --config /path/to/custom.yaml --pipeline

# Verificar dependências do ambiente
emupipeline --check-env

# Menu interativo
emupipeline
```

---

## 10. Testes

### 10.1 Estrutura de testes

```
tests/
├── conftest.py              # fixtures globais
│   ├── tmp_project          # dirs do projeto em tmp_path
│   ├── sample_dat           # DAT XML mínimo (4 jogos)
│   └── config_factory       # fábrica de config.yaml isolado
├── unit/
│   ├── test_config.py       # ConfigLoader + Pydantic
│   ├── test_dat_manager.py  # DatMaster busca 3 camadas
│   ├── test_execution_mode.py # AuditReport thread-safety
│   ├── test_transaction.py  # StagingTransaction atomicidade
│   └── test_steps/
│       ├── test_organize.py # ImageOrganizer fuzzy match
│       ├── test_upscale.py  # Upscaler subprocess + ImageMagick
│       ├── test_ports.py    # PortsAutomator launchers
│       ├── test_optimize.py # VideoOptimizer smart-skip
│       └── test_dat_split.py
└── integration/
    └── test_pipeline_smoke.py
```

### 10.2 Padrões de teste

```mermaid
flowchart LR
    subgraph FIXTURES["Fixtures (conftest.py)"]
        TMP["tmp_project\ncria estrutura de dirs\nem tmp_path"]
        DAT["sample_dat\nDAT XML com 4 jogos\n(sf2, sf2ce, kof97, mahjong)"]
        CFG["config_factory\ncria config.yaml\nreseta singleton\natualiza cfg_module.cfg"]
    end

    subgraph ISOLAÇÃO["Isolação de Singleton"]
        RST["cfg_module.ConfigLoader._instance = None"]
        NEW["new_cfg = ConfigLoader()\n(lê EMUPIPELINE_CONFIG)"]
        UPD["cfg_module.cfg = new_cfg\n⚠️ crítico: atualiza referência\ndo módulo processor.py"]
    end

    subgraph MOCK["Mocking (unittest.mock)"]
        SP["patch('subprocess.run')\ncontrola chamadas externas"]
        SW["patch('shutil.which')\nsimula presença de magick"]
        BIN["_REAL_BIN = '/usr/bin/false'\n(existe no Linux)"]
    end

    CFG --> ISOLAÇÃO
    MOCK --> TESTS["170+ testes\n✅ passando"]
```

### 10.3 Executar os testes

```bash
# Todos os testes com cobertura
pytest --cov=emupipeline --cov-report=html

# Apenas steps críticos
pytest tests/unit/test_steps/ -v

# Um step específico
pytest tests/unit/test_steps/test_upscale.py -v

# Sem cobertura (mais rápido)
pytest --no-cov -v
```

---

## 11. Troubleshooting

### Diagnóstico rápido

```mermaid
flowchart TD
    ERR["❌ Problema"]

    ERR --> T1{FileNotFoundError\nconfig.yaml}
    T1 --> S1["export EMUPIPELINE_CONFIG=/path/to/config.yaml\nou rode do diretório com config.yaml"]

    ERR --> T2{igir não\nencontrado}
    T2 --> S2["npm install -g igir\nou adicione ao PATH"]

    ERR --> T3{ffmpeg error\nnão converte}
    T3 --> S3["sudo dnf install ffmpeg\nVerifique: ffmpeg -version"]

    ERR --> T4{magick: command\nnot found}
    T4 --> S4["sudo dnf install ImageMagick\nVerifique: magick --version"]

    ERR --> T5{Upscaler:\nbinário não encontrado}
    T5 --> S5["Verifique paths.bin_waifu2x\nou paths.bin_realesrgan em config.yaml"]

    ERR --> T6{Imagens não\nmatched}
    T6 --> S6["Reduza images.fuzzy_threshold\n(ex: 0.70)\nVeja reports/unmatched_images.txt"]
```

### Variáveis de ambiente úteis

| Variável | Uso |
|---|---|
| `EMUPIPELINE_CONFIG` | Caminho alternativo para `config.yaml` |
| `EMUPIPELINE_LOG_LEVEL` | Override de nível de log (DEBUG/INFO/WARNING) |

---

## 12. Glossário

| Termo | Definição |
|---|---|
| **DAT** | Arquivo XML descrevendo ROMs com checksums (CRC/SHA1). Mantido por projetos como FBNeo, MAME, Redump |
| **Driver** | Código emulador de hardware (`sourcefile` no DAT, ex: `capcom/cps1.cpp`) |
| **IGIR** | Ferramenta Node.js para organizar e verificar ROMs contra DATs |
| **Fuzzy match** | Comparação aproximada de strings usando bigramas + SequenceMatcher |
| **Smart-skip** | Verificação do codec atual do vídeo antes de re-encodar |
| **CRF** | Constant Rate Factor — controla qualidade/tamanho no ffmpeg (0=melhor, 51=pior) |
| **Nonmerged** | Modo ROM onde cada jogo tem todos os arquivos necessários independentemente |
| **Symlink relativo** | Link simbólico cujo caminho é relativo ao diretório destino (portável) |
| **StagingTransaction** | Padrão write-to-temp + atomic-rename para evitar arquivos corrompidos |
| **AuditReport** | Registro de operações planejadas sem I/O real (modo AUDIT) |
| **Pipeline order** | Número que define a ordem de execução automática dos steps |
| **Bigram index** | Índice de pares de caracteres para busca fuzzy eficiente |
| **ProcessPool** | Pool de processos separados que bypassam o GIL do Python |
| **Blacklist** | Lista de termos que excluem ROMs (ex: `adult`, `mahjong`) |
| **Clone** | ROM derivado de um parent, com modificações (ex: `sf2ce` cloneof `sf2`) |
| **gamelist.xml** | Formato de metadados do EmulationStation para frontend de emulação |
| **Oversubscription** | Excesso de threads/processos causando degradação de desempenho |

---

## Contribuindo

```bash
# Setup de desenvolvimento
pip install -e ".[all]"
pre-commit install

# Rodar testes antes de commitar
pytest --no-cov -v

# Verificar formatação
ruff check src/ tests/
```

Pull requests são bem-vindos. Veja [CONTRIBUTING.md](CONTRIBUTING.md) para o guia completo.

---

<div align="center">

**EmuPipeline v5.0** — feito com ❤️ para a comunidade de emulação

[Issues](https://github.com/rtasistemas/evs/issues) · [Releases](https://github.com/rtasistemas/evs/releases) · [CHANGELOG](CHANGELOG.md)

</div>
