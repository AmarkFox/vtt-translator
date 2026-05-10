"""Tests for vtt_translator.manager."""

import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.conftest import FakeProvider
from vtt_translator.config import Config
from vtt_translator.manager import VttTranslatorManager, _coerce_config


@pytest.fixture
def manager_env(tmp_path, simple_vtt):
    """Set up a manager environment with VTT files in input_dir."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    done_dir = tmp_path / "done"
    log_dir = tmp_path / "logs"
    for d in (input_dir, output_dir, done_dir, log_dir):
        d.mkdir()

    # Copy fixtures into input_dir
    shutil.copy(simple_vtt, input_dir / "file1.vtt")
    shutil.copy(simple_vtt, input_dir / "file2.vtt")

    cfg = Config(
        input_dir=input_dir,
        output_dir=output_dir,
        done_dir=done_dir,
        log_dir=log_dir,
        target_language="zh",
        chunk_size=5,
        context_window=0,
        max_concurrent_chunks=1,
        enable_resume=False,
        api_sleep_time=0.0,
        min_sleep_time=0,
        max_sleep_time=0,
    )
    return cfg, input_dir, output_dir, done_dir


class TestFindVttFiles:
    def test_discovers_vtt_files(self, manager_env):
        cfg, input_dir, _, _ = manager_env
        with patch("vtt_translator.manager.create_provider", return_value=FakeProvider()):
            mgr = VttTranslatorManager(cfg)
        files = mgr.find_vtt_files()
        assert len(files) == 2
        names = [f.name for f in files]
        assert "file1.vtt" in names
        assert "file2.vtt" in names

    def test_skips_target_language_suffix(self, manager_env):
        cfg, input_dir, _, _ = manager_env
        # Create a file with -zh.vtt suffix
        (input_dir / "already-zh.vtt").write_text("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n已翻译\n")
        with patch("vtt_translator.manager.create_provider", return_value=FakeProvider()):
            mgr = VttTranslatorManager(cfg)
        files = mgr.find_vtt_files()
        names = [f.name for f in files]
        assert "already-zh.vtt" not in names

    def test_skips_files_in_done_dir(self, manager_env):
        cfg, input_dir, _, done_dir = manager_env
        # Move file1.vtt to done
        shutil.copy(input_dir / "file1.vtt", done_dir / "file1.vtt")
        with patch("vtt_translator.manager.create_provider", return_value=FakeProvider()):
            mgr = VttTranslatorManager(cfg)
        files = mgr.find_vtt_files()
        names = [f.name for f in files]
        assert "file1.vtt" not in names
        assert "file2.vtt" in names

    def test_skips_files_with_existing_translation(self, manager_env):
        cfg, input_dir, output_dir, _ = manager_env
        # Create translated output for file1
        (output_dir / "file1-zh.vtt").write_text("WEBVTT\n")
        with patch("vtt_translator.manager.create_provider", return_value=FakeProvider()):
            mgr = VttTranslatorManager(cfg)
        files = mgr.find_vtt_files()
        names = [f.name for f in files]
        assert "file1.vtt" not in names
        assert "file2.vtt" in names


class TestProcessFile:
    def test_translates_and_moves_to_done(self, manager_env):
        cfg, input_dir, output_dir, done_dir = manager_env
        provider = FakeProvider()
        with patch("vtt_translator.manager.create_provider", return_value=provider):
            mgr = VttTranslatorManager(cfg)
        mgr.provider = provider

        ok = mgr.process_file(input_dir / "file1.vtt")
        assert ok is True
        assert (output_dir / "file1-zh.vtt").exists()
        assert (done_dir / "file1.vtt").exists()
        assert not (input_dir / "file1.vtt").exists()


class TestBatchProcess:
    def test_processes_all_files(self, manager_env):
        cfg, input_dir, output_dir, done_dir = manager_env
        provider = FakeProvider()
        with patch("vtt_translator.manager.create_provider", return_value=provider):
            mgr = VttTranslatorManager(cfg)
        mgr.provider = provider

        success, total = mgr.batch_process()
        assert total == 2
        assert success == 2

    def test_start_end_slicing(self, manager_env):
        cfg, input_dir, output_dir, done_dir = manager_env
        provider = FakeProvider()
        with patch("vtt_translator.manager.create_provider", return_value=provider):
            mgr = VttTranslatorManager(cfg)
        mgr.provider = provider

        success, total = mgr.batch_process(start_index=0, end_index=1)
        assert total == 1
        assert success == 1


class TestCoerceConfig:
    def test_none_returns_defaults(self):
        cfg = _coerce_config(None)
        assert isinstance(cfg, Config)

    def test_config_instance_passthrough(self):
        original = Config(target_language="ja")
        cfg = _coerce_config(original)
        assert cfg is original

    def test_dict_creates_config(self):
        cfg = _coerce_config({"target_language": "ko"})
        assert cfg.target_language == "ko"

    def test_path_loads_file(self, tmp_path):
        path = tmp_path / "cfg.json"
        Config(target_language="fr").save(path)
        cfg = _coerce_config(path)
        assert cfg.target_language == "fr"

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError):
            _coerce_config(42)
