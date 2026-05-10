"""Tests for vtt_translator.llm.factory."""

from unittest.mock import patch

import pytest

from vtt_translator.config import Config
from vtt_translator.llm.bedrock import BedrockProvider
from vtt_translator.llm.factory import create_provider


class TestCreateProvider:
    def test_bedrock_provider(self):
        cfg = Config(provider="bedrock", verify_proxy_on_startup=False)
        with patch("vtt_translator.llm.bedrock.boto3") as mock_boto3:
            mock_boto3.client.return_value = None  # Won't actually call
            provider = create_provider(cfg)
        assert isinstance(provider, BedrockProvider)

    def test_unknown_provider_raises(self):
        cfg = Config(provider="nonexistent")
        with pytest.raises(ValueError, match="nonexistent"):
            create_provider(cfg)
