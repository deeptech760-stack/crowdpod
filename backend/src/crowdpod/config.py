"""Settings read from the environment (CROWDPOD_*)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def _env(name: str, default: str = "") -> str:
    return os.environ.get(f"CROWDPOD_{name}", default)


@dataclass(frozen=True)
class Settings:
    vault_dir: Path = field(default_factory=lambda: Path(_env("VAULT_DIR", str(ROOT / "vault"))))
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", str(ROOT / "data"))))
    # "mock" (offline, deterministic) or "openai" (any OpenAI-compatible endpoint)
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "mock"))
    llm_base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL"))
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL"))
    llm_concurrency: int = field(default_factory=lambda: int(_env("LLM_CONCURRENCY", "4")))
    crowd_batch_size: int = field(default_factory=lambda: int(_env("CROWD_BATCH_SIZE", "20")))
    hands_concurrency: int = field(default_factory=lambda: int(_env("HANDS_CONCURRENCY", "2")))
    hands_headless: bool = field(default_factory=lambda: _env("HANDS_HEADLESS", "1") != "0")
    # milliseconds Playwright waits between actions, so people can watch the browsers
    hands_slow_mo: int = field(default_factory=lambda: int(_env("HANDS_SLOW_MO", "0")))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "crowdpod.sqlite3"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"


def get_settings() -> Settings:
    return Settings()
