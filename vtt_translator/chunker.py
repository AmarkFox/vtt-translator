"""Split a caption list into translation chunks with optional context windows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .vtt_parser import Caption


@dataclass
class Chunk:
    """A unit of work for the LLM.

    Attributes:
        target: Captions to be translated.
        prev_context: Captions immediately preceding `target`, provided to
            the LLM for context only (not translated).
        next_context: Captions immediately following `target`, also
            context-only.
    """

    target: List[Caption]
    prev_context: List[Caption] = field(default_factory=list)
    next_context: List[Caption] = field(default_factory=list)


def split_into_chunks(
    captions: List[Caption],
    chunk_size: int,
    context_window: int = 0,
) -> List[Chunk]:
    """Split captions into fixed-size chunks with optional surrounding context.

    Args:
        captions: Full list of captions, in source order.
        chunk_size: Number of captions per chunk (must be >= 1).
        context_window: Number of captions to include as context before
            and after each chunk's target list (may be 0).
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    if context_window < 0:
        raise ValueError("context_window must be >= 0")

    chunks: List[Chunk] = []
    n = len(captions)
    for start in range(0, n, chunk_size):
        end = min(start + chunk_size, n)
        prev_start = max(0, start - context_window)
        next_end = min(n, end + context_window)

        chunks.append(
            Chunk(
                target=captions[start:end],
                prev_context=captions[prev_start:start],
                next_context=captions[end:next_end],
            )
        )
    return chunks
