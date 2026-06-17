# EmuPipeline v5.0

> **Pipeline Python 3 modular para padronização e organização de bibliotecas de emulação**
> Plataforma alvo: Bazzite / Linux · EmuDeck · FBNeo / MAME Arcade

[![CI](https://github.com/emupipeline/emupipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/emupipeline/emupipeline/actions)
[![Coverage](https://codecov.io/gh/emupipeline/emupipeline/badge.svg)](https://codecov.io/gh/emupipeline/emupipeline)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://python.org)
[![PyPI](https://img.shields.io/pypi/v/emupipeline)](https://pypi.org/project/emupipeline/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Índice

1. [Visão Geral](#1-visão-geral)
2. [Arquitetura do Projeto](#2-arquitetura-do-projeto)
3. [Requisitos e Instalação](#3-requisitos-e-instalação)
4. [Configuração — config.yaml](#4-configuração--configyaml)
5. [Como Usar](#5-como-usar)
6. [Steps do Pipeline](#6-steps-do-pipeline)
7. [Biblioteca Core](#7-biblioteca-core)
8. [Fluxo de Dados Completo](#8-fluxo-de-dados-completo)
9. [Referência Completa de config.yaml](#9-referência-completa-de-configyaml)
10. [Testes](#10-testes)
11. [Troubleshooting](#11-troubleshooting)
12. [Glossário](#12-glossário)
13. [Contribuindo e Roadmap](#13-contribuindo-e-roadmap)

---

## 1. Visão Geral

O EmuPipeline automatiza todas as etapas necessárias para montar uma biblioteca de emulação organizada, padronizada e otimizada:

```
DAT Mestre (XML)  ──►  Split por driver  ──►  IGIR organiza ROMs
                                                      │
Imagens brutas   ──►  Fuzzy match DAT   ──►  Pasta organizada
                                                      │
                                        ──►  Conversão WebP
                                        ──►  Upscaling (opcional)

Vídeos brutos    ──►  Smart-skip codec  ──►  H.265 otimizado

Tudo junto       ──►  gamelist.xml      ──►  EmulationStation
```

### O que o pipeline resolve

| Problema | Solução |
|---|---|
| Imagens com nomes incompatíveis com os ROMs | Fuzzy match com índice de bi-gramas (3 camadas) |
| Imagens PNG/JPG ocupando espaço excessivo | Conversão WebP com integridade verificada antes de deletar |
| Imagens com resolução baixa | Upscaling com waifu2x ou Real-ESRGAN via Vulkan |
| Vídeos em formatos variados e pesados | Reencoding H.265 com smart-skip e atomic write |
| DAT único difícil de usar com IGIR | Split automático por driver (cps1, neogeo…) |
| Romset desorganizado ou com extras | Validação e organização via IGIR |
| Metadados ausentes no EmulationStation | Geração de gamelist.xml com gêneros via catver.ini |
| Config inválido descoberto tarde | Validação Pydantic v2 na inicialização, erros amigáveis |
| Ferramenta ausente descoberta tarde | EnvironmentChecker com fail-fast antes do pipeline |
| Falha corrompendo dados parcialmente | StagingTransaction + commit atômico + rollback automático |

---

## 2. Arquitetura do Projeto

```
emupipeline/
│
├── pyproject.toml               ← empacotamento, deps, linters, pytest
├── config.yaml.example          ← template (copie para config.yaml)
├── README.md
├── CHANGELOG.md
├── CONTRIBUTING.md
│
├── src/
│   └── emupipeline/             ← pacote instalável via pip
│       ├── __init__.py          ← expõe __version__ = "5.0.0"
│       ├── cli.py               ← entry point: comando `emupipeline`
│       │
│       ├── core/                ← biblioteca interna (não editar)
│       │   ├── config.py        ConfigLoader singleton
│       │   ├── config_schema.py Schema Pydantic v2 (fallback manual sem Pydantic)
│       │   ├── dat_manager.py   Parser XML · Cache SHA-256 · Fuzzy search
│       │   ├── env_checker.py   Verificação de dependências (fail-fast)
│       │   ├── execution_mode.py ExecutionMode enum + AuditReport thread-safe
│       │   ├── logger.py        Fábrica de loggers (console + JSON estruturado)
│       │   ├── metrics.py       Métricas por step (throughput, compressão)
│       │   ├── processor.py     BaseProcessor thread-safe + executor configurável
│       │   ├── registry.py      StepRegistry com autodiscover + plugins externos
│       │   ├── step_interface.py StepMeta + StepProtocol (Protocol estrutural)
│       │   └── transaction.py   StagingTransaction + atomic_write
│       │
│       └── steps/               ← 12 módulos de steps
│           ├── step_dat_split.py    Split DAT por driver
│           ├── step_rom_manager.py  Wrapper IGIR
│           ├── step_validate.py     Validação romset vs DAT
│           ├── step_compare.py      Comparação de diretórios
│           ├── step_organize.py     Organização de imagens (fuzzy match)
│           ├── step_convert.py      PNG/JPG → WebP (ProcessPoolExecutor)
│           ├── step_clean.py        Deleção de originais (com confirmação explícita)
│           ├── step_upscale.py      waifu2x / Real-ESRGAN
│           ├── step_optimize.py     FFmpeg H.265 (atomic_write)
│           ├── step_metadata.py     gamelist.xml
│           ├── step_kpi.py          Relatório de uso de disco
│           └── step_ports.py        Launchers .desktop
│
└── tests/
    ├── conftest.py              fixtures globais
    ├── fixtures/
    │   ├── minimal.dat          DAT com 10 jogos de teste
    │   └── catver.ini
    ├── unit/                    testes sem ferramentas externas
    │   ├── test_config.py
    │   ├── test_dat_manager.py
    │   ├── test_execution_mode.py
    │   ├── test_env_checker.py
    │   ├── test_processor.py
    │   ├── test_transaction.py
    │   └── test_steps/
    │       ├── test_convert.py
    │       ├── test_dat_split.py
    │       ├── test_optimize.py
    │       └── test_organize.py
    └── integration/
        └── test_pipeline_smoke.py
```

### Princípios de design

**Sem estado global mutável.** Cada step é uma instância isolada. O modo de execução (`NORMAL`/`DRY_RUN`/`AUDIT`) é injetado via construtor — nunca via monkey-patch de variável de classe.

**Transações atômicas.** Operações destrutivas usam `StagingTransaction` ou `atomic_write`. O destino final só é escrito após validação completa. Falhas fazem rollback automático.

**Responsabilidade única.** `WebPConverter` converte. `OriginalCleaner` deleta. São steps distintos com confirmação explícita na deleção.

**Fail-fast.** `EnvironmentChecker` verifica ffmpeg, igir e ferramentas relevantes antes do primeiro step — não após 40 minutos de processamento.

**Extensível.** Novos steps são adicionados com um decorator `@register` e aparecem automaticamente no menu. Plugins externos usam `entry_points` do setuptools.

**Configuração centralizada.** `config.yaml` controla tudo. Nenhum arquivo `.py` precisa ser editado para uso normal.

---

## 3. Requisitos e Instalação

### 3.1 Python

Requer **Python 3.10 ou superior.**

```bash
python3 --version   # Python 3.10+
```

### 3.2 Instalação via pip

```bash
# Mínima
pip install emupipeline

# Completa (recomendado)
pip install emupipeline[full]

# Verificar
emupipeline --version
```

| Extra | Instala | Necessário para |
|---|---|---|
| `[images]` | Pillow | Conversão WebP (step 6) |
| `[kpi]` | pandas, openpyxl | Relatório KPI formatado (step 10) |
| `[validation]` | pydantic | Validação completa de config.yaml |
| `[full]` | tudo acima | Instalação completa |
| `[dev]` | + pytest, ruff, mypy | Desenvolvimento |

### 3.3 Instalação para desenvolvimento

```bash
git clone https://github.com/emupipeline/emupipeline.git
cd emupipeline
pip install -e ".[dev]"
pre-commit install
```

### 3.4 Ferramentas do sistema

#### FFmpeg (obrigatório para step_optimize)
```bash
sudo dnf install ffmpeg          # Fedora / Bazzite
sudo apt install ffmpeg          # Ubuntu / Debian
ffmpeg -version && ffprobe -version
```

#### IGIR (obrigatório para step_rom_manager)
```bash
node --version                   # precisa ser >= 18
npm install -g igir
igir --version
```

Se `npm` não está no PATH:
```bash
echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

#### ImageMagick 7+ (opcional — pós-processamento de upscaling)
```bash
sudo dnf install ImageMagick
magick -version                  # deve retornar "Version: ImageMagick 7.x"
```

> **Atenção:** o comando é `magick` (v7), não `convert` (v6). No Ubuntu pode ser necessário compilar manualmente ou usar `imagemagick-7`.

#### Upscalers (opcionais — requerem GPU com Vulkan)

| Engine | Repositório | Ideal para |
|---|---|---|
| waifu2x-ncnn-vulkan | [github.com/nihui/waifu2x-ncnn-vulkan](https://github.com/nihui/waifu2x-ncnn-vulkan/releases) | Arte 2D, pixel art, retro |
| realesrgan-ncnn-vulkan | [github.com/xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN/releases) | Fotos, renders 3D, capas |

Descompacte em `~/Applications/` e configure `config.yaml → paths.bin_waifu2x`.

### 3.5 Configuração inicial

```bash
cp config.yaml.example config.yaml
nano config.yaml
# Ajuste: global.base_dir, paths.dat_file, paths.input_roms, paths.input_imgs

emupipeline --check-env          # verifica todas as dependências antes de rodar
```

---

## 4. Configuração — config.yaml

O `config.yaml` é o **único arquivo que você precisa editar.** Todos os comportamentos do pipeline são controlados por ele.

### Localização do config

O sistema busca o `config.yaml` nesta ordem:

1. Variável de ambiente: `EMUPIPELINE_CONFIG=/caminho/config.yaml`
2. Diretório de trabalho atual (`./config.yaml`)
3. Diretório raiz do projeto (`emupipeline/config.yaml`)

### Expansão de caminhos

O sistema expande automaticamente:

- `~` → home do usuário (`/home/seu_usuario`)
- Caminhos relativos na seção `paths` → relativos ao `global.base_dir`

```yaml
global:
  base_dir: "~/Documents/emupipeline"

paths:
  dat_file: "dats/FinalBurn Neo.dat"
  # Resulta em: ~/Documents/emupipeline/dats/FinalBurn Neo.dat
```

### Validação automática (com Pydantic)

Com `pip install emupipeline[validation]`, erros de tipo e range são detectados na inicialização:

```
❌  ERRO DE CONFIGURAÇÃO em config.yaml

  Campo : videos → crf
  Valor : 'vinte e oito'
  Erro  : Input should be a valid integer

  Campo : images → fuzzy_threshold
  Valor : 1.5
  Erro  : Input should be less than or equal to 1

  Campo : videos → codec
  Valor : 'libx266'
  Erro  : String should match pattern '^(libx265|libx264)$'
```

---

## 5. Como Usar

### Menu interativo

```bash
emupipeline
```

```
╔══════════════════════════════════════════════════════╗
║              EmuPipeline v5.0                       ║
╠══════════════════════════════════════════════════════╣
║  ROMs & DATs                                        ║
║    1. Split DAT por driver (+ filtros)              ║
║    2. Organizar ROMs (IGIR)                         ║
║    3. Validar Romset vs DAT                         ║
║    4. Comparar duas pastas                          ║
╠══════════════════════════════════════════════════════╣
║  Imagens                                            ║
║    5. Organizar imagens (fuzzy match)               ║
║    6. Converter → WebP                              ║
║   12. Limpar originais convertidos                  ║
║    7. Upscaling (waifu2x / Real-ESRGAN)            ║
╠══════════════════════════════════════════════════════╣
║  Vídeo & Metadados                                  ║
║    8. Otimizar vídeos (FFmpeg H.265)                ║
║    9. Gerar gamelist.xml                            ║
║   10. Relatório KPI                                 ║
╠══════════════════════════════════════════════════════╣
║  Extras                                             ║
║   11. Launchers de Ports (.desktop)                 ║
╠══════════════════════════════════════════════════════╣
║   99. PIPELINE COMPLETO (automático)                ║
║    0. Sair                                          ║
╚══════════════════════════════════════════════════════╝
```

### CLI (linha de comando)

```bash
emupipeline --pipeline                        # pipeline completo
emupipeline --step 1                          # step específico
emupipeline --dry-run --pipeline              # simula sem tocar em disco
emupipeline --audit                           # relatório completo, zero escrita
emupipeline --audit --audit-format html       # relatório HTML
emupipeline --check-env                       # verifica dependências externas
emupipeline --config /outro/config.yaml       # config alternativo
emupipeline --help
```

### Diferença entre dry-run e audit

| | `--dry-run` | `--audit` |
|---|---|---|
| Executa lógica de decisão | ❌ Não | ✅ Completa |
| Escreve em disco | ❌ Não | ❌ Não |
| Gera relatório exportável | ❌ Não | ✅ JSON ou HTML |
| Conta arquivos afetados | ❌ Não | ✅ Com breakdown por step |
| Identifica operações destrutivas | ❌ Não | ✅ Marcadas em vermelho |
| Uso típico | Teste rápido | Revisão antes de produção |

### Variável de ambiente

```bash
export EMUPIPELINE_CONFIG=/mnt/externo/config.yaml
emupipeline --pipeline
```

---

## 6. Steps do Pipeline

### Step 1 — Split DAT por driver

**Arquivo:** `steps/step_dat_split.py` | **Menu:** `1` | **CLI:** `--step 1`

Lê o DAT Mestre (XML ClrMame Pro) e gera arquivos DAT menores por driver de hardware, aplicando filtros de blacklist, clones e BIOS.

```
FinalBurn Neo.dat (50.000 jogos)
        │
        ├─► cps1.dat         (Street Fighter II, Final Fight…)
        ├─► cps2.dat         (Marvel vs Capcom, DarkStalkers…)
        ├─► cps3.dat         (Street Fighter III…)
        ├─► neogeo.dat       (King of Fighters, Metal Slug…)
        └─► 00_BIOS_Global.dat  (neogeo.zip, pgm.zip…)
```

O diretório `output/dats_generated/` é **limpo antes** de cada execução. A blacklist é aplicada ao texto da `<description>` do jogo, não ao nome do arquivo ROM.

**Config relevante:** `roms.split_by_driver`, `roms.exclude_clones`, `roms.blacklist`

---

### Step 2 — Organizar ROMs com IGIR

**Arquivo:** `steps/step_rom_manager.py` | **Menu:** `2` | **CLI:** `--step 2`

Executa o [IGIR](https://igir.io) usando os DATs gerados no Step 1 (ou o DAT Mestre como fallback). Verifica integridade (CRC/SHA), renomeia e organiza em subpastas.

```
Existe output/dats_generated/*.dat?
    SIM → usa DATs gerados pelo Step 1 (preferido)
    NÃO → usa o DAT Mestre como fallback (com aviso)
```

**Modos de merge:**

| Modo | Descrição | Espaço |
|---|---|---|
| `nonmerged` | Cada ZIP é independente | Alto — **recomendado para EmuDeck** |
| `split` | Clones referenciam o parent | Médio |
| `merged` | Clones e parent no mesmo ZIP | Baixo |

**Config relevante:** `roms.enable_igir`, `roms.merge_mode`, `roms.organize_subfolders`

---

### Step 3 — Validar Romset vs DAT

**Arquivo:** `steps/step_validate.py` | **Menu:** `3` | **CLI:** `--step 3`

Compara os ROMs locais com o índice do DAT Mestre. Gera relatório em `output/reports/validation_report.txt`:

```
Total no DAT      : 4823
Encontrados       : 4102
Faltantes         : 721
Extras (sem DAT)  : 38
```

---

### Step 4 — Comparar Diretórios

**Arquivo:** `steps/step_compare.py` | **Menu:** `4` | **CLI:** `--step 4`

Operações de conjunto entre duas pastas: lista exclusivos em A, exclusivos em B e arquivos em comum. Opcionalmente copia os arquivos em comum para `output/common_files/`.

> O `output_dir` é **apagado e recriado** a cada execução. Não armazene arquivos importantes ali.

**Config relevante:** `compare.copy_common`, `compare.output_dir`

---

### Step 5 — Organizar Imagens

**Arquivo:** `steps/step_organize.py` | **Menu:** `5` | **CLI:** `--step 5`

Associa imagens brutas a ROMs em **3 camadas de match**:

```
Imagem: "Street Fighter II - The World Warrior (USA).png"
                │
                ▼
1. Match exato pelo nome da ROM
   normalize("Street Fighter II (USA)") → "street fighter ii"
   → não encontrado no rom_map
                │
                ▼
2. Match exato pelo título limpo do DAT
   → encontrado: sf2
   → Saída: output/images/capcom/sf2.png
```

Se nenhuma das duas camadas encontrar, tenta:

```
3. Fuzzy Match (bi-gramas + SequenceMatcher)
   threshold configurável (padrão: 0.80)
   "street fighter ii championship" → sf2ce (ratio: 0.83) → match!
```

Clones são sempre consolidados para o parent — sem duplicação de imagens.

**Modos de saída:**

| Modo | Resultado | Espaço |
|---|---|---|
| `symlink` | Link simbólico relativo | Zero — recomendado para SSD |
| `copy` | Cópia física | Duplica o arquivo |

Arquivos sem match são listados em `output/reports/unmatched_images.txt`.

**Config relevante:** `images.mode`, `images.fuzzy_threshold`, `images.organization_mode`

---

### Step 6 — Converter para WebP

**Arquivo:** `steps/step_convert.py` | **Menu:** `6` | **CLI:** `--step 6`

Converte PNG/JPG para WebP (~70% menos espaço). Usa `ProcessPoolExecutor` para paralelismo real de CPU — não afetado pelo GIL.

**Proteção anti-corrupção:** valida o tamanho do WebP gerado antes de qualquer ação. Arquivos menores que 100 bytes são considerados inválidos e o original é preservado.

**Nota v5:** a deleção dos originais é responsabilidade exclusiva do Step 12. O `WebPConverter` **nunca** apaga arquivos.

**Config relevante:** `webp.quality` (padrão: 85)

---

### Step 12 — Limpar Originais

**Arquivo:** `steps/step_clean.py` | **Menu:** `12` | **CLI:** `--step 12`

Deleta arquivos PNG/JPG que já têm versão WebP correspondente. **Sempre pede confirmação explícita** — nunca incluído no pipeline automático:

```
⚠️  Esta operação irá DELETAR arquivos originais.
   Diretório: ~/source/images
   Confirma? (digite 'DELETAR' para confirmar): _
```

---

### Step 7 — Upscaling de Imagens

**Arquivo:** `steps/step_upscale.py` | **Menu:** `7` | **CLI:** `--step 7`

Aumenta resolução com redes neurais via Vulkan (GPU):

| Engine | Ideal para |
|---|---|
| **waifu2x** | Arte 2D, pixel art, anime, screenshots retro |
| **Real-ESRGAN** | Renders 3D, texturas realistas, fotos de capas digitalizadas |

Pós-processamento opcional com ImageMagick (unsharp mask + ruído gaussiano sutil).

> Requer GPU com Vulkan. Em APUs AMD modernas (Steam Deck, Bazzite) o Vulkan geralmente já está disponível.

**Config relevante:** `upscale.engine`, `upscale.scale` (2 ou 4), `upscale.post_process`

---

### Step 8 — Otimizar Vídeos

**Arquivo:** `steps/step_optimize.py` | **Menu:** `8` | **CLI:** `--step 8`

```
video.avi encontrado
       │
       ▼
smart_skip=true → ffprobe verifica codec atual
       │
       ├─► codec = "hevc"   →  SKIP instantâneo
       │
       └─► codec = "mpeg4"  →  ffmpeg → .tmp_XXXXX.mp4
                                              │
                                    tamanho > 0?
                                              ├─► sim → rename atômico → video.mp4
                                              └─► não → rollback, original intacto
                                              │
                                    delete_original=true → remove video.avi
                                    (SOMENTE após commit bem-sucedido)
```

**Controle de oversubscription:** usa automaticamente `global.threads ÷ 2` workers Python para não competir com os processos ffmpeg filhos.

**Escolha do CRF:**

| CRF | Qualidade | Uso recomendado |
|---|---|---|
| 18-22 | Excelente | Arquivamento, conteúdo HD |
| 23-27 | Bom | Uso geral |
| 28-32 | Razoável | **Retro gaming** (baixa resolução original) |

**Config relevante:** `videos.codec`, `videos.crf`, `videos.smart_skip`, `videos.preset`

---

### Step 9 — Gerar gamelist.xml

**Arquivo:** `steps/step_metadata.py` | **Menu:** `9` | **CLI:** `--step 9`

Gera metadados para **EmulationStation / ES-DE** com paths relativos portáveis:

```xml
<?xml version='1.0' encoding='UTF-8'?>
<gameList>
  <game>
    <path>./roms/cps1/sf2.zip</path>
    <n>Street Fighter II: The World Warrior</n>
    <desc>Driver: cps1
Genre: Fighting / Versus</desc>
    <genre>Fighting</genre>
    <image>./images/cps1/sf2.webp</image>
  </game>
</gameList>
```

O `catver.ini` é opcional mas enriquece os metadados com gêneros. Baixe em: [mameworld.info/catver](http://www.mameworld.info/catver/).

---

### Step 10 — Relatório KPI

**Arquivo:** `steps/step_kpi.py` | **Menu:** `10` | **CLI:** `--step 10`

Contagem de arquivos e uso de disco por diretório. Exporta `output/reports/kpi.csv`.

```
--- KPI REPORT ---
Local                      Arquivos   Tamanho (MB)
ROMs (entrada)                 5201       42381.50
ROMs (saída)                   4102       40112.30
Imagens (entrada)             18423        3201.10
Imagens (saída)               18423         412.80   ← após WebP
Vídeos                         4102        8901.20
```

---

### Step 11 — Launchers de Ports

**Arquivo:** `steps/step_ports.py` | **Menu:** `11` | **CLI:** `--step 11`

Para cada pasta de port, gera `autorun.sh` e `.desktop` com suporte a Wine (jogos Windows), GameMode e MangoHud.

**Estrutura esperada:**
```
ports/
├── DeadCells/
│   └── DeadCells.x86_64     ← executável Linux
└── Stardew_Valley/
    └── Stardew Valley.exe   ← executável Windows (via Wine)
```

**Config relevante:** `ports.windows_runner`, `ports.enable_gamemode`, `ports.windows_environment`

---

### Pipeline Completo (opção 99)

Executa os steps em sequência lógica, pulando os que requerem interação manual:

```
Step 1  → Split DAT          → output/dats_generated/
Step 2  → Organizar ROMs     → output/roms/
Step 5  → Organizar Imagens  → output/images/
Step 6  → Converter WebP     → output/images/ (modo automático)
Step 8  → Otimizar Vídeos    → videos_dir/
Step 9  → gamelist.xml       → output/gamelist.xml
Step 10 → KPI                → output/reports/kpi.csv
```

Em caso de erro, o pipeline pergunta se deve continuar:

```
Erro em 'Organizar ROMs': comando 'igir' não encontrado.
Continuar pipeline? (s/N):
```

---

## 7. Biblioteca Core

### `core/config.py` — ConfigLoader

Singleton que carrega e fornece acesso ao `config.yaml`.

```python
from emupipeline.core.config import cfg

# Lê valor simples
threads = cfg.get("global", "threads")          # → 8

# Lê seção inteira
videos_cfg = cfg.get("videos")                  # → dict da seção

# Lê com default
level = cfg.get("global", "logging_level", "INFO")

# Acessa base_dir resolvido
base = cfg.base_dir                             # → Path("/home/user/emupipeline")

# Config alternativo via ENV
import os
os.environ["EMUPIPELINE_CONFIG"] = "/outro/config.yaml"
cfg.reload()
```

### `core/dat_manager.py` — DatMaster

Parser e índice de arquivos DAT XML com cache automático por SHA-256.

```python
from emupipeline.core.dat_manager import DatMaster

dat = DatMaster("dats/FinalBurn Neo.dat")
# 1ª execução: lê o XML e gera cache .pickle (~2s para 50k jogos)
# Execuções seguintes: carrega o .pickle instantaneamente

# Busca exata por nome ROM
game = dat.get_game("sf2")
# → GameInfo(name="sf2", parent="sf2",
#            description="Street Fighter II…", driver="cps1")

# Busca em 3 camadas (exact_rom → exact_title → fuzzy)
game, match_type = dat.search("Street Fighter II (USA).png")
# → (GameInfo(...), "exact_title")

# Campos do GameInfo
game.name           # "sf2"
game.parent         # "sf2" (ou nome do parent se for clone)
game.description    # "Street Fighter II: The World Warrior"
game.driver         # "cps1"
game.clean_title    # "street fighter ii the world warrior"
```

Para forçar reconstrução do cache:
```bash
rm dats/*.pickle
```

### `core/processor.py` — BaseProcessor

Classe base para todos os steps, com multithreading e stats thread-safe.

```python
from emupipeline.core.processor import BaseProcessor
from emupipeline.core.execution_mode import ExecutionMode, AuditReport
from pathlib import Path

class MeuStep(BaseProcessor):
    def __init__(self, mode=ExecutionMode.NORMAL, audit=None):
        super().__init__("MeuStep")
        self._mode = mode
        self._audit = audit

    def process_file(self, file_path: Path) -> str:
        if self._mode == ExecutionMode.DRY_RUN:
            self.logger.info(f"[DRY] Processaria: {file_path.name}")
            return "dry_run"
        # faça algo...
        return "processed"

    def run(self):
        files = self.scan("/pasta/entrada", extensions={".png", ".jpg"})
        self.run_parallel(files)   # usa threads do config automaticamente
```

Stats automáticos ao final:
```
--- MeuStep concluído em 12.40s ---
  processed            : 1823
  error                : 3
  skipped_exists       : 201
```

### `core/execution_mode.py` — AuditReport

```python
from emupipeline.core.execution_mode import ExecutionMode, AuditReport
from pathlib import Path

report = AuditReport()

# Registrar operação planejada (thread-safe)
report.record(
    step="WebPConverter",
    action="convert_to_webp",
    source="/a/sf2.png",
    dest="/b/sf2.webp",
    would_delete=False,
)

# Consultar
report.total              # → 1
report.destructive_count  # → 0

# Exportar
report.export_json(Path("output/audit.json"))
report.export_html(Path("output/audit.html"))
report.print_summary()
```

### `core/transaction.py` — Operações Atômicas

```python
from emupipeline.core.transaction import atomic_write, StagingTransaction

# Arquivo único — escrita atômica
with atomic_write(Path("output/video.mp4")) as tmp:
    subprocess.run(["ffmpeg", ..., str(tmp)], check=True)
# rename atômico só ocorre se nenhuma exceção foi levantada
# Em erro: tmp é apagado, destino final nunca criado

# Múltiplos arquivos — transação completa
with StagingTransaction(output_dir) as txn:
    for driver, content in dats.items():
        staged = txn.stage_path(f"{driver}.dat")
        staged.write_text(content)
    txn.commit()   # move tudo atomicamente para output_dir
# Se não chamar commit() ou ocorrer exceção → rollback automático
```

### `core/registry.py` — Sistema de Plugins

```python
from emupipeline.core.registry import autodiscover, get_all_steps, get_pipeline_steps

# Carrega todos os steps (internos + plugins externos)
autodiscover()

# Lista todos os steps registrados
steps = get_all_steps()
# → {'dat_split': DatSplitter, 'convert_webp': WebPConverter, ...}

# Steps ordenados para o pipeline automático
pipeline = get_pipeline_steps()
# → [DatSplitter, RomManager, ImageOrganizer, WebPConverter, ...]
```

**Adicionando um plugin externo:**

```toml
# pyproject.toml do seu plugin
[project.entry-points."emupipeline.steps"]
meu_step = "meu_pacote.meu_step:MeuStep"
```

Após `pip install meu-plugin`, o step aparece automaticamente no menu.

---

## 8. Fluxo de Dados Completo

```
ENTRADA
───────
source/
├── roms/                    ← Romset bruto (ZIPs misturados)
│   ├── sf2.zip
│   └── kof97.zip
├── images/                  ← Imagens com nomes variados
│   ├── "Street Fighter II (USA).png"
│   └── "KOF 97.jpg"
└── dats/
    ├── FinalBurn Neo.dat    ← DAT Mestre (ClrMame Pro XML)
    └── catver.ini           ← Gêneros (opcional)

        ↓ Step 1: Split DAT

output/dats_generated/
├── cps1.dat
└── neogeo.dat

        ↓ Step 2: IGIR

output/roms/
├── cps1/
│   └── sf2.zip              ← renomeado, CRC verificado, organizado
└── neogeo/
    └── kof97.zip

        ↓ Step 5: Organizar Imagens

output/images/
├── cps1/
│   └── sf2.png              ← symlink → source/images/Street Fighter II (USA).png
└── neogeo/
    └── kof97.jpg

        ↓ Step 6: Converter WebP

output/images/
├── cps1/
│   └── sf2.webp             ← convertido (original preservado até Step 12)
└── neogeo/
    └── kof97.webp

        ↓ Step 8: Otimizar Vídeos

videos_dir/
└── sf2.mp4                  ← H.265, atomic write (original .avi apagado após commit)

        ↓ Step 9: gamelist.xml

output/
└── gamelist.xml

SAÍDA FINAL
───────────
output/
├── roms/              → ROMs organizados para o emulador
├── images/            → Imagens padronizadas (WebP)
├── gamelist.xml       → Metadados para EmulationStation
├── dats_generated/    → DATs por driver
├── logs/
│   └── pipeline.log   → Log completo com rotação automática
└── reports/
    ├── validation_report.txt
    ├── unmatched_images.txt
    └── kpi.csv
```

---

## 9. Referência Completa de config.yaml

```yaml
# ===========================================================================
# EmuPipeline v5.0 — Referência Completa de Configuração
# Copie config.yaml.example → config.yaml e ajuste.
# ===========================================================================

global:
  base_dir: "~/Documents/emupipeline"
  logging_level: "INFO"   # DEBUG | INFO | WARNING | ERROR
  threads: 8              # workers paralelos (recomendado: nº de núcleos lógicos)
  structured_logging: false  # true = JSON para ELK/Grafana

paths:
  dat_file:       "dats/FinalBurn Neo (ClrMame Pro XML, Arcade only).dat"
  catver_ini:     "dats/catver.ini"       # opcional
  input_roms:     "source/roms"
  input_imgs:     "source/images"
  output_roms:    "output/roms"
  output_imgs:    "output/images"
  output_xml:     "output/gamelist.xml"
  output_dats:    "output/dats_generated"
  output_reports: "output/reports"
  output_logs:    "output/logs"
  videos_dir:     "~/Emulation/tools/downloaded_media/ports/videos"
  upscale_input:  "source/images"
  upscale_output: "output/images_upscaled"
  bin_waifu2x:    "~/Applications/waifu2x-ncnn-vulkan/waifu2x-ncnn-vulkan"
  bin_realesrgan: "~/Applications/realesrgan-ncnn-vulkan/realesrgan-ncnn-vulkan"

roms:
  enable_igir: true
  split_by_driver: true          # false → único DAT filtrado
  combined_filename: "FBNeo_Optimized.dat"
  organize_subfolders: true      # output/roms/cps1/sf2.zip
  merge_mode: "nonmerged"        # nonmerged | split | merged
  filter_regions: "WORLD,BRA,USA,EUR,JPN"
  threads_io: 4                  # 2–4 para HDD, até 8 para SSD NVMe
  generate_bios_file: false
  bios_filename: "00_BIOS_Global.dat"
  exclude_clones: true
  blacklist:
    - "mahjong"
    - "poker"
    - "adult"
    - "bootleg"
    - "hack"
    # Palavras-chave na <description> do jogo

images:
  organization_mode: "subfolders"  # subfolders | flat
  mode: "symlink"                  # symlink | copy
  overwrite: false
  fuzzy_threshold: 0.80            # 0.0–1.0 (0.80 recomendado)
  valid_extensions:
    - ".png"
    - ".jpg"
    - ".jpeg"
    - ".gif"
    - ".webp"

webp:
  quality: 85                      # 1–100 (85 = visualmente idêntico ao PNG)
  source_extensions:               # deleção gerenciada pelo step_clean (opção 12)
    - ".png"
    - ".jpg"
    - ".jpeg"
    - ".bmp"

videos:
  codec: "libx265"     # libx265 (H.265/HEVC) | libx264 (H.264/AVC)
  crf: 28              # 0–51 (28 = bom para retro gaming)
  preset: "fast"       # ultrafast | veryfast | fast | medium | slow
  delete_original: true   # apaga .avi após commit atômico bem-sucedido
  smart_skip: true        # pula vídeos já no codec correto (RECOMENDADO: true)
  extensions:
    - ".mp4"
    - ".avi"
    - ".mkv"
    - ".mov"
    - ".webm"

upscale:
  engine: null          # null (interativo) | "waifu2x" | "realesrgan"
  scale: 2              # 2 ou 4 (4 requer mais VRAM)
  output_format: "webp" # png | jpg | webp
  workers: 2            # limitado pela GPU, não pela CPU
  recursive: false
  post_process: true    # unsharp mask + ruído via ImageMagick
  unsharp: "0x1.0+1.0+0.02"
  noise: "0.5"

compare:
  output_dir: "output/common_files"  # APAGADO a cada execução
  copy_common: true

ports:
  source_dir: "~/Emulation/ports"
  output_dir: "~/Emulation/tools/ports_launchers"
  rename_plus_folders: false
  windows_runner: "wine"
  enable_gamemode: false
  enable_mangohud: false
  windows_extensions:
    - ".exe"
  windows_environment:
    ESYNC: "1"
    FSYNC: "1"
```

---

## 10. Testes

```bash
# Testes unitários (sem ferramentas externas)
pytest tests/unit/ -v

# Com cobertura HTML
pytest tests/unit/ --cov=src/emupipeline --cov-report=html
open htmlcov/index.html

# Testes de integração (requer ffmpeg e igir instalados)
pytest tests/integration/ -v

# Step específico
pytest tests/unit/test_steps/test_optimize.py -v

# Pular testes lentos
pytest tests/ -m "not slow"
```

### Cobertura mínima configurada

| Módulo | Meta |
|---|---|
| `core/dat_manager.py` | 90% |
| `core/execution_mode.py` | 90% |
| `core/transaction.py` | 85% |
| `core/config.py` | 85% |
| `core/processor.py` | 80% |
| `steps/step_optimize.py` | 80% |
| **Média geral** | **≥ 75%** |

### O que está coberto pelos testes

**Unitários (`tests/unit/`):** normalização de strings, busca em 3 camadas no DatMaster, invalidação de cache, thread-safety de stats e AuditReport, commit/rollback de StagingTransaction, atomic_write com erro, detecção de versão no EnvironmentChecker, smart-skip via ffprobe mockado, atomic write em VideoOptimizer, dry-run e audit-mode em todos os steps destrutivos.

**Integração (`tests/integration/`):** DatSplitter com blacklist real, ImageOrganizer end-to-end, separação `WebPConverter`/`OriginalCleaner`, pipeline completo com subprocess mockado, pipeline em modo AUDIT com verificação de zero-write em disco de entrada.

---

## 11. Troubleshooting

### `config.yaml não encontrado`
```bash
cd ~/Documents/emupipeline && emupipeline
# ou defina a variável de ambiente
export EMUPIPELINE_CONFIG=~/Documents/emupipeline/config.yaml
```

### `igir: command not found`
```bash
npm install -g igir
echo 'export PATH="$HOME/.npm-global/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Cache desatualizado — DAT modificado não refletido
```bash
rm dats/*.pickle    # força reconstrução do cache na próxima execução
```

### Fuzzy match casando imagens erradas
```yaml
images:
  fuzzy_threshold: 0.90   # mais restritivo (padrão: 0.80)
```
Verifique o arquivo `output/reports/unmatched_images.txt` para calibrar.

### WebP gerado com tamanho suspeito
```
WARNING | WebPConverter | WebP suspeito (< 100 bytes). Original preservado.
```
Verifique integridade da imagem original:
```bash
file imagem.png           # deve retornar "PNG image data…"
identify imagem.png       # ImageMagick verifica integridade
```

### FFmpeg falha silenciosamente
```yaml
global:
  logging_level: "DEBUG"    # stderr completo do ffmpeg em output/logs/pipeline.log
```

### Todos os vídeos marcados como `skipped_codec`
Os vídeos já estão no codec alvo (`hevc`). Para forçar reprocessamento:
```yaml
videos:
  smart_skip: false         # use com cautela — reprocessa todos
```

### Symlinks quebrados após mover `source/images/`
```bash
find output/images -type l -delete
emupipeline --step 5       # recria os symlinks relativos
```

### Upscaling trava ou crasha (VRAM insuficiente)
```yaml
upscale:
  workers: 1    # processamento sequencial
  scale: 2      # evite scale: 4 em GPUs com menos de 4GB VRAM
```

Verifique Vulkan:
```bash
vulkaninfo | head -20
vkcube                     # renderização Vulkan básica
```

---

## 12. Glossário

| Termo | Descrição |
|---|---|
| **DAT** | Arquivo XML no formato ClrMame Pro com metadados (nome, CRC, SHA1) de cada ROM de um sistema. |
| **Driver** | No FBNeo/MAME, o arquivo C++ responsável por emular um hardware específico. Ex: `cps1.cpp` emula o CPS-1 da Capcom. O pipeline usa o driver para organizar jogos em subpastas. |
| **Parent / Clone** | O "parent" é a versão principal de um jogo. "Clones" são variações regionais ou revisões. Ex: `sf2` (parent) → `sf2ce`, `sf2hf` (clones). |
| **Romset** | Coleção completa de ROMs para um sistema. Um romset "full" contém todos os jogos do DAT correspondente. |
| **IGIR** | Ferramenta Node.js para gerenciamento de ROMs. Verifica integridade (CRC/SHA), renomeia e organiza baseando-se em arquivos DAT. |
| **catver.ini** | Arquivo mantido pela comunidade MAME com a categoria/gênero de cada jogo arcade. |
| **gamelist.xml** | Arquivo de metadados lido pelo EmulationStation/ES-DE com nome, descrição, gênero e imagem para cada jogo. |
| **CRF** | Constant Rate Factor — parâmetro de qualidade do FFmpeg. Menor = maior qualidade e arquivo maior (0–51). |
| **HEVC / H.265** | Codec de vídeo moderno com ~50% melhor compressão que H.264 na mesma qualidade visual. |
| **Fuzzy Match** | Comparação aproximada de strings para casar nomes de imagens com nomes de ROMs mesmo com diferenças de formatação. |
| **Bi-gramas** | Pares de caracteres consecutivos usados como índice invertido para acelerar o fuzzy search de O(n·m) para O(k). |
| **WebP** | Formato de imagem do Google com compressão ~70% melhor que PNG mantendo qualidade visual. Suportado pelo EmulationStation. |
| **waifu2x** | Rede neural para upscaling de imagens 2D/anime via Vulkan. Especializada em pixel art e screenshots retro. |
| **Real-ESRGAN** | Rede neural para upscaling de imagens realistas via Vulkan. Preserva detalhes finos em texturas e fotografias. |
| **Symlink** | Atalho simbólico do filesystem. Aparece como arquivo normal mas aponta para outro. Economiza espaço ao evitar duplicação. |
| **atomic_write** | Escrita em arquivo temporário + rename atômico. Garante que o destino nunca fica em estado corrompido. |
| **StagingTransaction** | Padrão de escrita em diretório temporário com commit ou rollback explícito. |
| **EmuDeck** | Script de instalação automatizada de emuladores para Steam Deck e Linux. O EmuPipeline é complementar ao EmuDeck. |
| **Bazzite** | Distribuição Linux imutável baseada em Fedora Atomic, otimizada para gaming. Principal plataforma alvo do EmuPipeline. |
| **src-layout** | Convenção Python que coloca o código em `src/nome_pacote/`, separando-o do código de testes e evitando importações acidentais. |
| **entry_point** | Mecanismo do setuptools para registrar comandos CLI ou plugins descobertos por outros pacotes. |
| **GIL** | Global Interpreter Lock — mecanismo do CPython que impede múltiplas threads de executar bytecode Python simultaneamente. Operações I/O e extensões C (como PIL) liberam o GIL. |
| **ProcessPoolExecutor** | Executa tarefas em processos separados, contornando o GIL. Usado pelo `WebPConverter` para paralelismo real de CPU. |
| **WINEPREFIX** | Diretório com uma instalação isolada do Wine. Cada prefix é completamente independente. |
| **oversubscription** | Condição em que o número de processos/threads disputando CPU supera os núcleos disponíveis, degradando performance. O `VideoOptimizer` evita isso limitando seus workers Python a `threads // 2`. |

---

## 13. Contribuindo e Roadmap

Leia [CONTRIBUTING.md](CONTRIBUTING.md) para o guia completo de desenvolvimento, padrões de código, como adicionar steps/plugins e o processo de Pull Request.

### Roadmap

| Versão | Status | Features |
|---|---|---|
| v4.0 | ✅ Released | Consolidação dos dois projetos, BaseProcessor thread-safe, índice de bi-gramas |
| v5.0 | ✅ Current | Pydantic v2, EnvironmentChecker, StagingTransaction, StepRegistry, AuditReport, CI/CD, src-layout |
| v5.1 | 🔜 Planned | MkDocs + documentação auto-gerada do schema Pydantic; testes de regressão adicionais |
| v5.2 | 🔜 Planned | Suporte a múltiplos DATs simultâneos; suporte a No-Intro/Redump |
| v6.0 | 💡 Future | Interface web opcional via FastAPI; monitoramento em tempo real |

---

*EmuPipeline v5.0 — MIT License*
