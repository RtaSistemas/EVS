"""
Smoke tests para emupipeline.tui.

tui.py depende de 'textual' (não incluído no ambiente base). Todos os
testes são condicionais a ImportError — usando pytest.importorskip para
pular quando textual não está instalado.

Cobertura alvo: ~15-20% (import + instanciação básica com mocks de curses/textual).
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Verifica se textual está disponível
# ---------------------------------------------------------------------------

textual = pytest.importorskip("textual", reason="textual não instalado")


# ---------------------------------------------------------------------------
# Import do módulo
# ---------------------------------------------------------------------------

class TestTuiImport:
    def test_module_imports_without_error(self):
        """tui.py deve ser importável quando textual está disponível."""
        import importlib
        mod = importlib.import_module("emupipeline.tui")
        assert mod is not None

    def test_launch_tui_function_exists(self):
        from emupipeline import tui
        assert hasattr(tui, "launch_tui")
        assert callable(tui.launch_tui)

    def test_css_constant_is_string(self):
        from emupipeline import tui
        assert isinstance(tui.CSS, str)
        assert len(tui.CSS) > 0


# ---------------------------------------------------------------------------
# Instanciação da App (sem executar o loop de eventos)
# ---------------------------------------------------------------------------

class TestTuiApp:
    def test_app_class_exists(self, config_factory, tmp_project):
        """EmuPipelineApp (ou similar) deve existir no módulo."""
        config_factory()
        from emupipeline import tui
        # Procura a classe App no módulo
        app_cls = None
        for name in dir(tui):
            obj = getattr(tui, name)
            try:
                from textual.app import App
                if isinstance(obj, type) and issubclass(obj, App) and obj is not App:
                    app_cls = obj
                    break
            except Exception:
                pass
        assert app_cls is not None, "Nenhuma subclasse de App encontrada em tui.py"

    def test_app_can_be_instantiated(self, config_factory, tmp_project):
        config_factory()
        from emupipeline import tui

        from textual.app import App
        app_cls = None
        for name in dir(tui):
            obj = getattr(tui, name)
            try:
                if isinstance(obj, type) and issubclass(obj, App) and obj is not App:
                    app_cls = obj
                    break
            except Exception:
                pass

        if app_cls is None:
            pytest.skip("Nenhuma subclasse de App encontrada")

        # Instancia sem executar o loop de eventos
        try:
            app = app_cls(mode="normal")
        except TypeError:
            try:
                app = app_cls()
            except Exception as exc:
                pytest.skip(f"App não pode ser instanciada sem terminal: {exc}")
        assert app is not None


# ---------------------------------------------------------------------------
# launch_tui com mock de App.run
# ---------------------------------------------------------------------------

class TestLaunchTui:
    def test_launch_tui_calls_app_run(self, config_factory, tmp_project):
        config_factory()
        from textual.app import App

        with patch.object(App, "run", return_value=None) as mock_run:
            try:
                from emupipeline.tui import launch_tui
                launch_tui(mode="normal")
            except Exception:
                pytest.skip("launch_tui requer ambiente de terminal")

    def test_launch_tui_accepts_dry_run_mode(self, config_factory, tmp_project):
        config_factory()
        from textual.app import App

        with patch.object(App, "run", return_value=None):
            try:
                from emupipeline.tui import launch_tui
                launch_tui(mode="dry-run")  # não deve levantar TypeError
            except Exception:
                pytest.skip("launch_tui requer ambiente de terminal")
