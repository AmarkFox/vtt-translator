"""Factory for constructing LLM providers from a Config."""

from __future__ import annotations

import logging
from typing import Optional

from ..config import Config
from .base import LLMProvider
from .bedrock import BedrockProvider


def create_provider(config: Config, logger: Optional[logging.Logger] = None) -> LLMProvider:
    """Instantiate an LLMProvider based on `config.provider`.

    Currently only the `bedrock` provider is implemented; other values
    raise a clear error so adding providers later is mechanical.
    """
    provider_name = config.provider.strip().lower()
    if provider_name == "bedrock":
        return BedrockProvider(
            model_id=config.model_id,
            region=config.aws_region,
            max_retries=config.max_retries,
            retry_base_delay=config.retry_base_delay,
            retry_max_delay=config.retry_max_delay,
            post_call_sleep=config.api_sleep_time,
            proxy_url=config.proxy_url,
            logger=logger,
        )
    raise ValueError(
        f"Unsupported LLM provider: {config.provider!r}. "
        f"Supported providers: ['bedrock']"
    )
