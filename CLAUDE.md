# CLAUDE.md — EmuPipeline v5

Guia rápido para sessões do Claude Code neste repositório.

## Comandos essenciais

```bash
# Roda todos os testes (unit + integration + e2e)
pytest

# Só unit tests (rápido)
pytest tests/unit/ -v

# Um arquivo específico
pytest tests/unit/test_processor.py -v

# Com cobertura mínima (75% — falha o build se abaixo)
pytest --cov-fail-under=75

# Linter
ruff check src/ tests/

# Type checker (só src/, não tests/)
mypy src/emupipeline/
```

## Arquitetura

```
src/emupipeline/
├── core/           biblioteca interna — não editar sem testes
│   ├── config.py           ConfigLoader singleton (lê config.yaml)
│   ├── dat_manager.py      Parser DAT + fuzzy search + cache pickle
│   ├── execution_mode.py   ExecutionMode enum + AuditReport thread-safe
│   ├── processor.py        BaseProcessor — herdar para novos steps
│   ├── registry.py         @register + autodiscover() via entry-points
│   ├── transaction.py      StagingTransaction + atomic_write
│   └── env_checker.py      Verificação de dependências externas
└── steps/
    └── step_*.py           Cada step herda BaseProcessor + usa @register
tests/
├── unit/           isolados, sem I/O real de subprocess
├── integration/    steps reais se comunicando (DAT + imagens + filesystem)
└── e2e/            filesystem real, sem ferramentas externas (ffmpeg/igir mockados)
```

## Regras de código

- **Type hints obrigatórios** em todos os métodos públicos e privados
- **Docstrings** em módulos, classes públicas e métodos públicos
- **Sem `print()`** em steps/core — usar `self.logger`; exceção: `cli.py`
- **Operações destrutivas** (delete, overwrite) devem usar `atomic_write` ou
  `StagingTransaction`, e respeitar `ExecutionMode` antes de qualquer I/O
- **Linha máxima**: 100 caracteres (ruff)
- **Aspas**: duplas (ruff format)

## Regras de testes

- Um arquivo de teste por módulo: `step_convert.py` → `test_convert.py`
- Classes agrupadas por comportamento: `TestSmartSkip`, `TestDryRun`, `TestAuditMode`
- Usar fixtures do `conftest.py`: `tmp_project`, `sample_dat`, `config_factory`
- **Sempre mockar subprocess** — nunca chamar ffmpeg/igir/waifu2x em testes unitários
- Todo step destrutivo deve ter testes para os 3 modos: NORMAL, DRY_RUN, AUDIT
- Cobertura mínima: 75% geral; módulos core têm metas entre 80–90%

### Fixtures disponíveis (`conftest.py`)

```python
def test_exemplo(config_factory, tmp_project, sample_dat):
    cfg = config_factory()                        # config padrão
    cfg = config_factory({"videos": {"crf": 23}}) # com override de seção

    # tmp_project: Path com estrutura source/roms, output/images, etc.
    # sample_dat:  DAT XML com 4 jogos: sf2 (parent), sf2ce (clone),
    #              kof97, mahjong_game (blacklistado)
```

## Padrões obrigatórios por step

### Herdar BaseProcessor — todos os steps devem seguir este padrão

```python
from emupipeline.core.processor import BaseProcessor
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta

@register
class MeuStep(BaseProcessor):
    meta = StepMeta(
        id="meu_step",
        menu_number=12,
        label="Meu Step",
        group="Grupo",
        pipeline_order=120,
    )

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        audit: Optional[AuditReport] = None,
    ) -> None:
        super().__init__("MeuStep", mode=mode, audit=audit)
        # self.config, self.logger, self._mode, self._audit, self.name disponíveis

    def process_file(self, file_path: Path) -> str:
        # Stub obrigatório quando o step não usa scan()+run_parallel()
        return "not_applicable"
```

### ExecutionMode — verificar ANTES de qualquer I/O

```python
def process_file(self, file_path: Path) -> str:
    if self._mode == ExecutionMode.AUDIT:
        if self._audit is None:
            self.logger.error("AUDIT mode requer AuditReport injetado no construtor.")
            return "error"
        self._audit.record(step=self.name, action="minha_acao", source=str(file_path))
        return "audit_recorded"
    if self._mode == ExecutionMode.DRY_RUN:
        self.logger.info(f"[DRY] Processaria: {file_path.name}")
        return "dry_run"
    # NORMAL: I/O acontece aqui
    dest_dir.mkdir(parents=True, exist_ok=True)  # mkdir DEPOIS dos guards de modo
    ...
```

### Contagem de estatísticas — usar update_stat(), não _stats diretamente

```python
# ✅ Correto: thread-safe via update_stat()
self.update_stat("processed")        # incrementa em 1
self.update_stat("processed", 10)    # incrementa em 10
stats = self.get_stats()             # retorna cópia do dict

# ❌ Nunca: acesso direto não é thread-safe em run_parallel()
self._stats["processed"] = 1        # pode causar race condition
```

