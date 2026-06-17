"""
Fábrica de loggers com duas saídas:

  Console → texto legível, nível configurável
  Arquivo → JSON estruturado (quando structured_logging=true no config)
             ou texto (fallback)

Separação técnico vs usuário via campo `user_facing=True` no extra.
"""

from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


class JsonFormatter(logging.Formatter):
    """Uma linha JSON por evento — ingestível por ELK/Grafana/Loki."""

    def format(self, record: logging.LogRecord) -> str:
        data: dict = {
            "ts":     self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":  record.levelname,
            "logger": record.name,
            "msg":    record.getMessage(),
            "thread": record.thread,
        }
        for field in ("step", "file", "duration_s", "stats", "run_id"):
            if hasattr(record, field):
                data[field] = getattr(record, field)
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


_TEXT_FMT = logging.Formatter(
    "%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)

_configured: set[str] = set()


def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if name in _configured:
        return logger
    _configured.add(name)

    # Lê config de forma lazy para evitar import circular
    level = logging.INFO
    log_dir: Path | None = None
    use_json = False
    try:
        from emupipeline.core.config import cfg
        level_str = cfg.get("global", "logging_level", "INFO")
        level = getattr(logging, level_str.upper(), logging.INFO)
        log_dir = cfg.base_dir / "output" / "logs"
        use_json = bool(cfg.get("global", "structured_logging", False))
    except Exception:
        pass

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Console — sempre texto legível
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(_TEXT_FMT)
    ch.setLevel(level)
    logger.addHandler(ch)

    # Arquivo — JSON ou texto, rotação automática
    if log_dir:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(
                log_dir / "pipeline.log",
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            fh.setFormatter(JsonFormatter() if use_json else _TEXT_FMT)
            fh.setLevel(logging.DEBUG)
            logger.addHandler(fh)
        except OSError:
            pass

    return logger
