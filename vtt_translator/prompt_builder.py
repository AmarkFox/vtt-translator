"""Build prompts for numbered batch translation."""

from __future__ import annotations

from typing import List

from .chunker import Chunk
from .vtt_parser import Caption


SYSTEM_INSTRUCTIONS_TEMPLATE = """\
You are a professional video subtitle translator.
Translate the numbered subtitles from {source_lang} to {target_lang}.

Rules:
1. Output EXACTLY one line per input number, in the same order, using the format: [N] translated text
2. Do NOT translate, repeat, or comment on the context sections; they are provided only to help you understand the subtitles.
3. Keep the translation natural and idiomatic in {target_lang}; do not add explanations or notes.
4. If a subtitle is a continuation of the previous one (e.g. cut mid-sentence), translate it so that the combined result reads naturally in {target_lang}.
5. Preserve proper nouns, code identifiers, numbers, and URLs unchanged.
6. Do NOT output any other content besides the numbered lines.
"""


def _format_context_block(label: str, captions: List[Caption]) -> str:
    if not captions:
        return ""
    lines = [f"<{label}>"]
    for cap in captions:
        lines.append(f"- {cap.text}")
    lines.append(f"</{label}>")
    return "\n".join(lines)


def build_batch_prompt(chunk: Chunk, source_lang: str, target_lang: str) -> str:
    """Build a numbered-batch translation prompt for a single chunk.

    Target subtitles are numbered 1..N within the chunk. The caller must map
    those numbers back to the original Caption.index.
    """
    system = SYSTEM_INSTRUCTIONS_TEMPLATE.format(
        source_lang=source_lang,
        target_lang=target_lang,
    )

    parts: List[str] = [system]

    prev_block = _format_context_block("preceding_context", chunk.prev_context)
    if prev_block:
        parts.append(prev_block)

    # Numbered target lines (1-based within the chunk).
    parts.append("Translate the following subtitles:")
    for i, cap in enumerate(chunk.target, start=1):
        parts.append(f"[{i}] {cap.text}")

    next_block = _format_context_block("following_context", chunk.next_context)
    if next_block:
        parts.append(next_block)

    parts.append("Now produce the translated lines:")
    return "\n\n".join(parts)


def build_single_prompt(text: str, source_lang: str, target_lang: str) -> str:
    """Build a prompt for translating a single caption (single-item fallback)."""
    return (
        f"Translate the following {source_lang} subtitle to {target_lang}. "
        f"Output only the translated text, nothing else.\n\n"
        f"{text}"
    )