### MetricsCollector — integração no cli.py

```python
from emupipeline.core.metrics import MetricsCollector

collector = MetricsCollector()
# após cada step.run():
if hasattr(step, "last_metrics") and step.last_metrics is not None:
    collector.register(step.last_metrics)
# ao final do pipeline:
collector.export_json(Path(reports_dir) / "metrics.json")
```

### Escrita atômica

```python
from emupipeline.core.transaction import atomic_write, StagingTransaction

# Um arquivo:
with atomic_write(dest_path) as tmp:
    tmp.write_bytes(data)

# Múltiplos arquivos (ou substituição de diretório inteiro):
with StagingTransaction(dest_dir) as txn:
    txn.stage_path("output.dat").write_text(content)
    txn.commit()
```

## Armadilhas conhecidas

### ConfigLoader é singleton — não importar no nível de módulo em código de produção

```python
# ❌ NUNCA no topo de processor.py ou de qualquer módulo importado cedo
from emupipeline.core.config import cfg

# ✅ Importar dentro de __init__ ou de métodos
class MeuStep(BaseProcessor):
    def __init__(self, ...):
        super().__init__("MeuStep")  # BaseProcessor já faz self.config = cfg
        self._quality = self.config.get("webp", "quality", 85)
```

Se um módulo importar `cfg` no nível de módulo, qualquer `import` dele durante a
coleta do pytest levanta `FileNotFoundError` (config.yaml não existe fora do fixture).

### PIL/Pillow é importado lazily dentro de `process_file`

```python
# Em step_convert.py, Image é importado dentro do método — não é atributo do módulo.
# Por isso patch("emupipeline.steps.step_convert.Image") falha com AttributeError.

# ✅ Para testar sem Pillow: suprimir via sys.modules DEPOIS de instanciar o objeto
converter = WebPConverter(mode=ExecutionMode.NORMAL)  # instancia antes
with patch.dict("sys.modules", {"PIL": None, "PIL.Image": None}):
    result = converter.process_file(img)

# ✅ Para testar COM Pillow: usar pytest.importorskip
pytest.importorskip("PIL", reason="Pillow não instalado")
from PIL import Image
Image.new("RGB", (10, 10)).save(img_path, "PNG")
```

### ExecutorType.PROCESS não consegue serializar o ConfigLoader

O `ConfigLoader` mantém um `threading.Lock` internamente. `ProcessPoolExecutor`
usa pickle para enviar objetos entre processos e **não consegue serializar Lock**.

```python
# ✅ Em testes E2E que instanciam WebPConverter, forçar THREAD:
from emupipeline.core.processor import ExecutorType
with patch.object(WebPConverter, "_executor_type", ExecutorType.THREAD):
    WebPConverter().run()
```

### OriginalCleaner lê `paths.output_imgs`, não um atributo `_source_dir`

```python
# ✅ Colocar arquivos em output/images para testes do OriginalCleaner
out_imgs = tmp_project / "output" / "images"
out_imgs.mkdir(parents=True, exist_ok=True)
(out_imgs / "sf2.png").write_bytes(b"PNG" * 30)
(out_imgs / "sf2.webp").write_bytes(b"WEBP" * 30)  # > 50 bytes (threshold de validade)
```

### mkdir deve vir DEPOIS dos guards de ExecutionMode

Se `mkdir` for chamado antes do bloco `if AUDIT / DRY_RUN`, ele criará diretórios
vazios no disco mesmo em modos não-destrutivos — violando o contrato do AUDIT mode.

## Adicionando um novo step

1. Crie `src/emupipeline/steps/step_meu_step.py` herdando `BaseProcessor` com `@register`
2. Declare `meta = StepMeta(id=..., menu_number=..., pipeline_order=...)` na classe
3. Implemente `process_file(path) -> str` com guards de ExecutionMode
4. Implemente `run(**kwargs)` chamando `self.scan()` + `self.run_parallel()`
5. Crie `tests/unit/test_steps/test_meu_step.py` com classes por comportamento
6. Verifique o registro: `python -c "from emupipeline.core.registry import autodiscover, get_all_steps; autodiscover(); print(get_all_steps())"`

## Commits (Conventional Commits)

```
feat(step_optimize): adiciona controle de oversubscription de CPU
fix(dat_manager): exclui BIOS de driver DATs quando generate_bios_file=false
test(step_organize): cobre AUDIT mode no _match_and_place
refactor(processor): remove import de cfg no nível de módulo
```

Tipos válidos: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`

## Checklist antes de fazer push

- [ ] `pytest tests/unit/` — zero falhas
- [ ] `pytest --cov-fail-under=75` — cobertura ≥ 75%
- [ ] `ruff check src/ tests/` — sem erros
- [ ] `mypy src/emupipeline/` — sem erros de tipo
