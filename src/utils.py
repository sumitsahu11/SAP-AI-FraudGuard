# src/utils.py

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import LOGS_DIR, ALLOWED_EXTENSIONS


def setup_logging():
    LOGS_DIR.mkdir(exist_ok=True)
    log_file = LOGS_DIR / "app.log"

    logger = logging.getLogger("fraudguard")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


LOGGER = setup_logging()


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS