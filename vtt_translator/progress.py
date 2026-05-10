"""Per-file translation progress store (resumable translation).

Progress is stored as a JSON file under `<log_dir>/.progress/`, keyed by a
short hash of the absolute input path. The file stores translations at the
caption level (source-index -> translated text), so resuming with a
different `chunk_size` or `context_window` still benefits from previously
translated captions.

A progress file is invalidated (and silently ignored) when any of the
following change between runs:

- The input file's SHA1 or mtime (i.e. the user edited it).
- The resume fingerprint returned by ``Config.resume_fingerprint()``
  (e.g. target_language, model_id, provider).

The file is deleted after the full translation completes successfully.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, Optional

_PROGRESS_SCHEMA_VERSION = 1
_PROGRESS_DIR_NAME = ".progress"


def _sha1_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Compute SHA1 of a file's contents as a hex digest."""
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _path_key(input_file: Path) -> str:
    """Short hash of the absolute input path, used as the progress file name."""
    abs_path = str(input_file.resolve())
    return hashlib.sha1(abs_path.encode("utf-8")).hexdigest()[:12]


class ProgressStore:
    """Load/save per-file translation progress with atomic writes.

    Thread-safe for concurrent `update` calls made during chunk-level
    concurrency within a single file. Not safe for concurrent *file-level*
    writers against the same input file (which the pipeline never does).
    """

    def __init__(
        self,
        log_dir: str | Path,
        input_file: str | Path,
        config_fingerprint: dict,
        enabled: bool = True,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self.input_file = Path(input_file).resolve()
        self.enabled = enabled
        self._fingerprint = dict(config_fingerprint)
        self._translations: Dict[int, str] = {}
        self._dirty_lock = Lock()
        # Cached SHA1 of the input file — computed once and reused across
        # multiple _flush_locked() calls within the same run.
        self._input_sha1: Optional[str] = None

        progress_dir = Path(log_dir) / _PROGRESS_DIR_NAME
        self.progress_file = progress_dir / f"{_path_key(self.input_file)}.json"

    # ------------------------------------------------------------------ API

    def load(self) -> Dict[int, str]:
        """Return already-translated captions from a valid progress file, if any.

        If the progress file is missing, corrupt, stale, or doesn't match the
        current config/input, returns an empty dict (no error).
        """
        if not self.enabled:
            self._translations = {}
            return {}

        if not self.progress_file.exists():
            self._translations = {}
            return {}

        try:
            with self.progress_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            self.logger.warning(
                "Progress file %s is unreadable (%s); ignoring and starting fresh",
                self.progress_file, e,
            )
            self._translations = {}
            return {}

        if data.get("version") != _PROGRESS_SCHEMA_VERSION:
            self.logger.info(
                "Progress file %s has an unknown schema version; ignoring",
                self.progress_file,
            )
            self._translations = {}
            return {}

        if not self._input_matches(data):
            self.logger.info(
                "Progress file %s no longer matches the input (hash/mtime changed); ignoring",
                self.progress_file,
            )
            self._translations = {}
            return {}

        if data.get("config_fingerprint") != self._fingerprint:
            self.logger.info(
                "Progress file %s was produced with a different configuration; ignoring",
                self.progress_file,
            )
            self._translations = {}
            return {}

        raw = data.get("translations", {})
        # JSON object keys are strings; convert to int indices.
        try:
            translations = {int(k): v for k, v in raw.items() if isinstance(v, str)}
        except (TypeError, ValueError):
            self.logger.warning("Progress file %s has malformed keys; ignoring", self.progress_file)
            self._translations = {}
            return {}

        self._translations = dict(translations)
        self.logger.info(
            "Resuming from progress file: %d caption(s) already translated",
            len(self._translations),
        )
        return dict(self._translations)

    def update(self, new_translations: Dict[int, str]) -> None:
        """Merge new translations into the store and flush to disk atomically."""
        if not self.enabled or not new_translations:
            return

        with self._dirty_lock:
            self._translations.update(new_translations)
            self._flush_locked()

    def clear(self) -> None:
        """Delete the progress file.

        Always runs regardless of ``enabled`` — this is called both after a
        successful translation and, in ``--no-resume`` mode, before starting
        a run to discard any stale progress file.
        """
        try:
            self.progress_file.unlink()
            self.logger.debug("Deleted progress file: %s", self.progress_file)
        except FileNotFoundError:
            pass
        except OSError as e:
            self.logger.warning("Could not delete progress file %s: %s", self.progress_file, e)

    # ------------------------------------------------------------ Internals

    def _input_matches(self, data: dict) -> bool:
        try:
            expected_sha = data.get("input_sha1")
            expected_mtime = data.get("input_mtime")
        except AttributeError:
            return False
        if not expected_sha or expected_mtime is None:
            return False
        try:
            actual_mtime = self.input_file.stat().st_mtime
        except OSError:
            return False
        if abs(actual_mtime - float(expected_mtime)) > 1.0:
            # mtime drift tolerance of 1s covers filesystems with coarse mtime
            # resolution while still catching real edits.
            return False
        actual_sha = _sha1_file(self.input_file)
        if actual_sha == expected_sha:
            # Cache the SHA1 so _flush_locked() doesn't recompute it.
            self._input_sha1 = actual_sha
            return True
        return False

    def _flush_locked(self) -> None:
        """Write the current state to disk atomically. Caller must hold the lock."""
        progress_dir = self.progress_file.parent
        progress_dir.mkdir(parents=True, exist_ok=True)

        try:
            stat = self.input_file.stat()
        except OSError as e:
            self.logger.warning("Cannot stat input %s while saving progress: %s", self.input_file, e)
            return

        # Use cached SHA1 if available; compute and cache on first flush.
        if self._input_sha1 is None:
            self._input_sha1 = _sha1_file(self.input_file)

        payload = {
            "version": _PROGRESS_SCHEMA_VERSION,
            "input_file": str(self.input_file),
            "input_sha1": self._input_sha1,
            "input_mtime": stat.st_mtime,
            "config_fingerprint": self._fingerprint,
            "translations": {str(k): v for k, v in self._translations.items()},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        # Atomic write: tempfile in the same directory, then rename.
        fd, tmp_name = tempfile.mkstemp(
            prefix=self.progress_file.stem + ".", suffix=".tmp", dir=str(progress_dir)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_name, self.progress_file)
        except Exception:
            # Best-effort cleanup; re-raise so callers notice.
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
