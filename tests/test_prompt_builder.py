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
    def test_returns_system_and_user_prompt(self):
        chunk = Chunk(target=[_cap(0, "Hello")], prev_context=[], next_context=[])
        system, user = build_batch_prompt(chunk, source_lang="English", target_lang="Chinese")
        assert isinstance(system, str)
        assert isinstance(user, str)
        assert "translator" in system.lower()
        assert "[1] Hello" in user

    def test_includes_all_target_captions_numbered(self):
        chunk = Chunk(
            target=[_cap(0, "Hello"), _cap(1, "World")],
            prev_context=[],
            next_context=[],
        )
        _, user = build_batch_prompt(chunk, source_lang="English", target_lang="Chinese")
        assert "[1] Hello" in user
        assert "[2] World" in user

    def test_includes_context_when_present(self):
        chunk = Chunk(
            target=[_cap(2, "Main text")],
            prev_context=[_cap(0, "Before one"), _cap(1, "Before two")],
            next_context=[_cap(3, "After one")],
        )
        _, user = build_batch_prompt(chunk, source_lang="English", target_lang="Chinese")
        assert "Before one" in user
        assert "Before two" in user
        assert "After one" in user
        assert "[1] Main text" in user

    def test_omits_context_when_empty(self):
        chunk = Chunk(target=[_cap(0, "Only text")], prev_context=[], next_context=[])
        _, user = build_batch_prompt(chunk, source_lang="English", target_lang="Chinese")
        assert "preceding_context" not in user
        assert "following_context" not in user

    def test_includes_language_names_in_system(self):
        chunk = Chunk(target=[_cap(0, "Test")], prev_context=[], next_context=[])
        system, _ = build_batch_prompt(chunk, source_lang="English", target_lang="Japanese")
        assert "English" in system
        assert "Japanese" in system

    def test_glossary_injected_into_system(self):
        chunk = Chunk(target=[_cap(0, "cache")], prev_context=[], next_context=[])
        glossary = {"cache": "缓存", "LRU": "LRU"}
        system, _ = build_batch_prompt(
            chunk, source_lang="English", target_lang="Chinese", glossary=glossary,
        )
        assert "cache → 缓存" in system
        assert "LRU → LRU" in system
        assert "<glossary>" in system

    def test_no_glossary_no_section(self):
        chunk = Chunk(target=[_cap(0, "test")], prev_context=[], next_context=[])
        system, _ = build_batch_prompt(chunk, source_lang="English", target_lang="Chinese")
        assert "<glossary>" not in system


class TestBuildSinglePrompt:
    def test_returns_system_and_user(self):
        system, user = build_single_prompt("Hello world", source_lang="English", target_lang="Chinese")
        assert "translator" in system.lower()
        assert user == "Hello world"

    def test_glossary_in_single_prompt(self):
        glossary = {"hello": "你好"}
        system, _ = build_single_prompt(
            "Hello", source_lang="English", target_lang="Chinese", glossary=glossary,
        )
        assert "hello → 你好" in system
