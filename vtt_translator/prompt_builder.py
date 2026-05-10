"""Build prompts for numbered batch translation."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

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
6. Do NOT output any other content besides the numbered lines."""


GLOSSARY_TEMPLATE = """
<glossary>
You MUST use the following translations for these terms:
{entries}
</glossary>"""


def _format_context_block(label: str, captions: List[Caption]) -> str:
    if not captions:
        return ""
    lines = [f"<{label}>"]
    for cap in captions:
        lines.append(f"- {cap.text}")
    lines.append(f"</{label}>")
    return "\n".join(lines)


def _format_glossary(glossary: Optional[Dict[str, str]]) -> str:
    """Format glossary dict into a prompt section."""
    if not glossary:
        return ""
    entries = "\n".join(f"- {src} → {tgt}" for src, tgt in glossary.items())
    return GLOSSARY_TEMPLATE.format(entries=entries)


def build_batch_prompt(
    chunk: Chunk,
    source_lang: str,
    target_lang: str,
    glossary: Optional[Dict[str, str]] = None,
) -> Tuple[str, str]:
    """Build a numbered-batch translation prompt for a single chunk.

    Returns:
        A tuple of (system_prompt, user_prompt). The system prompt contains
        the translator role and rules; the user prompt contains the actual
        subtitles to translate with context.
    """
    system = SYSTEM_INSTRUCTIONS_TEMPLATE.format(
        source_lang=source_lang,
        target_lang=target_lang,
    )
    glossary_section = _format_glossary(glossary)
    if glossary_section:
        system += glossary_section

    # User prompt: context + numbered lines
    parts: List[str] = []

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
    user_prompt = "\n\n".join(parts)

    return system, user_prompt


def build_single_prompt(
    text: str,
    source_lang: str,
    target_lang: str,
    glossary: Optional[Dict[str, str]] = None,
) -> Tuple[str, str]:
    """Build a prompt for translating a single caption (fallback).

    Returns:
        A tuple of (system_prompt, user_prompt).
    """
    system = (
        f"You are a professional subtitle translator. "
        f"Translate from {source_lang} to {target_lang}. "
        f"Output only the translated text, nothing else."
    )
    glossary_section = _format_glossary(glossary)
    if glossary_section:
        system += glossary_section

    return system, text
