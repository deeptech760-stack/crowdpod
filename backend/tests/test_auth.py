"""Sign-in: accounts, sessions, lockout, the MCP token, and Google sign-in against a fake Google."""

from __future__ import annotations

import base64
import json
import sqlite3
import threading
import time
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from crowdpod import auth
from crowdpod.api import create_app

PASSWORD = "correct horse battery"


@pytest.fixture
def secured(settings):
    return replace(settings, auth_required=True)


def _register(client, email="asha@example.com", password=PASSWORD):
    return client.post("/api/auth/register", json={"name": "Asha", "email": email, "password": password})


def test_everything_needs_sign_in(secured):
    with TestClient(create_app(secured)) as client:
        assert client.get("/api/runs").status_code == 401
        assert client.get("/api/settings").status_code == 401
        assert client.get("/api/runs/x/events").status_code == 401
        assert client.get("/api/health").json() == {"ok": True}  # no setup details before sign-in
        assert client.get("/api/auth/me").json()["user"] is None


def test_register_login_logout(secured):
    with TestClient(create_app(secured)) as client:
        r = _register(client)
        assert r.status_code == 200 and r.json()["user"]["email"] == "asha@example.com"
        cookie = r.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=lax" in cookie
        assert client.get("/api/runs").status_code == 200
        assert "provider" in client.get("/api/health").json()

        assert client.post("/api/auth/logout").status_code == 200
        client.cookies.clear()
        assert client.get("/api/runs").status_code == 401

        assert client.post("/api/auth/login", json={"email": "ASHA@example.com", "password": PASSWORD}).status_code == 200
        assert client.get("/api/auth/me").json()["user"]["name"] == "Asha"

    # the password is stored hashed, never in clear
    rows = sqlite3.connect(secured.db_path).execute("select password_hash from users").fetchall()
    assert rows and rows[0][0].startswith("scrypt$") and PASSWORD not in rows[0][0]


def test_logout_really_ends_the_session(secured):
    with TestClient(create_app(secured)) as client:
        token = _register(client).cookies.get(auth.SESSION_COOKIE)
        client.post("/api/auth/logout")
        client.cookies.clear()
        client.cookies.set(auth.SESSION_COOKIE, token)  # replaying the old cookie must not work
        assert client.get("/api/runs").status_code == 401


def test_bad_input_and_wrong_passwords(secured):
    with TestClient(create_app(secured)) as client:
        assert _register(client, password="short").status_code == 400
        assert _register(client, email="not-an-email").status_code == 400
        assert _register(client).status_code == 200
        client.cookies.clear()
        assert _register(client).status_code == 409  # same email twice
        assert client.post("/api/auth/login", json={"email": "asha@example.com", "password": "nope"}).status_code == 401
        assert client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "nope"}).status_code == 401


def test_repeated_failures_lock_out(secured):
    with TestClient(create_app(secured)) as client:
        _register(client)
        client.cookies.clear()
        codes = [client.post("/api/auth/login", json={"email": "asha@example.com", "password": "wrong"}).status_code
                 for _ in range(6)]
        assert codes[:5] == [401] * 5 and codes[5] == 429
        # even the right password is refused while locked
        assert client.post("/api/auth/login", json={"email": "asha@example.com", "password": PASSWORD}).status_code == 429


def test_mcp_token_works_and_others_dont(secured):
    with TestClient(create_app(secured)) as client:
        token = (secured.data_dir / "mcp-token").read_text(encoding="utf-8").strip()
        assert client.get("/api/runs", headers={"Authorization": f"Bearer {token}"}).status_code == 200
        assert client.get("/api/runs", headers={"Authorization": "Bearer guess"}).status_code == 401


def test_google_off_until_configured(secured):
    with TestClient(create_app(secured)) as client:
        assert client.get("/api/auth/config").json() == {"required": True, "google": False}
        assert client.get("/api/auth/google/start", follow_redirects=False).status_code == 404


# ---------------------------------------------------------------- Google sign-in


