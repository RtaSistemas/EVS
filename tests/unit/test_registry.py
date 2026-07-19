"""
Testes para emupipeline.core.registry.

Cobertura: register() com/sem meta e com ID duplicado, autodiscover()
idempotência e falha de import, get_step() KeyError, get_by_menu_number(),
get_all_steps(), get_pipeline_steps().
"""

from __future__ import annotations

import importlib
import pkgutil
from unittest.mock import MagicMock, patch

import pytest

import emupipeline.core.registry as registry_module
from emupipeline.core.step_interface import StepMeta

# ---------------------------------------------------------------------------
# register() decorator
# ---------------------------------------------------------------------------

class TestRegister:
    def test_no_meta_raises_type_error(self):
        """Classe sem atributo `meta` deve levantar TypeError."""
        class NoMeta:
            pass

        with pytest.raises(TypeError, match="não tem atributo"):
            registry_module.register(NoMeta)

    def test_duplicate_id_different_class_raises_value_error(self, monkeypatch):
        """Dois steps com mesmo ID mas classes diferentes devem gerar ValueError."""
        class StepA:
            meta = StepMeta(id="__dup_test__", menu_number=990, label="A", group="G", description="A")

        class StepB:
            meta = StepMeta(id="__dup_test__", menu_number=991, label="B", group="G", description="B")

        monkeypatch.setitem(registry_module._REGISTRY, "__dup_test__", StepA)

        with pytest.raises(ValueError, match="duplicado"):
            registry_module.register(StepB)

    def test_duplicate_same_class_is_idempotent(self, monkeypatch):
        """Registrar a mesma classe duas vezes não deve levantar exceção."""
        class StepSame:
            meta = StepMeta(id="__same_test__", menu_number=992, label="S", group="G", description="S")

        monkeypatch.setitem(registry_module._REGISTRY, "__same_test__", StepSame)
        result = registry_module.register(StepSame)
        assert result is StepSame

    def test_register_returns_class_unchanged(self, monkeypatch):
        """@register deve retornar a própria classe (sem modificação)."""
        class StepNew:
            meta = StepMeta(id="__new_test__", menu_number=993, label="N", group="G", description="N")

        monkeypatch.setitem(registry_module._REGISTRY, "__new_test__", StepNew)
        returned = registry_module.register(StepNew)
        assert returned is StepNew


# ---------------------------------------------------------------------------
# autodiscover()
# ---------------------------------------------------------------------------

class TestAutodiscover:
    def test_idempotent_when_registry_populated(self, monkeypatch):
        """autodiscover() retorna imediatamente quando _REGISTRY já está populado."""
        monkeypatch.setitem(registry_module._REGISTRY, "__dummy_step__", object)
        with patch.object(pkgutil, "iter_modules") as mock_iter:
            registry_module.autodiscover()
        mock_iter.assert_not_called()

    def test_failing_import_logs_warning_not_raises(self, monkeypatch, caplog):
        """Falha de import de um step deve gerar WARNING, não exception."""
        import logging

        monkeypatch.setattr(registry_module, "_REGISTRY", {})

        fake_info = MagicMock()
        fake_info.name = "step_broken"

        with (
            patch.object(pkgutil, "iter_modules", return_value=[fake_info]),
            patch.object(importlib, "import_module", side_effect=ImportError("broken")),
            caplog.at_level(logging.WARNING, logger="Registry"),
        ):
            registry_module.autodiscover()

        assert "step_broken" in caplog.text

    def test_entry_points_failure_is_silenced(self, monkeypatch):
        """Falha ao carregar entry_points deve ser silenciada (não levantar)."""
        monkeypatch.setattr(registry_module, "_REGISTRY", {})

        with (
            patch.object(pkgutil, "iter_modules", return_value=[]),
            patch("importlib.metadata.entry_points", side_effect=RuntimeError("no ep")),
        ):
            registry_module.autodiscover()

    def test_plugin_load_failure_logs_warning_not_raises(self, monkeypatch, caplog):
        """Falha ao carregar plugin via ep.load() gera WARNING, não exception (linhas 73-76)."""
        import logging

        monkeypatch.setattr(registry_module, "_REGISTRY", {})

        fake_ep = MagicMock()
        fake_ep.name = "broken_plugin"
        fake_ep.load.side_effect = RuntimeError("plugin broken")

        with (
            patch.object(pkgutil, "iter_modules", return_value=[]),
            patch("importlib.metadata.entry_points", return_value=[fake_ep]),
            caplog.at_level(logging.WARNING, logger="Registry"),
        ):
            registry_module.autodiscover()

        assert "broken_plugin" in caplog.text


