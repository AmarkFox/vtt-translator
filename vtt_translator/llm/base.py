"""Abstract base class for LLM providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class TranslationError(Exception):
    """Raised when an LLM call fails in a non-retryable way, or after retries are exhausted."""


class RateLimitError(TranslationError):
    """Raised when the provider is rate-limiting us."""


class LLMProvider(ABC):
    """Minimal interface every LLM provider must implement.

    Implementations are responsible for:
      - Authentication/setup at construction time.
      - Converting a plain-text prompt into a plain-text response.
      - Retrying transient errors with backoff (use `_retry` in subclasses).
    """

    @abstractmethod
    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int,
        system: Optional[str] = None,
        temperature: Optional[float] = None,
        tag: Optional[str] = None,
    ) -> str:
        """Send a prompt to the model and return its text response.

        Args:
            prompt: The user prompt to send.
            max_tokens: Maximum tokens in the model response.
            system: Optional system-level instructions (separate from user
                prompt). When supported by the provider, this enables prompt
                caching and clearer role separation.
            temperature: Sampling temperature (0.0–1.0). Lower values produce
                more deterministic translations. None means use provider default.
            tag: Optional caller-provided label (e.g. "chunk 3/12") that
                implementations should include in retry/error log messages
                so operators can tell which work item failed. Implementations
                are free to ignore it.
        """
        raise NotImplementedError

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Identifier of the active model (for logging/telemetry)."""
        raise NotImplementedError
