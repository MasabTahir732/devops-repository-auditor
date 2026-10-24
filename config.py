"""Load explicit runtime settings without embedding credentials in source."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

from safety import register_secret


class ConfigError(ValueError):
    pass


def _positive(name: str, value: str, *, integer: bool = False) -> int | float:
    try:
        number = int(value) if integer else float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"{name} must be a positive {'integer' if integer else 'number'}."
        ) from exc
    if not math.isfinite(number) or number <= 0:
        raise ConfigError(f"{name} must be finite and positive.")
    return number


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    model: str
    max_steps: int
    timeout: float
    clone_timeout: float
    provider: str = "gemini"

    @classmethod
    def from_environment(cls, args) -> Settings:
        provider = (
            (getattr(args, "provider", None) or os.getenv("LLM_PROVIDER", "gemini")).strip().lower()
        )
        if provider not in {"gemini", "groq", "openai"}:
            raise ConfigError("LLM_PROVIDER must be gemini, groq, or openai.")
        key_name = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "openai": "OPENAI_API_KEY"}[
            provider
        ]
        key = os.getenv(key_name, "").strip()
        if not key or key.lower() in {"your-api-key", "your_api_key_here", "replace-me"}:
            raise ConfigError(
                f"{key_name} is missing. Copy .env.example to .env and set your API key locally."
            )
        register_secret(key)
        defaults = {
            "gemini": "gemini-3.8-flash",
            "groq": "openai/gpt-oss-120b",
            "openai": "gpt-4.1-mini",
        }
        model = (
            args.model
            or os.getenv("LLM_MODEL")
            or os.getenv(f"{provider.upper()}_MODEL", defaults[provider])
        )
        if not model.strip():
            raise ConfigError("The configured model must not be empty.")
        return cls(
            api_key=key,
            provider=provider,
            model=model.strip(),
            max_steps=int(
                _positive(
                    "max steps", args.max_steps or os.getenv("AUDIT_MAX_STEPS", "40"), integer=True
                )
            ),
            timeout=float(_positive("timeout", args.timeout or os.getenv("AUDIT_TIMEOUT", "60"))),
            clone_timeout=float(
                _positive(
                    "clone timeout", args.clone_timeout or os.getenv("AUDIT_CLONE_TIMEOUT", "120")
                )
            ),
        )
