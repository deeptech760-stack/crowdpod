"""Settings people change from the UI: which brain drives the personas, and how the browsers run.

Saved to <data_dir>/settings.json. Environment variables (config.py) only supply the defaults.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

from .config import Settings


class BrainSettings(BaseModel):
    # mock = offline rule-based brain; anthropic = Claude with the user's API key;
    # openai = any OpenAI-compatible endpoint (OpenAI, OpenRouter, Groq, LM Studio, Ollama, ...)
    provider: Literal["mock", "anthropic", "openai"] = "mock"
    base_url: str = Field(default="", max_length=500)
    api_key: str = Field(default="", max_length=500)
    model: str = Field(default="", max_length=200)
    concurrency: int = Field(default=4, ge=1, le=32)
    batch_size: int = Field(default=20, ge=1, le=50)
    effort: Literal["low", "medium", "high"] = "medium"  # Claude only: how hard each decision is thought through

    @field_validator("base_url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if v and urlparse(v).scheme not in ("http", "https"):
            raise ValueError("base URL must start with http:// or https://")
        return v

    def check_ready(self) -> None:
        if self.provider == "openai" and not (self.base_url and self.model):
            raise ValueError("a custom model needs a base URL and a model name")
        if self.provider == "anthropic" and not self.api_key:
            raise ValueError("Claude needs an Anthropic API key")

    @property
    def label(self) -> str:
        """Shown in the UI and stored with each run. Never includes the key."""
        if self.provider == "mock":
            return "mock"
        if self.provider == "anthropic":
            return f"{self.model or 'claude-opus-5-5'} @ Anthropic API"
        return f"{self.model} @ {urlparse(self.base_url).netloc or self.base_url}"

    def redact(self, text: str) -> str:
        """Remove the key from any text that might reach the browser or a log."""
        return text.replace(self.api_key, "***") if self.api_key else text


class BrowserSettings(BaseModel):
    show_windows: bool = False  # open visible Chromium windows so people can watch the agents
    slow_mo_ms: int = Field(default=0, ge=0, le=3000)
    parallel: int = Field(default=2, ge=1, le=8)


class RuntimeSettings(BaseModel):
    brain: BrainSettings = BrainSettings()
    browser: BrowserSettings = BrowserSettings()

    def public(self) -> dict:
        """Safe to send to the browser: the key is replaced by a hint."""
        data = self.model_dump()
        key = data["brain"].pop("api_key")
        data["brain"]["has_key"] = bool(key)
        data["brain"]["key_hint"] = f"…{key[-4:]}" if len(key) >= 8 else ("set" if key else "")
        return data


def defaults_from(env: Settings) -> RuntimeSettings:
    return RuntimeSettings(
        brain=BrainSettings(
            provider=env.llm_provider if env.llm_provider in ("mock", "anthropic", "openai") else "mock",
            base_url=env.llm_base_url, api_key=env.llm_api_key, model=env.llm_model,
            concurrency=env.llm_concurrency, batch_size=env.crowd_batch_size,
        ),
        browser=BrowserSettings(
            show_windows=not env.hands_headless, slow_mo_ms=env.hands_slow_mo, parallel=env.hands_concurrency,
        ),
    )


class SettingsStore:
    def __init__(self, path: Path, defaults: RuntimeSettings):
        self.path = path
        self._lock = threading.Lock()
        self._current = defaults
        if path.is_file():
            saved = json.loads(path.read_text(encoding="utf-8"))
            self._current = RuntimeSettings.model_validate({**defaults.model_dump(), **saved})

    def current(self) -> RuntimeSettings:
        with self._lock:
            return self._current.model_copy(deep=True)

    def save(self, new: RuntimeSettings) -> RuntimeSettings:
        new.brain.check_ready()
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            # the file can hold an API key: create it readable by the owner only
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(new.model_dump_json(indent=2))
            tmp.replace(self.path)
            self._current = new
            return new.model_copy(deep=True)
