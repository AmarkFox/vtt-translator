"""Tests for vtt_translator.utils."""

from pathlib import Path

from vtt_translator.utils import ensure_dir, move_file, setup_logger


class TestEnsureDir:
    def test_creates_directory(self, tmp_path):
        target = tmp_path / "new" / "nested" / "dir"
        result = ensure_dir(target)
        assert target.exists()
        assert target.is_dir()
        assert result == target

    def test_existing_directory_no_error(self, tmp_path):
        target = tmp_path / "existing"
        target.mkdir()
        result = ensure_dir(target)
        assert result == target


class TestMoveFile:
    def test_moves_file(self, tmp_path):
        source = tmp_path / "source.txt"
        source.write_text("content")
        target_dir = tmp_path / "dest"
        target_dir.mkdir()

        result = move_file(source, target_dir)
        assert not source.exists()
        assert result.exists()
        assert result.parent == target_dir
        assert result.read_text() == "content"

    def test_creates_target_dir_if_missing(self, tmp_path):
        source = tmp_path / "source.txt"
        source.write_text("content")
        target_dir = tmp_path / "new_dir"

        result = move_file(source, target_dir)
        assert result.exists()
        assert target_dir.exists()


class TestSetupLogger:
    def test_creates_log_file(self, tmp_path):
        logger = setup_logger(tmp_path, "test.log", logger_name="test_unique", console=False)
        logger.info("test message")
        log_file = tmp_path / "test.log"
        assert log_file.exists()
        assert "test message" in log_file.read_text()
