"""Centralized application logging. Never log API keys or screen contents."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import Config

_CONFIGURED = False
_LOGGER_NAME = "ai_companion"


def setup_logging(log_dir: Path | None = None) -> None:
    """Configure console and rotating file logging once."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    directory = log_dir or Config.LOG_DIR
    directory.mkdir(parents=True, exist_ok=True)
    log_file = directory / "app.log"

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    _CONFIGURED = True
    logger.info("Logging initialized")


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under the application logger."""
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")
