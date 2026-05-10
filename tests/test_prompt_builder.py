"""Tests for vtt_translator.prompt_builder."""

from vtt_translator.chunker import Chunk
from vtt_translator.prompt_builder import build_batch_prompt, build_single_prompt
from vtt_translator.vtt_parser import Caption


def _cap(index: int, text: str) -> Caption:
    return Caption(
        index=index,
        start=f"00:00:{index:02d}.000",
        end=f"00:00:{index:02d}.500",
        text=text,
        raw_text=text,
    )


class TestBuildBatchPrompt:
    def test_includes_all_target_captions_numbered(self):
        chunk = Chunk(
            target=[_cap(0, "Hello"), _cap(1, "World")],
            prev_context=[],
            next_context=[],
        )
        prompt = build_batch_prompt(chunk, source_lang="English", target_lang="Chinese")
        assert "[1] Hello" in prompt
        assert "[2] World" in prompt

    def test_includes_context_when_present(self):
        chunk = Chunk(
            target=[_cap(2, "Main text")],
            prev_context=[_cap(0, "Before one"), _cap(1, "Before two")],
            next_context=[_cap(3, "After one")],
        )
        prompt = build_batch_prompt(chunk, source_lang="English", target_lang="Chinese")
        assert "Before one" in prompt
        assert "Before two" in prompt
        assert "After one" in prompt
        assert "[1] Main text" in prompt

    def test_omits_context_when_empty(self):
        chunk = Chunk(
            target=[_cap(0, "Only text")],
            prev_context=[],
            next_context=[],
        )
        prompt = build_batch_prompt(chunk, source_lang="English", target_lang="Chinese")
        assert "[1] Only text" in prompt

    def test_includes_language_names(self):
        chunk = Chunk(target=[_cap(0, "Test")], prev_context=[], next_context=[])
        prompt = build_batch_prompt(chunk, source_lang="English", target_lang="Japanese")
        assert "English" in prompt
        assert "Japanese" in prompt


class TestBuildSinglePrompt:
    def test_contains_text_and_languages(self):
        prompt = build_single_prompt("Hello world", source_lang="English", target_lang="Chinese")
        assert "Hello world" in prompt
        assert "English" in prompt
        assert "Chinese" in prompt
