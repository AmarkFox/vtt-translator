"""Shared utilities: logging, file operations."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


_LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(
    log_dir: str | Path,
    log_file_name: Optional[str] = None,
    logger_name: Optional[str] = None,
    console: bool = True,
    level: int = logging.INFO,
) -> logging.Logger:
    """Create a logger that writes to a file and optionally the console.

    Args:
        log_dir: Directory for log files (created if missing).
        log_file_name: Log file name. Defaults to a timestamped name.
        logger_name: Explicit logger name. Defaults to the log file name.
        console: If True, also attach a StreamHandler.
        level: Log level.

    Returns:
        A configured logger. Idempotent: repeated calls with the same name
        will not duplicate handlers.
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    if log_file_name is None:
        log_file_name = f"translation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    if logger_name is None:
        logger_name = log_file_name

    logger = logging.getLogger(logger_name)
    logger.setLevel(level)
    # Don't propagate to root, which may have its own handlers.
    logger.propagate = False

    # Avoid adding duplicate handlers on repeated calls.
    if logger.handlers:
        return logger

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = logging.FileHandler(log_dir / log_file_name, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger


def get_file_logger(log_dir: str | Path, input_file: str | Path) -> logging.Logger:
    """Create a per-file logger that writes to its own log file only (no console).

    This prevents duplicate console output when a batch run's main logger is
    already emitting to the console.
    """
    base_name = Path(input_file).stem
    log_file = f"{base_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    # Unique logger name so handlers do not leak between files.
    logger_name = f"file:{log_file}"
    return setup_logger(log_dir, log_file, logger_name=logger_name, console=False)


def ensure_dir(directory: str | Path) -> Path:
    """Create the directory if it does not exist."""
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    return path


def move_file(source_path: str | Path, target_dir: str | Path) -> Path:
    """Move a file into `target_dir`, creating the target directory if needed."""
    src = Path(source_path)
    dst_dir = Path(target_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    shutil.move(str(src), str(dst))
    return dst
