"""Tests for vtt_translator.vtt_parser."""

import pytest

from vtt_translator.vtt_parser import Caption, parse_vtt, write_vtt


class TestParseVtt:
    def test_simple_file(self, simple_vtt):
        captions = parse_vtt(simple_vtt)
        assert len(captions) == 5
        assert captions[0].index == 0
        assert captions[0].start == "00:00:00.500"
        assert captions[0].end == "00:00:03.000"
        assert captions[0].text == "Hello and welcome to this course."

    def test_multiline_captions(self, multiline_vtt):
        captions = parse_vtt(multiline_vtt)
        assert len(captions) == 3
        # Multiline text should be normalized (newlines -> space)
        assert "spans multiple lines" in captions[0].text
        assert "\n" not in captions[0].text
        # raw_text preserves original newlines
        assert "\n" in captions[0].raw_text

    def test_empty_file(self, empty_vtt):
        captions = parse_vtt(empty_vtt)
        assert captions == []

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(Exception):
            parse_vtt(tmp_path / "no_such_file.vtt")

    def test_indices_are_sequential(self, simple_vtt):
        captions = parse_vtt(simple_vtt)
        indices = [c.index for c in captions]
        assert indices == list(range(len(captions)))


class TestWriteVtt:
    def test_roundtrip_preserves_timestamps(self, simple_vtt, tmp_path):
        captions = parse_vtt(simple_vtt)
        translations = {c.index: f"Translated {c.index}" for c in captions}
        output = tmp_path / "output.vtt"
        write_vtt(output, captions, translations)

        result = parse_vtt(output)
        assert len(result) == len(captions)
        for orig, written in zip(captions, result):
            assert written.start == orig.start
            assert written.end == orig.end

    def test_translations_used_in_output(self, simple_vtt, tmp_path):
        captions = parse_vtt(simple_vtt)
        translations = {0: "你好", 1: "世界", 2: "缓存", 3: "基础", 4: "内存"}
        output = tmp_path / "output.vtt"
        write_vtt(output, captions, translations)

        result = parse_vtt(output)
        assert result[0].text == "你好"
        assert result[1].text == "世界"

    def test_missing_translation_uses_empty(self, simple_vtt, tmp_path):
        captions = parse_vtt(simple_vtt)
        # Only translate first caption
        translations = {0: "你好"}
        output = tmp_path / "output.vtt"
        write_vtt(output, captions, translations)
        assert output.exists()