class FakeGoogle:
    """Google's token endpoint: returns an ID token with whatever claims the test sets."""

    def __init__(self) -> None:
        self.claims: dict = {}
        self.received: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002
                pass

            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers["Content-Length"])).decode()
                outer.received.append({k: v[0] for k, v in parse_qs(body).items()})
                part = base64.urlsafe_b64encode(json.dumps(outer.claims).encode()).rstrip(b"=").decode()
                payload = json.dumps({"id_token": f"eyJhbGciOiJub25lIn0.{part}.sig"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/token"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def google(secured, monkeypatch):
    fake = FakeGoogle()
    monkeypatch.setattr(auth, "GOOGLE_TOKEN_URL", fake.url)
    configured = replace(secured, google_client_id="client-123.apps.googleusercontent.com",
                         google_client_secret="test-secret", app_url="http://127.0.0.1:3000")
    yield configured, fake
    fake.server.shutdown()


def _start(client):
    r = client.get("/api/auth/google/start", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].startswith("https://accounts.google.com/")
    q = {k: v[0] for k, v in parse_qs(urlparse(r.headers["location"]).query).items()}
    assert q["code_challenge_method"] == "S256" and q["scope"] == "openid email profile"
    return q


def _claims(q, **over):
    return {"iss": "https://accounts.google.com", "aud": "client-123.apps.googleusercontent.com", "sub": "g-42",
            "email": "meera@example.com", "email_verified": True, "name": "Meera", "nonce": q["nonce"],
            "exp": time.time() + 600, **over}


def test_google_sign_in(google):
    settings, fake = google
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/auth/config").json()["google"] is True
        q = _start(client)
        fake.claims = _claims(q)
        r = client.get("/api/auth/google/callback", params={"state": q["state"], "code": "abc"}, follow_redirects=False)
        assert r.status_code == 302 and r.headers["location"] == "http://127.0.0.1:3000/app/"
        me = client.get("/api/auth/me").json()["user"]
        assert me["email"] == "meera@example.com" and me["google"] is True
        # the code was exchanged with PKCE and the client secret, server to server
        assert fake.received[0]["code_verifier"] and fake.received[0]["client_secret"] == "test-secret"
        # the same state can't be used twice
        r2 = client.get("/api/auth/google/callback", params={"state": q["state"], "code": "abc"}, follow_redirects=False)
        assert "error=" in r2.headers["location"]


def test_google_takes_over_an_account_with_the_same_email(google):
    """Already registered with a password? Google sign-in opens that same account, with its runs.
    Because the password account's email was never verified, whoever set that password (possibly
    someone else, registering your email first) loses access."""
    settings, fake = google
    with TestClient(create_app(settings)) as client:
        first = _register(client, email="meera@example.com").json()["user"]
        token = client.post("/api/tokens", json={"name": "old"}).json()["token"]
        squatter = dict(client.cookies)
        client.cookies.clear()

        q = _start(client)
        fake.claims = _claims(q, email="Meera@Example.com")
        r = client.get("/api/auth/google/callback", params={"state": q["state"], "code": "abc"}, follow_redirects=False)
        assert r.headers["location"] == "http://127.0.0.1:3000/app/"
        me = client.get("/api/auth/me").json()["user"]
        assert me["id"] == first["id"] and me["google"] is True  # the same account

        # the earlier password, sessions and tokens no longer work
        client.cookies.clear()
        r = client.post("/api/auth/login", json={"email": "meera@example.com", "password": PASSWORD})
        assert r.status_code == 401 and "Google" in r.json()["detail"]
        client.cookies.update(squatter)
        assert client.get("/api/runs").status_code == 401
        client.cookies.clear()
        assert client.get("/api/runs", headers={"Authorization": f"Bearer {token}"}).status_code == 401

        # and signing in with Google again keeps working
        q = _start(client)
        fake.claims = _claims(q)
        client.get("/api/auth/google/callback", params={"state": q["state"], "code": "abc"}, follow_redirects=False)
        assert client.get("/api/auth/me").json()["user"]["id"] == first["id"]


@pytest.mark.parametrize("bad", [
    {"aud": "someone-else"}, {"iss": "https://evil.example"}, {"nonce": "replayed"},
    {"email_verified": False}, {"exp": 1},
])
def test_google_rejects_bad_tokens(google, bad):
    settings, fake = google
    with TestClient(create_app(settings)) as client:
        q = _start(client)
        fake.claims = _claims(q, **bad)
        r = client.get("/api/auth/google/callback", params={"state": q["state"], "code": "abc"}, follow_redirects=False)
        assert r.headers["location"].startswith("http://127.0.0.1:3000/login/?error=")
        assert client.get("/api/auth/me").json()["user"] is None


def test_google_sign_in_must_start_in_this_browser(google):
    settings, fake = google
    with TestClient(create_app(settings)) as client:
        q = _start(client)
        fake.claims = _claims(q)
        client.cookies.clear()  # an attacker's link, finished in a browser that didn't start it
        r = client.get("/api/auth/google/callback", params={"state": q["state"], "code": "abc"}, follow_redirects=False)
        assert "error=" in r.headers["location"] and not fake.received
