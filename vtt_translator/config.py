"""Configuration model using pydantic.

Loads from JSON file (optional) with sensible defaults. All paths are
interpreted relative to the current working directory at runtime.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# Supported language codes -> human-readable names for prompt context.
LANGUAGE_NAMES = {
    "zh": "Simplified Chinese (简体中文)",
    "zh-hant": "Traditional Chinese (繁體中文)",
    "en": "English",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
    "es": "Spanish (Español)",
    "fr": "French (Français)",
    "de": "German (Deutsch)",
    "pt": "Portuguese (Português)",
    "ru": "Russian (Русский)",
    "it": "Italian (Italiano)",
    "ar": "Arabic (العربية)",
}


class Config(BaseModel):
    """Runtime configuration for the translator."""

    # -------- Directories --------
    input_dir: Path = Field(default=Path("./vtt"), description="Source VTT directory")
    output_dir: Path = Field(default=Path("./vtt/zh"), description="Translated VTT output directory")
    done_dir: Path = Field(default=Path("./vtt/done"), description="Processed source files are moved here")
    log_dir: Path = Field(default=Path("./logs"), description="Log files directory")

    # -------- LLM provider --------
    provider: str = Field(default="bedrock", description="LLM provider name (currently: bedrock)")
    model_id: str = Field(
        default="global.anthropic.claude-opus-4-6-v1",
        description="Model identifier for the selected provider",
    )
    aws_region: str = Field(default="us-west-2", description="AWS region for Bedrock")
    max_tokens: int = Field(default=4096, ge=256, le=200000, description="Max tokens for LLM response")
    proxy_url: Optional[str] = Field(
        default=None,
        description=(
            "Optional HTTP(S) proxy URL for the LLM provider, e.g. "
            "'http://127.0.0.1:8118'. When set, both HTTP and HTTPS traffic "
            "to the provider go through this proxy. Leave null to connect directly."
        ),
    )
    verify_proxy_on_startup: bool = Field(
        default=True,
        description=(
            "When a proxy_url is set, probe it once at startup to discover "
            "the exit IP and log it. Adds roughly one HTTP request of "
            "latency. Has no effect when proxy_url is null. Set to false "
            "to skip the probe (e.g. in environments where the IP echo "
            "service is blocked but AWS itself is reachable)."
        ),
    )

    # -------- Languages --------
    source_language: str = Field(default="en", description="Source language code")
    target_language: str = Field(default="zh", description="Target language code")

    # -------- Chunking --------
    chunk_size: int = Field(default=50, ge=1, le=500, description="Subtitles per translation batch")
    context_window: int = Field(default=5, ge=0, le=50, description="Context-only subtitles before/after each batch")

    # -------- Retry / backoff --------
    max_retries: int = Field(default=5, ge=0, le=20)
    retry_base_delay: float = Field(default=2.0, ge=0.0, description="Base delay for exponential backoff (seconds)")
    retry_max_delay: float = Field(default=60.0, ge=0.0, description="Cap for a single backoff wait (seconds)")

    # -------- Throttling --------
    api_sleep_time: float = Field(default=2.0, ge=0.0, description="Sleep after each successful API call")
    min_sleep_time: int = Field(default=180, ge=0, description="Min sleep between files in batch mode")
    max_sleep_time: int = Field(default=300, ge=0, description="Max sleep between files in batch mode")

    # -------- Fallback --------
    fallback_to_source: bool = Field(
        default=True,
        description="If True, failed translations fall back to original text; else mark as error",
    )
    fallback_marker: str = Field(default="", description="Suffix appended to fallback captions (for grep-ability)")

    # -------- Concurrency --------
    max_concurrent_files: int = Field(
        default=1, ge=1, le=16,
        description="Max files translated in parallel (batch mode). Currently unused; reserved.",
    )
    max_concurrent_chunks: int = Field(
        default=3, ge=1, le=32,
        description=(
            "Max chunks translated in parallel per file. Higher = faster but more "
            "likely to hit provider rate limits; start small and raise if stable."
        ),
    )

    # -------- Resumable translation --------
    enable_resume: bool = Field(
        default=True,
        description=(
            "If True, per-file translation progress is stored under "
            "<log_dir>/.progress/ and automatically resumed on next run. "
            "Progress files are deleted after a file is fully translated."
        ),
    )

    @field_validator("source_language", "target_language")
    @classmethod
    def _normalize_lang(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("max_sleep_time")
    @classmethod
    def _check_sleep_range(cls, v: int, info) -> int:
        min_val = info.data.get("min_sleep_time", 0)
        if v < min_val:
            raise ValueError(f"max_sleep_time ({v}) must be >= min_sleep_time ({min_val})")
        return v

    # -------- I/O helpers --------
    @classmethod
    def load(cls, config_path: Optional[str | Path] = None) -> "Config":
        """Load config from a JSON file; fall back to defaults if path is None or missing."""
        if not config_path:
            return cls()
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls(**data)

    def save(self, config_path: str | Path) -> None:
        """Save the current config to a JSON file."""
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # mode='json' serializes Path objects as strings
        payload = self.model_dump(mode="json")
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def target_language_name(self) -> str:
        """Human-readable name for the target language."""
        return LANGUAGE_NAMES.get(self.target_language, self.target_language)

    def source_language_name(self) -> str:
        """Human-readable name for the source language."""
        return LANGUAGE_NAMES.get(self.source_language, self.source_language)

    def resume_fingerprint(self) -> dict:
        """Subset of settings that must match for a progress file to be reused.

        If any of these change between runs, the cached translations from the
        previous run are invalidated and a full retranslation is performed.
        Note: chunk_size is intentionally NOT included here — we store
        translations at the caption level, so resuming with a different
        chunk_size just reuses already-translated captions.
        """
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "source_language": self.source_language,
            "target_language": self.target_language,
        }
