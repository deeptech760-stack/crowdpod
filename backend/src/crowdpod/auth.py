"""Accounts, sessions and Google sign-in.

- Passwords are hashed with scrypt (salted, standard library) and never stored or logged in clear.
- A session is a random token in an HttpOnly cookie; only its SHA-256 hash is stored.
- Repeated failed logins for an email or address are locked out for a while.
- An administrator can block an account: its sessions end and its tokens stop working.
- Google sign-in is OpenID Connect with state, nonce and PKCE. The ID token comes straight from
  Google's token endpoint over TLS, so (as OpenID Connect allows) its audience, issuer, expiry,
  nonce and verified email are checked instead of its signature.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from .store import Store

SESSION_COOKIE = "cp_session"
OAUTH_COOKIE = "cp_oauth"
SESSION_TTL = 14 * 24 * 3600
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

GOOGLE_AUTH_URL = os.environ.get("CROWDPOD_GOOGLE_AUTH_URL", "https://accounts.google.com/o/oauth2/v2/auth")
GOOGLE_TOKEN_URL = os.environ.get("CROWDPOD_GOOGLE_TOKEN_URL", "https://oauth2.googleapis.com/token")
GOOGLE_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}

SCHEMA = """
create table if not exists users (
  id text primary key, email text not null unique, name text not null, password_hash text,
  google_sub text unique, created_at real not null
);
create table if not exists logins (token_hash text primary key, user_id text not null, expires_at real not null);
create table if not exists tokens (
  id text primary key, user_id text not null, name text not null, token_hash text not null unique,
  created_at real not null, last_used real, revoked integer not null default 0
);
"""


class AuthError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass
class User:
    id: str
    email: str
    name: str
    google: bool
    blocked: bool = False

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "email": self.email, "name": self.name, "google": self.google}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        _, n, r, p, salt, digest = stored.split("$")
        check = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(check, _unb64(digest))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Accounts:
    def __init__(self, store: Store):
        self.store = store
        with store._lock:
            store._db.executescript(SCHEMA)
            columns = {r[1] for r in store._db.execute("pragma table_info(users)")}
            if "blocked" not in columns:  # older databases
                store._db.execute("alter table users add column blocked integer not null default 0")
                store._db.execute("alter table users add column blocked_reason text")
            store._db.commit()

    def _user(self, row: Any) -> User:
        return User(id=row["id"], email=row["email"], name=row["name"], google=bool(row["google_sub"]),
                    blocked=bool(row["blocked"]))

    def _not_blocked(self, user: User) -> User:
        if user.blocked:
            raise AuthError("This account has been blocked. Contact the site owner if you think this is a mistake.", 403)
        return user

    def get(self, user_id: str) -> User | None:
        rows = self.store._all("select * from users where id = ?", (user_id,))
        return self._user(rows[0]) if rows else None

    def set_blocked(self, user_id: str, blocked: bool, reason: str = "") -> None:
        """Block (ending every session) or unblock an account. Its tokens are refused while blocked."""
        self.store._exec("update users set blocked = ?, blocked_reason = ? where id = ?",
                         (int(blocked), reason[:200] if blocked else None, user_id))
        if blocked:
            self.store._exec("delete from logins where user_id = ?", (user_id,))

    def by_email(self, email: str) -> Any:
        rows = self.store._all("select * from users where email = ?", (email.strip().lower(),))
        return rows[0] if rows else None

    def register(self, name: str, email: str, password: str) -> User:
        email = email.strip().lower()
        name = name.strip()
        if not EMAIL.match(email):
            raise AuthError("Enter a valid email address.")
        if not name:
            raise AuthError("Enter your name.")
        if len(password) < 8:
            raise AuthError("Use a password of at least 8 characters.")
        if self.by_email(email):
            raise AuthError("An account with this email already exists. Sign in instead.", 409)
        uid = "u" + secrets.token_hex(6)
        self.store._exec("insert into users (id, email, name, password_hash, google_sub, created_at) values (?, ?, ?, ?, null, ?)", (uid, email, name[:80], hash_password(password), time.time()))
        return User(uid, email, name[:80], False)

    def check_password(self, email: str, password: str) -> User:
        row = self.by_email(email)
        # hash even when the email is unknown, so timing doesn't reveal which emails exist
        ok = verify_password(password, row["password_hash"] if row else hash_password("x"))
        if row and row["google_sub"] and not row["password_hash"]:
            raise AuthError("This account signs in with Google. Use “Continue with Google”.", 401)
        if not row or not ok:
            raise AuthError("Wrong email or password.", 401)
        return self._not_blocked(self._user(row))

    def google_user(self, sub: str, email: str, name: str) -> User:
        rows = self.store._all("select * from users where google_sub = ?", (sub,))
        if rows:
            return self._not_blocked(self._user(rows[0]))
        row = self.by_email(email)
        if row:
            # Google has verified this email, so its owner gets the existing account with all its runs.
            # A password account's email was never verified, and anyone could have registered it first
            # (pre-account hijacking), so that password and every session and token made with it end here.
            self._not_blocked(self._user(row))
            self.store._exec("update users set google_sub = ?, password_hash = null where id = ?", (sub, row["id"]))
            self.store._exec("delete from logins where user_id = ?", (row["id"],))
            self.store._exec("update tokens set revoked = 1 where user_id = ?", (row["id"],))
            return User(row["id"], row["email"], row["name"], True)
        uid = "u" + secrets.token_hex(6)
        self.store._exec("insert into users (id, email, name, password_hash, google_sub, created_at) values (?, ?, ?, null, ?, ?)", (uid, email.lower(), (name or email)[:80], sub, time.time()))
        return User(uid, email.lower(), (name or email)[:80], True)

    def new_session(self, user: User) -> str:
        token = secrets.token_urlsafe(32)
        self.store._exec("insert into logins values (?, ?, ?)", (_token_hash(token), user.id, time.time() + SESSION_TTL))
        return token

    def session_user(self, token: str | None) -> User | None:
        if not token:
            return None
        rows = self.store._all(
            "select u.* from logins l join users u on u.id = l.user_id where l.token_hash = ? and l.expires_at > ?",
            (_token_hash(token), time.time()),
        )
        return self._user(rows[0]) if rows else None

    def end_session(self, token: str | None) -> None:
        if token:
            self.store._exec("delete from logins where token_hash = ?", (_token_hash(token),))

    # personal access tokens, for a user's own agent (MCP) instead of a browser session
    def create_token(self, user: User, name: str) -> tuple[str, dict[str, Any]]:
        active = self.store._all("select count(*) as n from tokens where user_id = ? and revoked = 0", (user.id,))
        if active[0]["n"] >= 10:
            raise AuthError("You have 10 active tokens already. Revoke one first.", 409)
        tid = "t" + secrets.token_hex(5)
        token = "cpat_" + secrets.token_urlsafe(32)  # recognisable prefix helps secret scanners
        now = time.time()
        self.store._exec("insert into tokens values (?, ?, ?, ?, ?, null, 0)",
                         (tid, user.id, (name.strip() or "agent")[:60], _token_hash(token), now))
        return token, {"id": tid, "name": (name.strip() or "agent")[:60], "created_at": now, "last_used": None}

    def list_tokens(self, user: User) -> list[dict[str, Any]]:
        rows = self.store._all(
            "select id, name, created_at, last_used from tokens where user_id = ? and revoked = 0 order by created_at desc",
            (user.id,),
        )
        return [dict(r) for r in rows]

    def revoke_token(self, user: User, token_id: str) -> bool:
        rows = self.store._all("select id from tokens where id = ? and user_id = ? and revoked = 0", (token_id, user.id))
        if not rows:
            return False
        self.store._exec("update tokens set revoked = 1 where id = ?", (token_id,))
        return True

    def token_user(self, token: str) -> User | None:
        if not token.startswith("cpat_"):
            return None
        rows = self.store._all(
            "select u.*, t.id as tid from tokens t join users u on u.id = t.user_id where t.token_hash = ? and t.revoked = 0",
            (_token_hash(token),),
        )
        if not rows:
            return None
        self.store._exec("update tokens set last_used = ? where id = ?", (time.time(), rows[0]["tid"]))
        return self._user(rows[0])


class Limiter:
    """After 5 failed logins for the same email or address, refuse that key for a minute."""

    def __init__(self, attempts: int = 5, window: float = 300, lockout: float = 60):
        self.attempts, self.window, self.lockout = attempts, window, lockout
        self._fails: dict[str, list[float]] = {}
        self._locked: dict[str, float] = {}
        self._lock = threading.Lock()

    def check(self, *keys: str) -> None:
        now = time.time()
        with self._lock:
            for key in keys:
                if self._locked.get(key, 0) > now:
                    raise AuthError("Too many failed attempts. Wait a minute and try again.", 429)

    def failed(self, *keys: str) -> None:
        now = time.time()
        with self._lock:
            for key in keys:
                recent = [t for t in self._fails.get(key, []) if now - t < self.window] + [now]
                self._fails[key] = recent
                if len(recent) >= self.attempts:
                    self._locked[key] = now + self.lockout
                    self._fails[key] = []

    def succeeded(self, *keys: str) -> None:
        with self._lock:
            for key in keys:
                self._fails.pop(key, None)


# ---------------------------------------------------------------- Google (OpenID Connect)


class GoogleFlows:
    """Pending sign-ins: state -> (nonce, PKCE verifier, created). Kept in memory for 10 minutes."""

    def __init__(self) -> None:
        self._pending: dict[str, tuple[str, str, float]] = {}
        self._lock = threading.Lock()

    def start(self, client_id: str, redirect_uri: str) -> tuple[str, str]:
        state, nonce, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(24), secrets.token_urlsafe(48)
        challenge = _b64(hashlib.sha256(verifier.encode()).digest())
        with self._lock:
            now = time.time()
            self._pending = {k: v for k, v in self._pending.items() if now - v[2] < 600}
            self._pending[state] = (nonce, verifier, now)
        url = GOOGLE_AUTH_URL + "?" + urlencode({
            "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code",
            "scope": "openid email profile", "state": state, "nonce": nonce,
            "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "select_account",
        })
        return url, state

    def take(self, state: str) -> tuple[str, str]:
        with self._lock:
            entry = self._pending.pop(state, None)
        if not entry or time.time() - entry[2] > 600:
            raise AuthError("This Google sign-in expired or didn't start here. Try again.")
        return entry[0], entry[1]


def id_token_claims(id_token: str) -> dict[str, Any]:
    try:
        return json.loads(_unb64(id_token.split(".")[1]))
    except (IndexError, ValueError) as e:
        raise AuthError("Google returned an unreadable sign-in token.") from e


async def google_identity(code: str, verifier: str, nonce: str, *, client_id: str, client_secret: str, redirect_uri: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code, "client_id": client_id, "client_secret": client_secret,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code", "code_verifier": verifier,
        })
    if r.status_code != 200:
        raise AuthError("Google didn't accept the sign-in. Try again.", 401)
    claims = id_token_claims(r.json().get("id_token", ""))
    if claims.get("aud") != client_id or claims.get("iss") not in GOOGLE_ISSUERS:
        raise AuthError("The Google sign-in token wasn't issued for this app.", 401)
    if float(claims.get("exp", 0)) < time.time():
        raise AuthError("The Google sign-in token has expired. Try again.", 401)
    if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise AuthError("The Google sign-in didn't match this request. Try again.", 401)
    if not claims.get("email") or claims.get("email_verified") not in (True, "true"):
        raise AuthError("Your Google account's email isn't verified.", 401)
    return claims


# ---------------------------------------------------------------- local token for the MCP server


def mcp_token(data_dir: Path) -> str:
    """A random token the MCP server (same machine) uses instead of a browser session."""
    path = data_dir / "mcp-token"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    data_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token)
    return token
