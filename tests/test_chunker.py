"""Tests for vtt_translator.chunker."""

import pytest

from vtt_translator.chunker import split_into_chunks
from vtt_translator.vtt_parser import Caption


def _make_captions(n: int) -> list[Caption]:
    """Create n dummy captions."""
    return [
        Caption(
            index=i,
            start=f"00:00:{i:02d}.000",
            end=f"00:00:{i:02d}.500",
            text=f"Caption {i}",
            raw_text=f"Caption {i}",
        )
        for i in range(n)
    ]


class TestSplitIntoChunks:
    def test_even_split(self):
        captions = _make_captions(10)
        chunks = split_into_chunks(captions, chunk_size=5, context_window=0)
        assert len(chunks) == 2
        assert len(chunks[0].target) == 5
        assert len(chunks[1].target) == 5

    def test_uneven_split(self):
        captions = _make_captions(10)
        chunks = split_into_chunks(captions, chunk_size=3, context_window=0)
        assert len(chunks) == 4
        sizes = [len(c.target) for c in chunks]
        assert sizes == [3, 3, 3, 1]

    def test_context_window(self):
        captions = _make_captions(10)
        chunks = split_into_chunks(captions, chunk_size=3, context_window=2)
        # First chunk: no prev_context
        assert len(chunks[0].prev_context) == 0
        assert len(chunks[0].next_context) == 2
        # Middle chunk: both contexts
        assert len(chunks[1].prev_context) == 2
        assert len(chunks[1].next_context) == 2
        # Last chunk: no next_context
        assert len(chunks[-1].next_context) == 0
        assert len(chunks[-1].prev_context) == 2

    def test_first_chunk_no_prev_context(self):
        captions = _make_captions(6)
        chunks = split_into_chunks(captions, chunk_size=3, context_window=2)
        assert chunks[0].prev_context == []

    def test_last_chunk_no_next_context(self):
        captions = _make_captions(6)
        chunks = split_into_chunks(captions, chunk_size=3, context_window=2)
        assert chunks[-1].next_context == []

    def test_single_caption(self):
        captions = _make_captions(1)
        chunks = split_into_chunks(captions, chunk_size=5, context_window=2)
        assert len(chunks) == 1
        assert len(chunks[0].target) == 1
        assert chunks[0].prev_context == []
        assert chunks[0].next_context == []

    def test_chunk_size_larger_than_captions(self):
        captions = _make_captions(3)
        chunks = split_into_chunks(captions, chunk_size=10, context_window=2)
        assert len(chunks) == 1
        assert len(chunks[0].target) == 3

    def test_invalid_chunk_size(self):
        captions = _make_captions(5)
        with pytest.raises(ValueError):
            split_into_chunks(captions, chunk_size=0)

    def test_negative_context_window(self):
        captions = _make_captions(5)
        with pytest.raises(ValueError):
            split_into_chunks(captions, chunk_size=3, context_window=-1)

    def test_target_indices_preserved(self):
        captions = _make_captions(6)
        chunks = split_into_chunks(captions, chunk_size=3, context_window=0)
        # First chunk targets indices 0,1,2
        assert [c.index for c in chunks[0].target] == [0, 1, 2]
        # Second chunk targets indices 3,4,5
        assert [c.index for c in chunks[1].target] == [3, 4, 5]