# ---------------------------------------------------------------------------
# get_step()
# ---------------------------------------------------------------------------

class TestGetStep:
    def test_known_step_returns_class(self):
        cls = registry_module.get_step("dat_split")
        assert cls is not None
        assert cls.__name__ == "DatSplitter"

    def test_another_known_step(self):
        cls = registry_module.get_step("convert_webp")
        assert cls.__name__ == "WebPConverter"

    def test_unknown_step_raises_key_error(self):
        with pytest.raises(KeyError):
            registry_module.get_step("__nonexistent_step_id_xyz__")

    def test_key_error_message_lists_available(self):
        with pytest.raises(KeyError, match="Disponíveis"):
            registry_module.get_step("__nonexistent_xyz__")

    def test_calls_autodiscover_when_registry_empty(self, monkeypatch):
        """get_step() chama autodiscover() quando _REGISTRY está vazio (linha 83)."""
        monkeypatch.setattr(registry_module, "_REGISTRY", {})

        with (
            patch.object(registry_module, "autodiscover") as mock_auto,
            pytest.raises(KeyError),
        ):
            registry_module.get_step("__any__")

        mock_auto.assert_called_once()


# ---------------------------------------------------------------------------
# get_by_menu_number()
# ---------------------------------------------------------------------------

class TestGetByMenuNumber:
    def test_existing_menu_number_returns_class(self):
        cls = registry_module.get_by_menu_number(6)  # WebPConverter
        assert cls is not None
        assert cls.__name__ == "WebPConverter"

    def test_menu_number_1_returns_dat_splitter(self):
        cls = registry_module.get_by_menu_number(1)
        assert cls is not None
        assert cls.__name__ == "DatSplitter"

    def test_nonexistent_menu_number_returns_none(self):
        result = registry_module.get_by_menu_number(99_999)
        assert result is None

    def test_calls_autodiscover_when_registry_empty(self, monkeypatch):
        """get_by_menu_number() chama autodiscover() quando _REGISTRY está vazio (linha 94)."""
        monkeypatch.setattr(registry_module, "_REGISTRY", {})

        with patch.object(registry_module, "autodiscover") as mock_auto:
            result = registry_module.get_by_menu_number(9999)

        mock_auto.assert_called_once()
        assert result is None


# ---------------------------------------------------------------------------
# get_all_steps()
# ---------------------------------------------------------------------------

class TestGetAllSteps:
    def test_returns_nonempty_dict(self):
        steps = registry_module.get_all_steps()
        assert isinstance(steps, dict)
        assert len(steps) > 0

    def test_returns_copy_not_reference(self):
        """Modificar o resultado não deve alterar o registry interno."""
        steps = registry_module.get_all_steps()
        steps["__injected__"] = None
        assert "__injected__" not in registry_module._REGISTRY

    def test_calls_autodiscover_when_registry_empty(self, monkeypatch):
        """get_all_steps() chama autodiscover() quando _REGISTRY está vazio (linha 103)."""
        monkeypatch.setattr(registry_module, "_REGISTRY", {})

        with patch.object(registry_module, "autodiscover") as mock_auto:
            result = registry_module.get_all_steps()

        mock_auto.assert_called_once()
        assert result == {}

    def test_known_steps_present(self):
        steps = registry_module.get_all_steps()
        assert "dat_split" in steps
        assert "convert_webp" in steps


# ---------------------------------------------------------------------------
# get_pipeline_steps()
# ---------------------------------------------------------------------------

class TestGetPipelineSteps:
    def test_returns_list(self):
        steps = registry_module.get_pipeline_steps()
        assert isinstance(steps, list)
        assert len(steps) > 0

    def test_sorted_by_pipeline_order(self):
        steps = registry_module.get_pipeline_steps()
        orders = [cls.meta.pipeline_order for cls in steps]
        assert orders == sorted(orders)

    def test_excludes_steps_with_order_999_or_higher(self):
        steps = registry_module.get_pipeline_steps()
        assert all(cls.meta.pipeline_order < 999 for cls in steps)
