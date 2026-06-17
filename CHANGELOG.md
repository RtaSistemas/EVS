# Changelog

Todas as mudanças notáveis deste projeto são documentadas aqui.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).
Versionamento segue [Semantic Versioning](https://semver.org/lang/pt-BR/).

---

## [5.0.0] — 2026-02

### ✨ Adicionado

- **Empacotamento formal** (`pyproject.toml`) com entry point `emupipeline` instalável via pip
- **Validação de config com Pydantic v2** — erros de tipo/range reportados na inicialização com mensagens amigáveis ao usuário; fallback para validação manual quando Pydantic não está instalado
- **EnvironmentChecker** — verificação de dependências externas com fail-fast antes do pipeline iniciar (ffmpeg, ffprobe, igir, magick, waifu2x, realesrgan)
- **ExecutionMode enum** — três modos distintos: `NORMAL`, `DRY_RUN`, `AUDIT`
- **AuditReport** — coleta thread-safe de todas as operações planejadas em modo AUDIT; exporta JSON e HTML
- **StagingTransaction e `atomic_write`** — toda escrita vai para diretório staging; commit atômico via `rename()` no mesmo filesystem; rollback automático em exceção
- **StepRegistry com autodiscover** — steps registrados via decorator `@register`; plugins externos via `entry_points`
- **StepMeta / StepProtocol** — interface formal com `id`, `menu_number`, `group`, `pipeline_order`
- **MetricsCollector** — métricas por step: duração, throughput (arq/s), taxa de compressão (bytes_in/bytes_out)
- **JsonFormatter** — logging estruturado JSON opcional (`global.structured_logging: true`)
- **ProcessPoolExecutor para WebPConverter** — paralelismo real de CPU contornando o GIL
- **step_clean.py** — `OriginalCleaner` separado de `WebPConverter` (responsabilidade única; sempre pede confirmação explícita)
- **Modo dry-run via injeção** de `ExecutionMode` no construtor (substitui monkey-patch de variável de classe)
- **Controle de oversubscription** — `VideoOptimizer` usa `threads // 2` para não competir com processos ffmpeg
- **Cache com SHA-256 híbrido** — primeiros 512KB + últimos 64KB + mtime + tamanho; inclui `CACHE_VERSION` para invalidação por schema
- **Suite de testes** — 300+ assertivas em testes unitários e de integração; cobertura mínima configurada em 75%
- **CI/CD GitHub Actions** — lint (ruff), type check (mypy), testes Python 3.10/3.11/3.12, build e publicação automática no PyPI
- **pre-commit hooks** — ruff, mypy, bandit, verificações de segurança
- **Menu dinâmico** gerado automaticamente a partir do registry de steps
- `src-layout` — separação clara entre código de distribuição e de desenvolvimento

### 🔧 Alterado

- `main.py` substituído por `cli.py` com entry point formal
- `BaseProcessor.dry_run` removido como variável de classe; substituído por `mode: ExecutionMode` injetado via construtor
- `ConfigLoader` agora usa `ConfigSchema` (Pydantic) internamente; a interface pública `.get()` permanece compatível
- `DatMaster._dat_hash()` → `_dat_fingerprint()` com SHA-256 híbrido (era MD5 de 64KB)
- `step_convert.py` — `delete_original` removido; deleção movida para `step_clean.py`
- `VideoOptimizer` usa `atomic_write` em vez de rename direto
- Estrutura de pastas migrada para `src/emupipeline/` (src-layout)
- Symlinks criados por `ImageOrganizer` são sempre relativos

### 🐛 Corrigido

- **Race condition** em dry-run: monkey-patch de variável de classe afetava todas as instâncias em ambiente multi-thread
- **Zombies de ffmpeg**: processos orphaned em timeout agora recebem SIGKILL via `os.killpg`
- **Corrupção parcial**: falha no meio de `step_optimize` agora nunca deixa arquivo corrompido no destino
- **Cache stale**: MD5 de 64KB não detectava mudanças no meio/fim do DAT; SHA-256 híbrido resolve
- **Pickle com schema desatualizado**: `CACHE_VERSION` invalida cache quando `GameInfo` muda
- **Oversubscription de CPU**: VideoOptimizer limitava workers Python sem considerar os processos ffmpeg filhos

### ❌ Removido

- `main.py` (substituído por `cli.py`)
- `lib_emudeck/` e `lib_core/` (foram removidos na v4; confirmado ausente na v5)
- `delete_original` de `WebPConverter` (movido para `OriginalCleaner`)

---

## [4.0.0] — 2026-01

### ✨ Adicionado

- Consolidação dos dois projetos paralelos (`lib_emudeck/` + `EmuPipeline/`) em estrutura única
- `BaseProcessor` com lock em stats (`threading.Lock`) — eliminadas race conditions
- Índice de bi-gramas no `DatMaster` para fuzzy search O(k) (era O(n·m))
- `GameInfo` com `__slots__` — eficiência de memória para 50k+ objetos
- Lazy loading de steps em `main.py` — falha de dependência isolada por step
- Symlinks relativos em `step_organize` — sobrevivem a movimentação de pastas
- Cache Pickle com validação por MD5 de 64KB
- Dry-run global via flag `--dry-run`
- `step_ports.py` — launchers `.desktop` para Linux e Windows (Wine)
- `step_clean.py` — separação de deleção de originais

### 🔧 Alterado

- `normalize_string()` consolidada em `dat_manager.py` (era duplicada em 3 lugares)
- `ConfigLoader` unificado (era dois com lógicas incompatíveis)
- `resolve_driver()` e `sanitize_driver_name()` mescladas

### 🐛 Corrigido

- Zombie processes de ffmpeg em timeout
- File handle leak em `Image.open()` sem context manager
- Temp files `.mp4` persistindo após falha (atomic rename)
- WebP gerado com tamanho suspeito não apagava o original
- Symlinks absolutos quebravam com movimentação de projeto

---

## [3.x] — Histórico anterior

Versões 3.x e anteriores não foram formalmente documentadas.
O histórico de commits do repositório git é a referência primária.
