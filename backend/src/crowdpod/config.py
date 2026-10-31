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
    # sign-in: on by default; CROWDPOD_AUTH=off turns it off (only sensible on a private machine)
    auth_required: bool = field(default_factory=lambda: _env("AUTH", "on") != "off")
    # Google sign-in, from an OAuth client the owner creates in Google Cloud (left empty = off)
    google_client_id: str = field(default_factory=lambda: _env("GOOGLE_CLIENT_ID"))
    google_client_secret: str = field(default_factory=lambda: _env("GOOGLE_CLIENT_SECRET"))
    # where this API and the web app are reached in the browser (for Google's redirect)
    public_url: str = field(default_factory=lambda: _env("PUBLIC_URL", "http://127.0.0.1:8000").rstrip("/"))
    app_url: str = field(default_factory=lambda: _env("APP_URL", "http://127.0.0.1:3000").rstrip("/"))

    # local = one person on their own machine; public = a hosted, multi-user site (strict limits)
    mode: str = field(default_factory=lambda: _env("MODE", "local"))
    # extra browser origins allowed to call the API with cookies, e.g. https://crowdpod.vercel.app
    allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(o.strip().rstrip("/") for o in _env("ALLOWED_ORIGINS").split(",") if o.strip())
    )
    # behind a reverse proxy (Vercel, a load balancer): take the client address from X-Forwarded-For
    trust_proxy: bool = field(default_factory=lambda: _env("TRUST_PROXY", "0") == "1")
    # emails allowed to change server-wide settings in public mode
    admin_emails: tuple[str, ...] = field(
        default_factory=lambda: tuple(e.strip().lower() for e in _env("ADMIN_EMAILS").split(",") if e.strip())
    )
    # where security alerts are emailed (defaults to the admins); SMTP is set with CROWDPOD_SMTP_*
    alert_emails: tuple[str, ...] = field(
        default_factory=lambda: tuple(e.strip().lower() for e in _env("ALERT_EMAILS").split(",") if e.strip())
    )

    @property
    def public(self) -> bool:
        return self.mode == "public"

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    # Limits: generous on your own machine, strict on a public site.
    @property
    def max_crowd(self) -> int:
        return 500 if self.public else 5000

    @property
    def runs_per_hour(self) -> int:
        return 10 if self.public else 1000

    @property
    def concurrent_runs(self) -> int:
        return 2 if self.public else 20

    @property
    def hands_runs_per_day(self) -> int:
        return 5 if self.public else 1000

    @property
    def max_visitors(self) -> int:
        return 3 if self.public else 20

    @property
    def max_body_bytes(self) -> int:
        return 256 * 1024

    @property
    def allow_private_urls(self) -> bool:
        """Browser agents may visit localhost and private networks only on your own machine."""
        return not self.public

    @property
    def generated_dir(self) -> Path:
        """Where personas generated for ideas are saved as Obsidian notes."""
        override = _env("GENERATED_DIR")
        return Path(override) if override else self.vault_dir / "personas" / "generated"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "crowdpod.sqlite3"

    @property
    def artifacts_dir(self) -> Path:
        return self.data_dir / "artifacts"


def get_settings() -> Settings:
    return Settings()
