"""Tests for vtt_translator.config."""

import json

import pytest
from pydantic import ValidationError

from vtt_translator.config import Config


class TestConfigDefaults:
    def test_default_values(self):
        cfg = Config()
        assert cfg.provider == "bedrock"
        assert cfg.source_language == "en"
        assert cfg.target_language == "zh"
        assert cfg.chunk_size == 50
        assert cfg.context_window == 5
        assert cfg.max_concurrent_chunks == 3
        assert cfg.enable_resume is True
        assert cfg.fallback_to_source is True

    def test_language_normalization(self):
        cfg = Config(source_language="EN", target_language="ZH")
        assert cfg.source_language == "en"
        assert cfg.target_language == "zh"


class TestConfigValidation:
    def test_max_sleep_less_than_min_raises(self):
        with pytest.raises(ValidationError):
            Config(min_sleep_time=300, max_sleep_time=100)

    def test_chunk_size_zero_raises(self):
        with pytest.raises(ValidationError):
            Config(chunk_size=0)

    def test_negative_context_window_raises(self):
        with pytest.raises(ValidationError):
            Config(context_window=-1)


class TestConfigIO:
    def test_save_and_load_roundtrip(self, tmp_path):
        cfg = Config(target_language="ja", chunk_size=30)
        path = tmp_path / "cfg.json"
        cfg.save(path)
        loaded = Config.load(path)
        assert loaded.target_language == "ja"
        assert loaded.chunk_size == 30

    def test_load_nonexistent_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            Config.load(tmp_path / "nonexistent.json")

    def test_load_none_returns_defaults(self):
        cfg = Config.load(None)
        assert cfg.provider == "bedrock"

    def test_save_creates_parent_dirs(self, tmp_path):
        cfg = Config()
        path = tmp_path / "deep" / "nested" / "cfg.json"
        cfg.save(path)
        assert path.exists()


class TestConfigMethods:
    def test_language_name_known(self):
        cfg = Config(target_language="ja")
        assert "Japanese" in cfg.target_language_name()

    def test_language_name_unknown_returns_code(self):
        cfg = Config(target_language="xx")
        assert cfg.target_language_name() == "xx"

    def test_resume_fingerprint_keys(self):
        cfg = Config()
        fp = cfg.resume_fingerprint()
        assert "provider" in fp
        assert "model_id" in fp
        assert "source_language" in fp
        assert "target_language" in fp
        assert "chunk_size" not in fp
