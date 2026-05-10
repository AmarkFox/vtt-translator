"""Tests for vtt_translator.llm.bedrock (mocked boto3)."""

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError, BotoCoreError

from vtt_translator.llm.base import RateLimitError, TranslationError
from vtt_translator.llm.bedrock import BedrockProvider


def _make_response(text: str) -> dict:
    """Create a fake Bedrock invoke_model response."""
    body = json.dumps({"content": [{"text": text}]}).encode()
    return {"body": BytesIO(body)}


def _client_error(code: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": f"Mock {code}"}},
        "InvokeModel",
    )


@pytest.fixture
def bedrock_provider():
    """Create a BedrockProvider with mocked boto3 client."""
    with patch("vtt_translator.llm.bedrock.boto3") as mock_boto3:
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        provider = BedrockProvider(
            model_id="test-model",
            region="us-east-1",
            max_retries=2,
            retry_base_delay=0.01,
            retry_max_delay=0.05,
            post_call_sleep=0.0,
            verify_proxy_on_startup=False,
        )
        yield provider, mock_client


class TestBedrockProviderSuccess:
    def test_successful_call(self, bedrock_provider):
        provider, client = bedrock_provider
        client.invoke_model.return_value = _make_response("Hello")
        result = provider.complete("test prompt", max_tokens=100)
        assert result == "Hello"
        client.invoke_model.assert_called_once()

    def test_model_id_property(self, bedrock_provider):
        provider, _ = bedrock_provider
        assert provider.model_id == "test-model"


class TestBedrockProviderRetry:
    def test_throttling_retries_then_succeeds(self, bedrock_provider):
        provider, client = bedrock_provider
        client.invoke_model.side_effect = [
            _client_error("ThrottlingException"),
            _make_response("Success after retry"),
        ]
        result = provider.complete("prompt", max_tokens=100)
        assert result == "Success after retry"
        assert client.invoke_model.call_count == 2

    def test_throttling_exhausted_raises_rate_limit(self, bedrock_provider):
        provider, client = bedrock_provider
        client.invoke_model.side_effect = _client_error("ThrottlingException")
        with pytest.raises(RateLimitError):
            provider.complete("prompt", max_tokens=100)
        # max_retries=2, so 1 original + 2 retries = 3 calls
        assert client.invoke_model.call_count == 3

    def test_transient_error_retries(self, bedrock_provider):
        provider, client = bedrock_provider
        client.invoke_model.side_effect = [
            _client_error("ServiceUnavailableException"),
            _make_response("Recovered"),
        ]
        result = provider.complete("prompt", max_tokens=100)
        assert result == "Recovered"

    def test_non_transient_error_raises_immediately(self, bedrock_provider):
        provider, client = bedrock_provider
        client.invoke_model.side_effect = _client_error("ValidationException")
        with pytest.raises(TranslationError):
            provider.complete("prompt", max_tokens=100)
        assert client.invoke_model.call_count == 1

    def test_network_error_retries(self, bedrock_provider):
        provider, client = bedrock_provider
        client.invoke_model.side_effect = [
            BotoCoreError(),
            _make_response("Recovered from network"),
        ]
        result = provider.complete("prompt", max_tokens=100)
        assert result == "Recovered from network"

    def test_network_error_exhausted_raises(self, bedrock_provider):
        provider, client = bedrock_provider
        client.invoke_model.side_effect = BotoCoreError()
        with pytest.raises(TranslationError):
            provider.complete("prompt", max_tokens=100)


class TestBedrockProviderProxy:
    def test_proxy_config_passed_to_boto(self):
        with patch("vtt_translator.llm.bedrock.boto3") as mock_boto3, \
             patch("vtt_translator.llm.bedrock.check_proxy") as mock_check:
            mock_check.return_value = MagicMock(ok=True, exit_ip="1.2.3.4")
            mock_boto3.client.return_value = MagicMock()
            BedrockProvider(
                model_id="test",
                proxy_url="http://127.0.0.1:8118",
                verify_proxy_on_startup=True,
            )
            # Verify config with proxies was passed
            call_kwargs = mock_boto3.client.call_args[1]
            assert "config" in call_kwargs
