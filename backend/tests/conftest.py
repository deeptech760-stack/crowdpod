from __future__ import annotations

import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from crowdpod.config import ROOT, Settings
from crowdpod.models import IdeaBrief
from crowdpod.vault import Vault

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def vault() -> Vault:
    return Vault(ROOT / "vault")


@pytest.fixture
def brief() -> IdeaBrief:
    return IdeaBrief.model_validate(json.loads((FIXTURES / "brief-fitness.json").read_text(encoding="utf-8")))


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    # generated personas go to a temp folder, never into the real vault
    monkeypatch.setenv("CROWDPOD_GENERATED_DIR", str(tmp_path / "generated"))
    # sign-in has its own tests (test_auth.py); the others test features with it off
    return Settings(vault_dir=ROOT / "vault", data_dir=tmp_path, llm_provider="mock", auth_required=False)


@pytest.fixture(scope="session")
def site_url():
    """Serves tests/fixtures/sites on a free local port."""
    handler = partial(SimpleHTTPRequestHandler, directory=str(FIXTURES / "sites"))
    handler.log_message = lambda *a, **k: None  # type: ignore[attr-defined]
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
