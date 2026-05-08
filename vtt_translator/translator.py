"""High-level translation orchestrator for a single VTT file.

Strategy:
  1. Parse the VTT into Captions.
  2. Split into chunks of N captions (with optional context windows).
  3. Resume: load already-translated captions from the progress store
     (if enabled) and skip chunks that are fully cached.
  4. Translate the remaining chunks concurrently (bounded by
     ``max_concurrent_chunks``). Each chunk uses a numbered-batch prompt;
     incomplete responses are retried once, then missing captions are
     translated one-by-one as a fallback.
  5. After each chunk completes, its partial results are written to the
     progress store so a crash doesn't lose work.
  6. Write the translated VTT using the original timestamps. On success,
     delete the progress file.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Tuple

from .chunker import Chunk, split_into_chunks
from .config import Config
from .llm import LLMProvider, TranslationError, create_provider
from .progress import ProgressStore
from .prompt_builder import build_batch_prompt, build_single_prompt
from .validator import parse_numbered_response, validate_coverage
from .vtt_parser import Caption, parse_vtt, write_vtt


# Max times we retry a whole chunk when numbered coverage is incomplete.
_CHUNK_RETRY_LIMIT = 1


def _format_duration(seconds: float) -> str:
    """Render a duration as e.g. '3m12s' or '45s'."""
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds}s"
    minutes, s = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m{s:02d}s"
    hours, m = divmod(minutes, 60)
    return f"{hours}h{m:02d}m{s:02d}s"


class VttTranslator:
    """Translate a single VTT file end-to-end."""

    def __init__(
        self,
        config: Optional[Config] = None,
        logger: Optional[logging.Logger] = None,
        provider: Optional[LLMProvider] = None,
    ) -> None:
        self.config = config or Config()
        self.logger = logger or logging.getLogger(__name__)
        self.provider = provider or create_provider(self.config, self.logger)

    # ---------------------------------------------------------------- API
    def translate_vtt(
        self,
        input_file: str | Path,
        output_file: str | Path,
        *,
        resume: Optional[bool] = None,
    ) -> bool:
        """Translate ``input_file`` and write results to ``output_file``.

        Args:
            input_file: Source VTT path.
            output_file: Destination VTT path.
            resume: If None (default) use ``config.enable_resume``. Pass
                False to force a fresh translation even if a progress file
                exists (this also deletes any stale progress file).

        Returns:
            True on success, False if parsing/writing fails catastrophically.
            Per-caption translation failures do NOT fail the whole file;
            they are filled with the original text when ``fallback_to_source``
            is set.
        """
        try:
            self.logger.info("Parsing VTT: %s", input_file)
            captions = parse_vtt(input_file)
        except Exception as e:
            self.logger.error("Failed to parse %s: %s", input_file, e)
            return False

        if not captions:
            self.logger.warning("No captions found in %s; writing empty output", input_file)
            try:
                write_vtt(output_file, [], {})
                return True
            except Exception as e:
                self.logger.error("Failed to write empty output %s: %s", output_file, e)
                return False

        self.logger.info(
            "Parsed %d captions; chunking with size=%d, context_window=%d",
            len(captions), self.config.chunk_size, self.config.context_window,
        )
        chunks = split_into_chunks(
            captions,
            chunk_size=self.config.chunk_size,
            context_window=self.config.context_window,
        )
        self.logger.info("Split into %d chunk(s)", len(chunks))

        # ---- Resume: load any previously-translated captions ----
        resume_enabled = self.config.enable_resume if resume is None else bool(resume)
        progress = ProgressStore(
            log_dir=self.config.log_dir,
            input_file=input_file,
            config_fingerprint=self.config.resume_fingerprint(),
            enabled=resume_enabled,
            logger=self.logger,
        )
        if resume_enabled:
            cached = progress.load()
        else:
            # User asked for no-resume: make sure any stale progress file is gone.
            progress.clear()
            cached = {}

        # Seed the results dict with cached translations.
        translations: Dict[int, str] = dict(cached)
        translations_lock = Lock()

        # ---- Pick which chunks still need work ----
        pending: List[Tuple[int, Chunk]] = []
        for i, chunk in enumerate(chunks):
            needed = [cap.index for cap in chunk.target if cap.index not in cached]
            if needed:
                pending.append((i, chunk))

        if cached:
            self.logger.info(
                "Resume: %d/%d caption(s) cached; %d/%d chunk(s) still need translation",
                len(cached), len(captions), len(pending), len(chunks),
            )

        # ---- Translate pending chunks concurrently ----
        failed_count = 0
        max_workers = max(1, min(self.config.max_concurrent_chunks, len(pending) or 1))

        if pending:
            self.logger.info(
                "Translating %d chunk(s) with up to %d worker(s)",
                len(pending), max_workers,
            )
            run_start = time.monotonic()
            total_chunks = len(chunks)

            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="vtt-chunk") as ex:
                future_to_meta: Dict[Future, Tuple[int, Chunk]] = {}
                for i, chunk in pending:
                    # Each chunk carries a human-readable tag so the provider
                    # and worker can include it in log lines.
                    tag = f"chunk {i + 1}/{total_chunks}"
                    future_to_meta[ex.submit(self._translate_chunk, chunk, tag)] = (i, chunk)

                completed = 0
                for fut in as_completed(future_to_meta):
                    i, chunk = future_to_meta[fut]
                    completed += 1
                    try:
                        chunk_results, chunk_failures = fut.result()
                    except Exception as e:
                        # A worker raised something non-TranslationError.
                        # Treat every target caption in this chunk as failed;
                        # later code will source-fallback them.
                        self.logger.exception(
                            "Unexpected error translating chunk %d/%d: %s",
                            i + 1, total_chunks, e,
                        )
                        chunk_results = {}
                        chunk_failures = len(chunk.target)

                    # Progress + ETA. Only meaningful after the second
                    # completion so we have a rate estimate.
                    eta_str = ""
                    if completed >= 2 and completed < len(pending):
                        elapsed = time.monotonic() - run_start
                        per_chunk = elapsed / completed
                        remaining = per_chunk * (len(pending) - completed)
                        eta_str = f", ETA {_format_duration(remaining)}"
                    self.logger.info(
                        "Chunk %d/%d done (%d/%d completed this run%s)",
                        i + 1, total_chunks, completed, len(pending), eta_str,
                    )

                    # Merge results atomically and persist progress.
                    with translations_lock:
                        translations.update(chunk_results)
                        failed_count += chunk_failures
                    progress.update(chunk_results)

        # ---- Source-fallback anything still missing ----
        missing = [c.index for c in captions if c.index not in translations]
        if missing:
            self.logger.warning(
                "%d caption(s) still missing after translation; using source text",
                len(missing),
            )
            for idx in missing:
                cap = captions[idx]
                translations[idx] = self._source_fallback(cap)

        # ---- Write output ----
        try:
            write_vtt(output_file, captions, translations)
        except Exception as e:
            self.logger.error("Failed to write %s: %s", output_file, e)
            return False

        total_fallbacks = failed_count + len(missing)
        self.logger.info(
            "Done: wrote %s (%d translated, %d fallback-to-source)",
            output_file,
            len(captions) - total_fallbacks,
            total_fallbacks,
        )
        # Only clear progress on a clean write.
        progress.clear()
        return True

    # ----------------------------------------------------------- Internals
    def _translate_chunk(
        self, chunk: Chunk, tag: str = "chunk",
    ) -> Tuple[Dict[int, str], int]:
        """Translate one chunk. Returns (results-by-source-index, failure_count).

        Safe to call from a worker thread: uses no shared mutable state.

        Args:
            chunk: Captions plus optional context windows.
            tag: Human-readable identifier (e.g. ``"chunk 3/12"``). Included
                in log lines and propagated to the LLM provider so its retry
                messages are attributable to the right work item.
        """
        target = chunk.target
        expected = len(target)
        if expected == 0:
            return {}, 0

        self.logger.info(
            "Translating %s (%d captions, +%d/+%d context)",
            tag, expected, len(chunk.prev_context), len(chunk.next_context),
        )

        # Map in-chunk 1-based numbers -> source Caption.index.
        idx_map = {i + 1: cap.index for i, cap in enumerate(target)}

        parsed = self._call_with_chunk_retry(chunk, tag=tag)

        results: Dict[int, str] = {}
        for local_idx, text in parsed.items():
            if local_idx in idx_map:
                results[idx_map[local_idx]] = text

        # Find gaps and fall back one-by-one.
        missing_local = [i for i in range(1, expected + 1) if i not in parsed]
        failure_count = 0
        for local_idx in missing_local:
            cap = target[local_idx - 1]
            # Demoted to DEBUG: this is noisy on files with flaky numbered
            # responses and doesn't help at the batch level. The warning
            # below still fires when fallback fails.
            self.logger.debug(
                "Single-caption fallback for source index %d: %r",
                cap.index, cap.text[:80],
            )
            text = self._translate_single_caption(cap, tag=tag)
            if text is None:
                failure_count += 1
                text = self._source_fallback(cap)
                self.logger.warning(
                    "Falling back to source text for caption %d (%s)",
                    cap.index, tag,
                )
            results[cap.index] = text

        return results, failure_count

    def _call_with_chunk_retry(
        self, chunk: Chunk, *, tag: str = "chunk",
    ) -> Dict[int, str]:
        """Send a chunk to the LLM, retrying once if coverage is incomplete."""
        attempt = 0
        best_parsed: Dict[int, str] = {}
        expected = len(chunk.target)

        while attempt <= _CHUNK_RETRY_LIMIT:
            prompt = build_batch_prompt(
                chunk,
                source_lang=self.config.source_language_name(),
                target_lang=self.config.target_language_name(),
            )
            try:
                response = self.provider.complete(
                    prompt, max_tokens=self.config.max_tokens, tag=tag,
                )
            except TranslationError as e:
                self.logger.error(
                    "LLM call failed for %s (attempt %d): %s",
                    tag, attempt + 1, e,
                )
                return best_parsed

            parsed = parse_numbered_response(response)
            complete, missing, unexpected = validate_coverage(parsed, expected)
            # Keep the best (most complete) response across attempts.
            if len(parsed) > len(best_parsed):
                best_parsed = parsed

            if complete:
                return parsed

            self.logger.warning(
                "Incomplete numbered response for %s (attempt %d): got %d/%d, missing=%s, unexpected=%s",
                tag, attempt + 1, len(parsed), expected, missing[:5], unexpected[:5],
            )
            attempt += 1

        return best_parsed

    def _translate_single_caption(
        self, cap: Caption, *, tag: str = "single-caption",
    ) -> Optional[str]:
        """Translate a single caption in isolation. Returns None on failure."""
        prompt = build_single_prompt(
            cap.text,
            source_lang=self.config.source_language_name(),
            target_lang=self.config.target_language_name(),
        )
        try:
            text = self.provider.complete(
                prompt,
                max_tokens=self.config.max_tokens,
                tag=f"{tag}/cap-{cap.index}",
            )
        except TranslationError as e:
            self.logger.error(
                "Single-caption LLM call failed for caption %d (%s): %s",
                cap.index, tag, e,
            )
            return None

        # Strip any accidental `[N]` prefix the model may have added.
        text = text.strip()
        if text.startswith("[") and "]" in text[:6]:
            text = text.split("]", 1)[1].strip()
        return text or None

    def _source_fallback(self, cap: Caption) -> str:
        """Return the original text (optionally marked) when translation fails."""
        if not self.config.fallback_to_source:
            return ""
        if self.config.fallback_marker:
            return f"{cap.text} {self.config.fallback_marker}".strip()
        return cap.text
