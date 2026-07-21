"""
Testes para emupipeline.core.logger.

Cobertura: JsonFormatter.format() (linhas 24-36), OSError no file handler (89-90),
setup_logger com structured_logging=True.
"""

from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# JsonFormatter
# ---------------------------------------------------------------------------

class TestJsonFormatter:
    def _make_record(
        self,
        name: str = "test",
        level: int = logging.INFO,
        msg: str = "hello",
        exc_info: object = None,
    ) -> logging.LogRecord:
        return logging.LogRecord(
            name=name, level=level,
            pathname="", lineno=0,
            msg=msg, args=(), exc_info=exc_info,
        )

    def test_format_returns_valid_json(self):
        from emupipeline.core.logger import JsonFormatter
        fmt = JsonFormatter()
        record = self._make_record()
        result = fmt.format(record)
        data = json.loads(result)
        assert data["level"] == "INFO"
        assert data["msg"] == "hello"
        assert data["logger"] == "test"
        assert "ts" in data
        assert "thread" in data

    def test_format_includes_optional_step_field(self):
        from emupipeline.core.logger import JsonFormatter
        fmt = JsonFormatter()
        record = self._make_record()
        record.step = "DatSplitter"
        result = fmt.format(record)
        data = json.loads(result)
        assert data["step"] == "DatSplitter"

    def test_format_includes_optional_duration_field(self):
        from emupipeline.core.logger import JsonFormatter
        fmt = JsonFormatter()
        record = self._make_record()
        record.duration_s = 3.14
        result = fmt.format(record)
        data = json.loads(result)
        assert data["duration_s"] == pytest.approx(3.14)

    def test_format_includes_exc_info(self):
        from emupipeline.core.logger import JsonFormatter
        fmt = JsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            exc_info = sys.exc_info()
        record = self._make_record(level=logging.ERROR, exc_info=exc_info)
        result = fmt.format(record)
        data = json.loads(result)
        assert "exc" in data
        assert "ValueError" in data["exc"]
        assert "boom" in data["exc"]

    def test_format_skips_absent_optional_fields(self):
        from emupipeline.core import logger as logger_mod
        from emupipeline.core.logger import JsonFormatter, reset_run_id
        reset_run_id()
        fmt = JsonFormatter()
        record = self._make_record()
        result = fmt.format(record)
        data = json.loads(result)
        # run_id é gerado automaticamente ao primeiro log estruturado — deve existir
        assert "run_id" in data
        # campos opcionais que dependem de atributos no record não devem estar presentes
        for field in ("step", "file", "duration_s", "stats"):
            assert field not in data


# ---------------------------------------------------------------------------
# setup_logger
# ---------------------------------------------------------------------------

class TestSetupLogger:
    def _unique_name(self, suffix: str) -> str:
        """Gera nome único para evitar colisão com loggers já configurados."""
        import random
        return f"_test_{suffix}_{random.randint(100000, 999999)}"

    def test_returns_logger_instance(self, config_factory):
        config_factory()
        from emupipeline.core.logger import setup_logger
        name = self._unique_name("basic")
        logger = setup_logger(name)
        assert isinstance(logger, logging.Logger)

    def test_idempotent_second_call_returns_same(self, config_factory):
        config_factory()
        from emupipeline.core.logger import setup_logger
        name = self._unique_name("idem")
        l1 = setup_logger(name)
        l2 = setup_logger(name)
        assert l1 is l2

    def test_logger_has_console_handler(self, config_factory):
        config_factory()
        from emupipeline.core.logger import setup_logger
        name = self._unique_name("console")
        logger = setup_logger(name)
        assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)

    def test_logger_has_file_handler_when_log_dir_set(self, config_factory):
        config_factory()
        from emupipeline.core.logger import setup_logger
        name = self._unique_name("file")
        logger = setup_logger(name)
        assert any(isinstance(h, RotatingFileHandler) for h in logger.handlers)

    def test_oserror_on_file_handler_does_not_crash(self, config_factory):
        """OSError ao criar RotatingFileHandler é silenciada — logger ainda é retornado."""
        config_factory()
        from emupipeline.core.logger import _configured, setup_logger
        name = self._unique_name("oserr")
        _configured.discard(name)

        with patch("emupipeline.core.logger.RotatingFileHandler", side_effect=OSError("disk full")):
            logger = setup_logger(name)

        assert isinstance(logger, logging.Logger)
        # Apenas o console handler deve estar presente
        assert all(not isinstance(h, RotatingFileHandler) for h in logger.handlers)

    def test_structured_logging_uses_json_formatter(self, config_factory):
        """structured_logging=True deve usar JsonFormatter no handler de arquivo."""
        config_factory({"global": {"structured_logging": True}})
        from emupipeline.core.logger import JsonFormatter, _configured, setup_logger
        name = self._unique_name("json")
        _configured.discard(name)

        logger = setup_logger(name)

        json_handlers = [
            h for h in logger.handlers
            if isinstance(h, RotatingFileHandler) and isinstance(h.formatter, JsonFormatter)
        ]
        assert len(json_handlers) >= 1
