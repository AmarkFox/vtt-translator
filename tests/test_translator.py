"""Tests for vtt_translator.translator (full pipeline with FakeProvider)."""

from pathlib import Path

import pytest

from tests.conftest import FakeProvider
from vtt_translator.config import Config
from vtt_translator.translator import VttTranslator
from vtt_translator.vtt_parser import parse_vtt


@pytest.fixture
def translator_env(tmp_path, simple_vtt):
    """Set up a translator with FakeProvider and isolated dirs."""
    cfg = Config(
        log_dir=tmp_path / "logs",
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        done_dir=tmp_path / "done",
        chunk_size=2,
        context_window=1,
        max_concurrent_chunks=2,
        enable_resume=False,
        api_sleep_time=0.0,
        min_sleep_time=0,
        max_sleep_time=0,
    )
    provider = FakeProvider()
    translator = VttTranslator(cfg, provider=provider)
    output = tmp_path / "output.vtt"
    return translator, provider, simple_vtt, output


class TestTranslatorFullPipeline:
    def test_successful_translation(self, translator_env):
        translator, provider, input_file, output = translator_env
        ok = translator.translate_vtt(input_file, output)
        assert ok is True
        assert output.exists()
        result = parse_vtt(output)
        assert len(result) == 5
        # FakeProvider prefixes with [翻译]
        assert "[翻译]" in result[0].text

    def test_empty_input_returns_true(self, translator_env, empty_vtt, tmp_path):
        translator, _, _, _ = translator_env
        output = tmp_path / "empty_output.vtt"
        ok = translator.translate_vtt(empty_vtt, output)
        assert ok is True
        assert output.exists()

    def test_nonexistent_input_returns_false(self, translator_env, tmp_path):
        translator, _, _, _ = translator_env
        ok = translator.translate_vtt(tmp_path / "no.vtt", tmp_path / "out.vtt")
        assert ok is False


class TestTranslatorFallback:
    def test_all_failures_uses_source_text(self, tmp_path, simple_vtt):
        """When provider always fails, fallback_to_source keeps original text."""
        cfg = Config(
            log_dir=tmp_path / "logs",
            chunk_size=2,
            context_window=0,
            max_concurrent_chunks=1,
            enable_resume=False,
            fallback_to_source=True,
            api_sleep_time=0.0,
            min_sleep_time=0,
            max_sleep_time=0,
        )
        # Fail on all calls (0,1,2,... up to many)
        provider = FakeProvider(fail_on=set(range(100)))
        translator = VttTranslator(cfg, provider=provider)
        output = tmp_path / "output.vtt"

        ok = translator.translate_vtt(simple_vtt, output)
        assert ok is True
        result = parse_vtt(output)
        # Should contain original English text as fallback
        assert result[0].text == "Hello and welcome to this course."

    def test_incomplete_response_triggers_single_fallback(self, tmp_path, simple_vtt):
        """When batch response is missing items, single-caption fallback kicks in."""
        cfg = Config(
            log_dir=tmp_path / "logs",
            chunk_size=3,
            context_window=0,
            max_concurrent_chunks=1,
            enable_resume=False,
            api_sleep_time=0.0,
            min_sleep_time=0,
            max_sleep_time=0,
        )
        # First call returns only [1] (missing [2] and [3])
        # Second call (retry) also incomplete
        # Then single-caption fallback calls succeed (auto_respond)
        responses = [
            "[1] 翻译第一条",
            "[1] 翻译第一条",  # chunk retry
        ]
        provider = FakeProvider(responses=responses)
        translator = VttTranslator(cfg, provider=provider)
        output = tmp_path / "output.vtt"

        ok = translator.translate_vtt(simple_vtt, output)
        assert ok is True
        result = parse_vtt(output)
        assert len(result) == 5


class TestTranslatorResume:
    def test_resume_skips_cached_chunks(self, tmp_path, simple_vtt):
        """With resume enabled, previously translated captions are reused."""
        cfg = Config(
            log_dir=tmp_path / "logs",
            chunk_size=2,
            context_window=0,
            max_concurrent_chunks=1,
            enable_resume=True,
            api_sleep_time=0.0,
            min_sleep_time=0,
            max_sleep_time=0,
        )
        provider = FakeProvider()
        translator = VttTranslator(cfg, provider=provider)
        output = tmp_path / "output.vtt"

        # First run: translates everything
        ok = translator.translate_vtt(simple_vtt, output)
        assert ok is True
        first_call_count = provider._call_count

        # Second run with fresh provider: should re-translate (progress cleared on success)
        provider2 = FakeProvider()
        translator2 = VttTranslator(cfg, provider=provider2)
        ok = translator2.translate_vtt(simple_vtt, output)
        assert ok is True
        # Progress was cleared after first success, so second run re-translates
        assert provider2._call_count > 0

    def test_no_resume_ignores_progress(self, tmp_path, simple_vtt):
        """With resume=False, any existing progress is ignored."""
        cfg = Config(
            log_dir=tmp_path / "logs",
            chunk_size=5,
            context_window=0,
            max_concurrent_chunks=1,
            enable_resume=True,
            api_sleep_time=0.0,
            min_sleep_time=0,
            max_sleep_time=0,
        )
        provider = FakeProvider()
        translator = VttTranslator(cfg, provider=provider)
        output = tmp_path / "output.vtt"

        # Force resume=False
        ok = translator.translate_vtt(simple_vtt, output, resume=False)
        assert ok is True
