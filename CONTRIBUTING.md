# Contribuindo com o EmuPipeline

Obrigado pelo interesse em contribuir! Este guia cobre o processo de desenvolvimento do projeto.

## Índice

1. [Configurando o ambiente](#1-configurando-o-ambiente)
2. [Estrutura do projeto](#2-estrutura-do-projeto)
3. [Fluxo de trabalho](#3-fluxo-de-trabalho)
4. [Padrões de código](#4-padrões-de-código)
5. [Escrevendo testes](#5-escrevendo-testes)
6. [Adicionando um novo step](#6-adicionando-um-novo-step)
7. [Adicionando um plugin externo](#7-adicionando-um-plugin-externo)
8. [Commit e Pull Request](#8-commit-e-pull-request)
9. [Versionamento](#9-versionamento)

---

## 1. Configurando o ambiente

```bash
# Clone o repositório
git clone https://github.com/seu-usuario/emupipeline.git
cd emupipeline

# Crie um virtualenv (Python 3.10+)
python3 -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# Instale o pacote em modo editável com todas as dependências de dev
pip install -e ".[dev]"

# Instale os pre-commit hooks
pre-commit install
pre-commit install --hook-type commit-msg

# Verifique que tudo funciona
pytest tests/unit/ -v
emupipeline --help
```

---

## 2. Estrutura do projeto

```
src/emupipeline/
├── core/                  ← biblioteca interna; não edite sem testes
│   ├── config.py          ConfigLoader (singleton)
│   ├── config_schema.py   Schema Pydantic de validação
│   ├── dat_manager.py     Parser DAT + fuzzy search
│   ├── env_checker.py     Verificação de dependências externas
│   ├── execution_mode.py  ExecutionMode enum + AuditReport
│   ├── logger.py          Fábrica de loggers
│   ├── metrics.py         Coleta de métricas por step
│   ├── processor.py       BaseProcessor (herdar para novos steps)
│   ├── registry.py        Registry de steps com autodiscover
│   ├── step_interface.py  StepMeta + StepProtocol
│   └── transaction.py     StagingTransaction + atomic_write
└── steps/                 ← módulos de steps (um por arquivo)
    └── step_*.py          Cada step herda BaseProcessor + usa @register
```

### Convenções de nomenclatura

| Elemento | Convenção | Exemplo |
|---|---|---|
| Arquivo de step | `step_{nome}.py` | `step_convert.py` |
| Classe do step | PascalCase + sufixo funcional | `WebPConverter` |
| ID no registry | snake_case | `"webp_convert"` |
| Teste unitário | `test_{módulo}.py` | `test_convert.py` |

---

## 3. Fluxo de trabalho

```
main (protegido) ← PR ← feature/meu-step ← desenvolvimento local
```

1. Crie uma branch a partir de `develop` (não de `main`):

```bash
git checkout develop
git checkout -b feature/meu-step
```

2. Desenvolva com TDD (escreva o teste antes da implementação).

3. Garanta que os hooks passam antes do commit:

```bash
pre-commit run --all-files
pytest tests/unit/ --cov=src/emupipeline
```

4. Abra um PR para `develop`. Um revisor irá aprová-lo antes do merge para `main`.

---

## 4. Padrões de código

### Type hints obrigatórios

Todos os métodos públicos e privados devem ter type hints completos:

```python
# ✅ Correto
def process_file(self, file_path: Path) -> str:
    ...

# ❌ Incorreto
def process_file(self, file_path):
    ...
```

### Docstrings

Módulos, classes públicas e métodos públicos devem ter docstrings:

```python
def search(self, filename: str, fuzzy_threshold: float = 0.80) -> tuple[GameInfo | None, str | None]:
    """
    Busca em 3 camadas: exact_rom → exact_title → fuzzy.

    Args:
        filename: Nome do arquivo (com ou sem extensão).
        fuzzy_threshold: Threshold de similaridade (0.0–1.0).

    Returns:
        Tupla (GameInfo, match_type) ou (None, None) se não encontrado.
    """
```

### Sem prints diretos

Use `self.logger` em vez de `print()` em steps e core:

```python
# ✅
self.logger.info(f"Processando {file_path.name}")

# ❌
print(f"Processando {file_path.name}")
```

Exceção: `cli.py` pode usar `print()` para output ao usuário.

### Operações destrutivas

Todo método que deleta ou sobrescreve arquivos deve:

1. Usar `atomic_write` ou `StagingTransaction`
2. Validar o output antes de deletar o original
3. Respeitar o `ExecutionMode`

```python
from emupipeline.core.transaction import atomic_write

def process_file(self, path: Path) -> str:
    if self._mode == ExecutionMode.DRY_RUN:
        self.logger.info(f"[DRY] Converteria: {path.name}")
        return "dry_run"

    dest = path.with_suffix(".webp")
    with atomic_write(dest) as tmp:
        # ... escreve em tmp ...
    return "converted"
```

---

## 5. Escrevendo testes

### Regras básicas

- **Um arquivo de teste por módulo**: `test_convert.py` → `step_convert.py`
- **Classes de teste por comportamento**: `TestSmartSkip`, `TestAtomicWrite`, `TestDryRun`
- **Use fixtures do `conftest.py`**: `tmp_project`, `sample_dat`, `config_factory`
- **Mocke subprocess sempre**: nunca chame ffmpeg/igir em testes unitários
- **Teste os três modos** (NORMAL, DRY_RUN, AUDIT) em todo step destrutivo

### Fixtures disponíveis

```python
def test_exemplo(tmp_project, sample_dat, config_factory):
    # tmp_project: Path com estrutura de diretórios mínima em /tmp
    # sample_dat: Path para DAT XML com 10 jogos de teste
    # config_factory(): cria config.yaml apontando para tmp_project

    config_factory()   # usa defaults
    config_factory({"videos": {"crf": 23}})  # com overrides
```

### Nomenclatura de testes

```python
# Formato: test_{o_que_faz}_{dado_estado}
def test_smart_skip_returns_skipped_when_codec_matches(): ...
def test_atomic_write_preserves_original_on_error(): ...
def test_audit_report_records_all_operations(): ...
```

### Cobertura mínima

| Módulo | Meta |
|---|---|
| `core/dat_manager.py` | 90% |
| `core/config.py` | 85% |
| `core/processor.py` | 80% |
| `core/execution_mode.py` | 90% |
| `core/transaction.py` | 85% |
| `steps/step_convert.py` | 80% |
| `steps/step_optimize.py` | 80% |
| Média geral | **75%** |

---

## 6. Adicionando um novo step

1. **Crie o arquivo** `src/emupipeline/steps/step_meu_step.py`:

```python
from __future__ import annotations

from pathlib import Path

from emupipeline.core.execution_mode import AuditReport, ExecutionMode
from emupipeline.core.processor import BaseProcessor
from emupipeline.core.registry import register
from emupipeline.core.step_interface import StepMeta


@register
class MeuStep(BaseProcessor):
    meta = StepMeta(
        id="meu_step",
        menu_number=12,           # próximo número disponível no menu
        label="Descrição no menu",
        group="Grupo no Menu",    # "ROMs & DATs" | "Imagens" | "Vídeo & Metadados" | "Extras"
        description="Descrição longa para --help",
        requires_dat=False,        # True se precisar de DatMaster
        pipeline_order=999,        # 999 = não incluso no pipeline automático
    )

    def __init__(
        self,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        audit: AuditReport | None = None,
    ) -> None:
        super().__init__("MeuStep")
        self._mode = mode
        self._audit = audit
        # leia configurações do cfg aqui

    def process_file(self, file_path: Path) -> str:
        if self._mode == ExecutionMode.DRY_RUN:
            self.logger.info(f"[DRY] Processaria: {file_path.name}")
            return "dry_run"

        if self._mode == ExecutionMode.AUDIT:
            self._audit.record(  # type: ignore[union-attr]
                step=self.name,
                action="minha_acao",
                source=str(file_path),
            )
            return "audit_recorded"

        # Implementação real aqui
        return "processed"

    def run(self, **kwargs) -> None:
        files = self.scan(self._source_dir)
        self.run_parallel(files)
```

2. **Crie os testes** `tests/unit/test_steps/test_meu_step.py` (ver seção 5).

3. **Verifique o registro**:

```bash
python -c "
from emupipeline.core.registry import autodiscover, get_all_steps
autodiscover()
steps = get_all_steps()
print('meu_step' in steps)  # deve imprimir True
"
```

4. O step aparecerá **automaticamente** no menu na posição `menu_number`.

---

## 7. Adicionando um plugin externo

Plugins externos permitem adicionar steps sem modificar o repositório principal.

1. Crie um pacote Python separado (`pip install -e meu-plugin`)

2. Declare o entry point no `pyproject.toml` do plugin:

```toml
[project.entry-points."emupipeline.steps"]
meu_step = "meu_pacote.meu_step:MeuStep"
```

3. O `autodiscover()` carregará o plugin automaticamente.

---

## 8. Commit e Pull Request

### Formato de commits (Conventional Commits)

```
<tipo>(<escopo>): <descrição curta>

[corpo opcional — explica O QUÊ e POR QUÊ, não o como]

[rodapé opcional — BREAKING CHANGE, closes #N]
```

| Tipo | Uso |
|---|---|
| `feat` | Nova feature |
| `fix` | Correção de bug |
| `refactor` | Refatoração sem mudança de comportamento |
| `test` | Adição ou correção de testes |
| `docs` | Documentação |
| `chore` | Manutenção (deps, CI, config) |
| `perf` | Melhoria de performance |

Exemplos:

```
feat(step_optimize): adiciona controle de oversubscription de CPU

O VideoOptimizer agora usa threads // 2 como limite de workers Python
para evitar competição com os processos ffmpeg filhos.

fix(dat_manager): substitui MD5 de 64KB por SHA-256 híbrido

MD5 de 64KB não detectava mudanças no meio/fim de DATs grandes.
O SHA-256 híbrido cobre primeiros 512KB + últimos 64KB + metadados.

Closes #42
```

### Checklist do PR

- [ ] Testes escritos e passando (`pytest tests/unit/`)
- [ ] Cobertura não regrediu (`--cov-fail-under=75`)
- [ ] Mypy sem erros (`mypy src/emupipeline/`)
- [ ] Ruff sem erros (`ruff check src/ tests/`)
- [ ] CHANGELOG.md atualizado
- [ ] Docstrings em métodos públicos novos

---

## 9. Versionamento

Seguimos [Semantic Versioning](https://semver.org/):

```
MAJOR.MINOR.PATCH

5.0.0  → versão estável atual
5.1.0  → nova feature (compatível com 5.0)
5.1.1  → bugfix
6.0.0  → breaking change (ex: mudança na API do StepProtocol)
```

Para fazer um release:

```bash
# Bump de versão (edita src/emupipeline/__init__.py e pyproject.toml)
# Depois crie uma tag:
git tag -a v5.1.0 -m "Release v5.1.0"
git push origin v5.1.0
# O CI fará o build e publicação no PyPI automaticamente
```
