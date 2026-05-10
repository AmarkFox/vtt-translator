"""Shared fixtures for the vtt-translator test suite."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pytest

from vtt_translator.config import Config
from vtt_translator.llm.base import LLMProvider, TranslationError


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FakeProvider(LLMProvider):
    """Deterministic LLM provider for testing.

    By default, echoes numbered translations with a [翻译] prefix.
    Can be configured with explicit responses or programmed failures.
    """

    def __init__(
        self,
        responses: list[str] | None = None,
        fail_on: set[int] | None = None,
    ) -> None:
        self._responses = list(responses) if responses else []
        self._call_count = 0
        self._fail_on = fail_on or set()
        self.calls: list[str] = []

    @property
    def model_id(self) -> str:
        return "fake/test-model"

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        tag: Optional[str] = None,
    ) -> str:
        idx = self._call_count
        self._call_count += 1
        self.calls.append(prompt)

        if idx in self._fail_on:
            raise TranslationError(f"Fake failure at call {idx}")

        if self._responses:
            return self._responses.pop(0)

        return self._auto_respond(prompt)

    def _auto_respond(self, prompt: str) -> str:
        """Parse [N] lines from prompt and return translated versions."""
        lines = []
        for match in re.finditer(r"^\[(\d+)\]\s*(.+)$", prompt, re.MULTILINE):
            num, text = match.group(1), match.group(2)
            lines.append(f"[{num}] [翻译]{text}")
        return "\n".join(lines) if lines else "[1] translated text"


@pytest.fixture
def fake_provider():
    """Create a default FakeProvider instance."""
    return FakeProvider()


@pytest.fixture
def simple_vtt():
    """Path to simple.vtt fixture (5 captions)."""
    return FIXTURES_DIR / "simple.vtt"


@pytest.fixture
def multiline_vtt():
    """Path to multiline.vtt fixture (3 captions with newlines)."""
    return FIXTURES_DIR / "multiline.vtt"


@pytest.fixture
def empty_vtt():
    """Path to empty.vtt fixture (valid header, no captions)."""
    return FIXTURES_DIR / "empty.vtt"


@pytest.fixture
def test_config(tmp_path):
    """Config with all dirs pointing to tmp_path for isolation."""
    return Config(
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        done_dir=tmp_path / "done",
        log_dir=tmp_path / "logs",
        provider="bedrock",
        model_id="fake/test-model",
        source_language="en",
        target_language="zh",
        chunk_size=3,
        context_window=1,
        max_concurrent_chunks=1,
        enable_resume=False,
        api_sleep_time=0.0,
        min_sleep_time=0,
        max_sleep_time=0,
    )
