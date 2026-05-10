"""Tests for vtt_translator.proxy_diagnostics."""

import socket
import urllib.error
from unittest.mock import MagicMock, patch

from vtt_translator.proxy_diagnostics import ProxyCheckResult, check_proxy


class TestCheckProxy:
    def test_proxy_works(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"1.2.3.4\n"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("vtt_translator.proxy_diagnostics.urllib.request.build_opener") as mock_opener:
            mock_opener.return_value.open.return_value = mock_resp
            result = check_proxy("http://127.0.0.1:8118")

        assert result.ok is True
        assert result.exit_ip == "1.2.3.4"
        assert result.proxy_url == "http://127.0.0.1:8118"

    def test_proxy_unreachable(self):
        with patch("vtt_translator.proxy_diagnostics.urllib.request.build_opener") as mock_opener:
            mock_opener.return_value.open.side_effect = urllib.error.URLError("Connection refused")
            result = check_proxy("http://127.0.0.1:9999")

        assert result.ok is False
        assert result.error is not None
        assert "Connection refused" in result.error

    def test_proxy_timeout(self):
        with patch("vtt_translator.proxy_diagnostics.urllib.request.build_opener") as mock_opener:
            mock_opener.return_value.open.side_effect = socket.timeout()
            result = check_proxy("http://127.0.0.1:8118", timeout=5.0)

        assert result.ok is False
        assert "timed out" in result.error

    def test_no_proxy_direct_connection(self):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"5.6.7.8\n"
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("vtt_translator.proxy_diagnostics.urllib.request.build_opener") as mock_opener:
            mock_opener.return_value.open.return_value = mock_resp
            result = check_proxy(None)

        assert result.ok is True
        assert result.exit_ip == "5.6.7.8"
        assert result.proxy_url is None


class TestProxyCheckResultFormat:
    def test_format_success_with_proxy(self):
        r = ProxyCheckResult(proxy_url="http://proxy:8080", ok=True, exit_ip="1.2.3.4")
        text = r.format()
        assert "http://proxy:8080" in text
        assert "1.2.3.4" in text

    def test_format_failure(self):
        r = ProxyCheckResult(proxy_url="http://proxy:8080", ok=False, error="Connection refused")
        text = r.format()
        assert "Connection refused" in text
