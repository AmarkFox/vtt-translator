"""Tests for vtt_translator.cli."""

from pathlib import Path
from unittest.mock import patch

import pytest

from tests.conftest import FakeProvider
from vtt_translator.cli import main


class TestCliConfig:
    def test_config_generates_file(self, tmp_path):
        output = str(tmp_path / "generated.json")
        exit_code = main(["config", output])
        assert exit_code == 0
        assert Path(output).exists()


class TestCliEstimate:
    def test_estimate_prints_stats(self, simple_vtt, capsys):
        exit_code = main(["estimate", str(simple_vtt)])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Captions:" in captured.out
        assert "Chunks:" in captured.out
        assert "5" in captured.out  # 5 captions


class TestCliTranslate:
    def test_translate_with_fake_provider(self, simple_vtt, tmp_path):
        output = str(tmp_path / "output.vtt")
        provider = FakeProvider()
        with patch("vtt_translator.cli.VttTranslator") as MockTranslator:
            instance = MockTranslator.return_value
            instance.translate_vtt.return_value = True
            exit_code = main(["translate", str(simple_vtt), output, "--no-resume"])
        assert exit_code == 0

    def test_translate_failure_returns_1(self, simple_vtt, tmp_path):
        output = str(tmp_path / "output.vtt")
        with patch("vtt_translator.cli.VttTranslator") as MockTranslator:
            instance = MockTranslator.return_value
            instance.translate_vtt.return_value = False
            exit_code = main(["translate", str(simple_vtt), output])
        assert exit_code == 1


class TestCliHelp:
    def test_help_exits_zero(self):
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0

    def test_unknown_command_exits_error(self):
        with pytest.raises(SystemExit) as exc_info:
            main(["nonexistent"])
        assert exc_info.value.code != 0
