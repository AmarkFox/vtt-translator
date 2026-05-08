"""AWS Bedrock LLM provider (Anthropic Claude models)."""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Optional

import boto3
from botocore.exceptions import ClientError, BotoCoreError

from .base import LLMProvider, RateLimitError, TranslationError


# Bedrock error codes that we consider transient and worth retrying.
_THROTTLING_CODES = {"ThrottlingException", "TooManyRequestsException"}
_TRANSIENT_CODES = _THROTTLING_CODES | {
    "ServiceUnavailableException",
    "InternalServerException",
    "ModelTimeoutException",
    "ModelStreamErrorException",
}


class BedrockProvider(LLMProvider):
    """LLMProvider backed by AWS Bedrock's Anthropic messages API.

    The Bedrock client is created once per instance and reused, which avoids
    the per-call overhead of the old implementation.
    """

    def __init__(
        self,
        model_id: str,
        region: str = "us-west-2",
        *,
        max_retries: int = 5,
        retry_base_delay: float = 2.0,
        retry_max_delay: float = 60.0,
        post_call_sleep: float = 0.0,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._model_id = model_id
        self.region = region
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay
        self.post_call_sleep = post_call_sleep
        self.logger = logger or logging.getLogger(__name__)

        self._client = boto3.client("bedrock-runtime", region_name=region)

    @property
    def model_id(self) -> str:
        return self._model_id

    # ----------------------------- Public API -----------------------------
    def complete(self, prompt: str, *, max_tokens: int) -> str:
        """Call the model with a single user prompt and return its text."""
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }

        def _invoke() -> str:
            response = self._client.invoke_model(
                modelId=self._model_id,
                body=json.dumps(body),
            )
            payload = json.loads(response["body"].read().decode("utf-8"))
            content = payload.get("content") or []
            if not content or "text" not in content[0]:
                raise TranslationError(f"Unexpected Bedrock response shape: {payload!r}")
            return content[0]["text"]

        text = self._retry(_invoke)

        if self.post_call_sleep > 0:
            time.sleep(self.post_call_sleep)
        return text

    # ----------------------------- Internals ------------------------------
    def _retry(self, fn):
        """Run `fn` with exponential backoff + jitter for transient errors."""
        attempt = 0
        while True:
            try:
                return fn()
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                if code in _TRANSIENT_CODES and attempt < self.max_retries:
                    wait = self._backoff(attempt)
                    kind = "throttling" if code in _THROTTLING_CODES else "transient error"
                    self.logger.warning(
                        "Bedrock %s (%s); retry %d/%d after %.1fs",
                        kind, code, attempt + 1, self.max_retries, wait,
                    )
                    time.sleep(wait)
                    attempt += 1
                    continue
                if code in _THROTTLING_CODES:
                    raise RateLimitError(f"Bedrock throttled after {attempt} retries: {e}") from e
                raise TranslationError(f"Bedrock error ({code}): {e}") from e
            except BotoCoreError as e:
                # Network-level errors: also retry.
                if attempt < self.max_retries:
                    wait = self._backoff(attempt)
                    self.logger.warning(
                        "Bedrock network error (%s); retry %d/%d after %.1fs",
                        type(e).__name__, attempt + 1, self.max_retries, wait,
                    )
                    time.sleep(wait)
                    attempt += 1
                    continue
                raise TranslationError(f"Bedrock network error after {attempt} retries: {e}") from e

    def _backoff(self, attempt: int) -> float:
        """Exponential backoff with full jitter, capped at `retry_max_delay`."""
        base = min(self.retry_base_delay * (2 ** attempt), self.retry_max_delay)
        # Full jitter: random.uniform(0, base) smooths bursts.
        return random.uniform(0.0, base)
