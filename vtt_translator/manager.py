"""Batch file processing manager."""

from __future__ import annotations

import logging
import os
import random
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .config import Config
from .llm import create_provider
from .translator import VttTranslator
from .utils import ensure_dir, get_file_logger, move_file, setup_logger


class VttTranslatorManager:
    """Discovers VTT files and translates them in sequence.

    The provider is constructed once and reused for every file, reducing
    connection overhead.
    """

    def __init__(
        self,
        config: Optional[Config | str | Path | dict] = None,
        logger: Optional[logging.Logger] = None,
        *,
        resume: Optional[bool] = None,
    ) -> None:
        self.config = _coerce_config(config)
        # resume=None -> use config.enable_resume per-file; True/False -> override.
        self.resume = resume

        for key in ("input_dir", "output_dir", "done_dir", "log_dir"):
            ensure_dir(getattr(self.config, key))

        self.logger = logger or setup_logger(
            self.config.log_dir,
            f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
            logger_name=f"batch_{id(self)}",
        )

        # Share a single provider across all files.
        self.provider = create_provider(self.config, self.logger)

    # ---------------------------------------------------------------- API
    def find_vtt_files(self, input_dir: Optional[Path] = None) -> List[Path]:
        """Return unprocessed .vtt files in the input directory, sorted."""
        dir_ = Path(input_dir) if input_dir else self.config.input_dir
        if not dir_.exists():
            return []

        files: List[Path] = []
        for name in os.listdir(dir_):
            if not name.endswith(".vtt"):
                continue
            lang = self.config.target_language
            if name.endswith(f"-{lang}.vtt") or name.endswith(f"_{lang}.vtt"):
                continue
            if (self.config.done_dir / name).exists():
                continue
            base = Path(name).stem
            # Target-language suffix (e.g. -zh.vtt) signals already-translated.
            translated_name = f"{base}-{self.config.target_language}.vtt"
            if (self.config.output_dir / translated_name).exists():
                continue
            files.append(dir_ / name)
        return sorted(files)

    def process_file(self, input_file: Path) -> bool:
        """Translate one file; move source to `done_dir` on success."""
        input_file = Path(input_file)
        base = input_file.stem
        output_file = self.config.output_dir / f"{base}-{self.config.target_language}.vtt"

        file_logger = get_file_logger(self.config.log_dir, input_file)
        self.logger.info("Starting: %s", input_file.name)

        start = time.time()
        try:
            translator = VttTranslator(self.config, file_logger, provider=self.provider)
            success = translator.translate_vtt(input_file, output_file, resume=self.resume)
        except Exception as e:
            self.logger.exception("Unhandled error for %s: %s", input_file.name, e)
            return False

        duration = time.time() - start
        if success:
            self.logger.info("Success: %s (%.1fs)", input_file.name, duration)
            try:
                move_file(input_file, self.config.done_dir)
            except OSError as e:
                self.logger.warning("Could not move %s to done dir: %s", input_file.name, e)
            return True

        self.logger.error("Failure: %s (%.1fs)", input_file.name, duration)
        return False

    def batch_process(
        self,
        start_index: int = 0,
        end_index: Optional[int] = None,
    ) -> Tuple[int, int]:
        """Translate a slice of discovered files. Returns (successes, total)."""
        files = self.find_vtt_files()
        if not files:
            self.logger.info("No VTT files to process")
            return 0, 0

        if end_index is None or end_index > len(files):
            end_index = len(files)
        selected = files[start_index:end_index]

        if not selected:
            self.logger.info("Range [%d:%d] is empty", start_index, end_index)
            return 0, 0

        self.logger.info("Batch: %d file(s) selected", len(selected))
        for i, f in enumerate(selected, start=1):
            self.logger.info("  %d. %s", i, f.name)

        successes = 0
        for i, f in enumerate(selected):
            if self.process_file(f):
                successes += 1
            if i < len(selected) - 1:
                self._sleep_between_files()

        self.logger.info("Batch complete: %d/%d succeeded", successes, len(selected))
        return successes, len(selected)

    # ----------------------------------------------------------- Internals
    def _sleep_between_files(self) -> None:
        lo, hi = self.config.min_sleep_time, self.config.max_sleep_time
        if hi <= 0:
            return
        wait = random.randint(lo, hi) if hi > lo else hi
        self.logger.info("Sleeping %ds before next file...", wait)
        time.sleep(wait)


def _coerce_config(value: Optional[Config | str | Path | dict]) -> Config:
    """Accept Config, str/Path (file path), dict, or None."""
    if value is None:
        return Config()
    if isinstance(value, Config):
        return value
    if isinstance(value, dict):
        return Config(**value)
    if isinstance(value, (str, Path)):
        return Config.load(value)
    raise TypeError(f"Unsupported config type: {type(value).__name__}")
