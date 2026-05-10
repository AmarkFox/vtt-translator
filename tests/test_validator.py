"""Tests for vtt_translator.validator."""

from vtt_translator.validator import parse_numbered_response, validate_coverage


class TestParseNumberedResponse:
    def test_standard_numbered_format(self):
        response = "[1] Hello world\n[2] Goodbye world"
        result = parse_numbered_response(response)
        assert result == {1: "Hello world", 2: "Goodbye world"}

    def test_multiline_text_between_numbers(self):
        response = "[1] First line\nsecond line\n[2] Another caption"
        result = parse_numbered_response(response)
        assert 1 in result
        assert "First line" in result[1]
        assert "second line" in result[1]
        assert result[2] == "Another caption"

    def test_empty_response(self):
        assert parse_numbered_response("") == {}

    def test_no_brackets(self):
        assert parse_numbered_response("just some plain text") == {}

    def test_numbered_with_extra_whitespace(self):
        response = "  [1]   Translated text  \n  [2]   More text  "
        result = parse_numbered_response(response)
        assert 1 in result
        assert 2 in result

    def test_non_sequential_numbers(self):
        response = "[1] First\n[3] Third\n[5] Fifth"
        result = parse_numbered_response(response)
        assert set(result.keys()) == {1, 3, 5}

    def test_chinese_translation(self):
        response = "[1] 你好世界\n[2] 再见世界"
        result = parse_numbered_response(response)
        assert result[1] == "你好世界"
        assert result[2] == "再见世界"


class TestValidateCoverage:
    def test_complete_coverage(self):
        parsed = {1: "a", 2: "b", 3: "c"}
        complete, missing, unexpected = validate_coverage(parsed, 3)
        assert complete is True
        assert missing == []
        assert unexpected == []

    def test_missing_items(self):
        parsed = {1: "a", 3: "c"}
        complete, missing, unexpected = validate_coverage(parsed, 3)
        assert complete is False
        assert 2 in missing

    def test_unexpected_items(self):
        parsed = {1: "a", 2: "b", 3: "c", 99: "extra"}
        complete, missing, unexpected = validate_coverage(parsed, 3)
        # complete is False when unexpected items exist
        assert complete is False
        assert missing == []
        assert 99 in unexpected

    def test_empty_parsed(self):
        complete, missing, unexpected = validate_coverage({}, 3)
        assert complete is False
        assert missing == [1, 2, 3]

    def test_zero_expected(self):
        complete, missing, unexpected = validate_coverage({}, 0)
        assert complete is True
