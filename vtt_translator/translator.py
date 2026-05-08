"""High-level translation orchestrator for a single VTT file.

Strategy:
  1. Parse the VTT into Captions.
  2. Split into chunks of N captions (with optional context windows).
  3. For each chunk, send a numbered-batch prompt to the LLM and parse
     the numbered response.
  4. If any caption index is missing from the response, retry the chunk
     once. Any still-missing captions are translated individually. Final
     fallback: the original source text (with an optional marker).
  5. Write the translated VTT using the original timestamps.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from .chunker import Chunk, split_into_chunks
from .config import Config
from .llm import LLMProvider, TranslationError, create_provider
from .prompt_builder import build_batch_prompt, build_single_prompt
from .validator import parse_numbered_response, validate_coverage
from .vtt_parser import Caption, parse_vtt, write_vtt


# Max times we retry a whole chunk when numbered coverage is incomplete.
_CHUNK_RETRY_LIMIT = 1


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
    def translate_vtt(self, input_file: str | Path, output_file: str | Path) -> bool:
        """Translate `input_file` and write results to `output_file`.

        Returns:
            True on success, False if parsing/writing fails catastrophically.
            Per-caption translation failures do NOT fail the whole file;
            they are filled with the original text (see config.fallback_to_source).
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

        translations: Dict[int, str] = {}
        failed_count = 0

        for i, chunk in enumerate(chunks, start=1):
            self.logger.info(
                "Translating chunk %d/%d (%d captions, +%d/+%d context)",
                i, len(chunks), len(chunk.target),
                len(chunk.prev_context), len(chunk.next_context),
            )
            chunk_results, chunk_failures = self._translate_chunk(chunk)
            translations.update(chunk_results)
            failed_count += chunk_failures

        # Any caption missing from `translations` gets the source text as a
        # last-resort fallback (write_vtt already does this, but log it).
        missing = [c.index for c in captions if c.index not in translations]
        if missing:
            self.logger.warning(
                "%d caption(s) still missing after translation; using source text",
                len(missing),
            )

        try:
            write_vtt(output_file, captions, translations)
        except Exception as e:
            self.logger.error("Failed to write %s: %s", output_file, e)
            return False

        self.logger.info(
            "Done: wrote %s (%d translated, %d fallback-to-source)",
            output_file,
            len(captions) - failed_count - len(missing),
            failed_count + len(missing),
        )
        return True

    # ----------------------------------------------------------- Internals
    def _translate_chunk(self, chunk: Chunk) -> tuple[Dict[int, str], int]:
        """Translate one chunk. Returns (results-by-source-index, failure_count)."""
        target = chunk.target
        expected = len(target)
        if expected == 0:
            return {}, 0

        # Map in-chunk 1-based numbers -> source Caption.index.
        idx_map = {i + 1: cap.index for i, cap in enumerate(target)}

        parsed = self._call_with_chunk_retry(chunk)

        # Map parsed numbers back to source indices, skipping anything not
        # in the requested range (e.g. hallucinated extra numbers).
        results: Dict[int, str] = {}
        for local_idx, text in parsed.items():
            if local_idx in idx_map:
                results[idx_map[local_idx]] = text

        # Find gaps and fall back one-by-one.
        missing_local = [i for i in range(1, expected + 1) if i not in parsed]
        failure_count = 0
        for local_idx in missing_local:
            cap = target[local_idx - 1]
            self.logger.info(
                "Single-caption fallback for source index %d: %r",
                cap.index, cap.text[:80],
            )
            text = self._translate_single_caption(cap)
            if text is None:
                failure_count += 1
                text = self._source_fallback(cap)
                self.logger.warning(
                    "Falling back to source text for caption %d", cap.index
                )
            results[cap.index] = text

        return results, failure_count

    def _call_with_chunk_retry(self, chunk: Chunk) -> Dict[int, str]:
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
                response = self.provider.complete(prompt, max_tokens=self.config.max_tokens)
            except TranslationError as e:
                self.logger.error("Chunk LLM call failed (attempt %d): %s", attempt + 1, e)
                return best_parsed

            parsed = parse_numbered_response(response)
            complete, missing, unexpected = validate_coverage(parsed, expected)
            # Keep the best (most complete) response across attempts.
            if len(parsed) > len(best_parsed):
                best_parsed = parsed

            if complete:
                return parsed

            self.logger.warning(
                "Incomplete numbered response (attempt %d): got %d/%d, missing=%s, unexpected=%s",
                attempt + 1, len(parsed), expected, missing[:5], unexpected[:5],
            )
            attempt += 1

        return best_parsed

    def _translate_single_caption(self, cap: Caption) -> Optional[str]:
        """Translate a single caption in isolation. Returns None on failure."""
        prompt = build_single_prompt(
            cap.text,
            source_lang=self.config.source_language_name(),
            target_lang=self.config.target_language_name(),
        )
        try:
            text = self.provider.complete(prompt, max_tokens=self.config.max_tokens)
        except TranslationError as e:
            self.logger.error("Single-caption LLM call failed for index %d: %s", cap.index, e)
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
