"""Tests for vtt_translator.progress."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from vtt_translator.progress import ProgressStore


@pytest.fixture
def progress_env(tmp_path, simple_vtt):
    """Set up a progress store with a real input file."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    fingerprint = {"provider": "bedrock", "model_id": "test", "source_language": "en", "target_language": "zh"}
    store = ProgressStore(
        log_dir=log_dir,
        input_file=simple_vtt,
        config_fingerprint=fingerprint,
        enabled=True,
    )
    return store, fingerprint


class TestProgressStoreBasic:
    def test_fresh_load_returns_empty(self, progress_env):
        store, _ = progress_env
        assert store.load() == {}

    def test_update_then_load(self, progress_env):
        store, _ = progress_env
        store.load()  # Initialize
        store.update({0: "你好", 1: "世界"})

        # Create a new store to verify persistence
        store2 = ProgressStore(
            log_dir=store.progress_file.parent.parent,
            input_file=store.input_file,
            config_fingerprint=store._fingerprint,
            enabled=True,
        )
        loaded = store2.load()
        assert loaded == {0: "你好", 1: "世界"}

    def test_clear_deletes_file(self, progress_env):
        store, _ = progress_env
        store.load()
        store.update({0: "test"})
        assert store.progress_file.exists()
        store.clear()
        assert not store.progress_file.exists()

    def test_clear_on_nonexistent_no_error(self, progress_env):
        store, _ = progress_env
        store.clear()  # Should not raise


class TestProgressStoreInvalidation:
    def test_fingerprint_change_invalidates(self, tmp_path, simple_vtt):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        fp1 = {"provider": "bedrock", "model_id": "m1", "source_language": "en", "target_language": "zh"}
        fp2 = {"provider": "bedrock", "model_id": "m2", "source_language": "en", "target_language": "zh"}

        store1 = ProgressStore(log_dir=log_dir, input_file=simple_vtt, config_fingerprint=fp1, enabled=True)
        store1.load()
        store1.update({0: "cached"})

        store2 = ProgressStore(log_dir=log_dir, input_file=simple_vtt, config_fingerprint=fp2, enabled=True)
        assert store2.load() == {}

    def test_input_content_change_invalidates(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        input_file = tmp_path / "test.vtt"
        input_file.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n")
        fp = {"provider": "bedrock", "model_id": "m", "source_language": "en", "target_language": "zh"}

        store = ProgressStore(log_dir=log_dir, input_file=input_file, config_fingerprint=fp, enabled=True)
        store.load()
        store.update({0: "cached"})

        # Modify input file content
        time.sleep(0.1)
        input_file.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nChanged\n")

        store2 = ProgressStore(log_dir=log_dir, input_file=input_file, config_fingerprint=fp, enabled=True)
        assert store2.load() == {}


class TestProgressStoreDisabled:
    def test_disabled_load_returns_empty(self, tmp_path, simple_vtt):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        fp = {"provider": "bedrock", "model_id": "m", "source_language": "en", "target_language": "zh"}
        store = ProgressStore(log_dir=log_dir, input_file=simple_vtt, config_fingerprint=fp, enabled=False)
        assert store.load() == {}

    def test_disabled_update_is_noop(self, tmp_path, simple_vtt):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        fp = {"provider": "bedrock", "model_id": "m", "source_language": "en", "target_language": "zh"}
        store = ProgressStore(log_dir=log_dir, input_file=simple_vtt, config_fingerprint=fp, enabled=False)
        store.update({0: "test"})
        assert not store.progress_file.exists()

    def test_clear_works_even_when_disabled(self, tmp_path, simple_vtt):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        fp = {"provider": "bedrock", "model_id": "m", "source_language": "en", "target_language": "zh"}
        # Create a progress file with enabled=True
        store = ProgressStore(log_dir=log_dir, input_file=simple_vtt, config_fingerprint=fp, enabled=True)
        store.load()
        store.update({0: "test"})
        assert store.progress_file.exists()
        # Clear with disabled=True should still delete
        store2 = ProgressStore(log_dir=log_dir, input_file=simple_vtt, config_fingerprint=fp, enabled=False)
        store2.clear()
        assert not store.progress_file.exists()


class TestProgressStoreConcurrency:
    def test_concurrent_updates_no_corruption(self, progress_env):
        store, _ = progress_env
        store.load()

        def do_update(i: int):
            store.update({i: f"translation_{i}"})

        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = [ex.submit(do_update, i) for i in range(20)]
            for f in futures:
                f.result()

        # Reload and verify all 20 translations present
        store2 = ProgressStore(
            log_dir=store.progress_file.parent.parent,
            input_file=store.input_file,
            config_fingerprint=store._fingerprint,
            enabled=True,
        )
        loaded = store2.load()
        assert len(loaded) == 20
