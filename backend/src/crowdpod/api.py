"""HTTP API for the UI: REST for data, Server-Sent Events for live runs."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlparse

import hmac

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auth import (
    OAUTH_COOKIE, SESSION_COOKIE, SESSION_TTL, Accounts, AuthError, GoogleFlows, Limiter, google_identity, mcp_token,
)
from .audit import KINDS, Audit, looks_like_injection
from .config import Settings, get_settings
from .sampler import sample_persona
from .netguard import BlockedURL, check_url
from .events import TERMINAL, EventBus
from .llm import make_provider
from .models import RunRequest
from .pipeline import Pipeline
from .runtime import BrainSettings, BrowserSettings, RuntimeSettings, SettingsStore, defaults_from
from .store import Store
from .vault import Vault


security_log = logging.getLogger("crowdpod.security")
TOKEN_PLACEHOLDER = "PASTE_YOUR_TOKEN"  # the page fills in a token the user just created

# Requests that can read or change keys must come from this machine.
LOCAL_CLIENTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def allowed_hosts() -> list[str]:
    """Host headers the API answers to. Blocks DNS-rebinding attacks from other websites."""
    extra = [h.strip() for h in os.environ.get("CROWDPOD_ALLOWED_HOSTS", "").split(",") if h.strip()]
    public = urlparse(os.environ.get("CROWDPOD_PUBLIC_URL", "")).hostname
    return ["127.0.0.1", "localhost", "[::1]", "testserver", *extra, *([public] if public else [])]


def check_public_config(settings: Settings) -> None:
    """Refuse to run a public site in an unsafe configuration; warn about weak spots."""
    if not settings.public:
        return
    if not settings.auth_required:
        raise RuntimeError("CROWDPOD_AUTH=off can't be used with CROWDPOD_MODE=public: anyone could use the site.")
    if not settings.public_url.startswith("https://"):
        security_log.warning("CROWDPOD_PUBLIC_URL isn't https: sign-in cookies won't be marked Secure")
    if not settings.admin_emails:
        security_log.warning("CROWDPOD_ADMIN_EMAILS is empty: nobody can open the admin console or change settings")


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class TokenRequest(BaseModel):
    name: str = Field(default="agent", max_length=60)


# Reachable without signing in. Everything else under /api needs a session (or the MCP token).
PUBLIC_PATHS = {"/api/health", "/api/auth/config", "/api/auth/me", "/api/auth/login", "/api/auth/register",
                "/api/auth/logout", "/api/auth/google/start", "/api/auth/google/callback"}


class SampleRequest(BaseModel):
    archetype: str = Field(max_length=80)


class BlockRequest(BaseModel):
    reason: str = Field(default="", max_length=200)


class InterviewRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class BrainUpdate(BrainSettings):
    # None keeps the saved key, "" removes it; the UI never receives the key back
    api_key: str | None = Field(default=None, max_length=500)  # type: ignore[assignment]


class SettingsUpdate(BaseModel):
    brain: BrainUpdate
    browser: BrowserSettings


class Ping(BaseModel):
    ok: bool


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    tasks: set[asyncio.Task[None]] = set()

    check_public_config(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = Store(settings.db_path)
        runtime = SettingsStore(settings.data_dir / "settings.json", defaults_from(settings))
        app.state.pipeline = Pipeline(settings, Vault(settings.vault_dir), store, EventBus(store), runtime)
        app.state.accounts = Accounts(store)
        app.state.audit = Audit(store, admins=settings.admin_emails, alert_to=settings.alert_emails,
                                app_url=settings.app_url, mailer=app.state.mailer)

        def run_event(kind: str, run_id: str, detail: str) -> None:
            _, owner = store.run_owner(run_id)
            user = app.state.accounts.get(owner) if owner else None
            app.state.audit.record(kind, severity="warning", user=user, detail=f"run {run_id}: {detail}")

        app.state.pipeline.on_security = run_event
        # remote users connect with personal tokens; the machine-local token is for your own computer
        app.state.mcp_token = "" if settings.public else mcp_token(settings.data_dir)
        yield
        for t in tasks:
            t.cancel()
        store.close()

    # a public site doesn't advertise its whole API surface
    docs = {} if not settings.public else {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(title="Crowdpod", version="0.1.0", lifespan=lifespan, **docs)
    app.state.mailer = None  # tests swap in a recording mailer
    limiter = Limiter()
    signups = Limiter(attempts=5, window=3600, lockout=3600)  # account creations per address per hour
    google = GoogleFlows()
    secure_cookies = settings.public_url.startswith("https://")
    local_origin = re.compile(r"^http://(localhost|127\.0\.0\.1)(:\d+)?$")
    trusted_origins = {*settings.allowed_origins, settings.app_url}

    def origin_allowed(origin: str) -> bool:
        return origin in trusted_origins or (not settings.public and bool(local_origin.match(origin)))

    def client_ip(request: Request) -> str:
        if settings.trust_proxy and request.headers.get("x-forwarded-for"):
            return request.headers["x-forwarded-for"].split(",")[0].strip()
        return request.client.host if request.client else ""

    @app.middleware("http")
    async def security(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Size limit, CSRF origin check and sign-in for every /api route, plus security headers."""
        request.state.user = None
        request.state.superuser = not settings.auth_required
        path = request.url.path
        unsafe = request.method in ("POST", "PUT", "PATCH", "DELETE")
        if path.startswith("/api/") and request.method != "OPTIONS":
            length = request.headers.get("content-length")
            if unsafe and length is None and request.headers.get("transfer-encoding"):
                return JSONResponse({"detail": "A content length is required."}, status_code=411)
            if length and (not length.isdigit() or int(length) > settings.max_body_bytes):
                audit(request, "oversize", "warning", detail=f"{request.method} {path} {length[:20]} bytes")
                return JSONResponse({"detail": "Request too large."}, status_code=413)

            bearer = request.headers.get("authorization", "")
            token = bearer[7:] if bearer.startswith("Bearer ") else ""
            user = None
            if token:
                user = app.state.accounts.token_user(token)
                # the machine-local MCP token only exists outside public mode
                if not user and app.state.mcp_token and hmac.compare_digest(token, app.state.mcp_token):
                    request.state.superuser = True
                elif not user:
                    audit(request, "bad_token", "warning", detail=f"{request.method} {path}")
            else:
                user = app.state.accounts.session_user(request.cookies.get(SESSION_COOKIE))
                origin = request.headers.get("origin")
                # cookie-authenticated changes must come from our own pages (CSRF defence)
                if unsafe and origin and not origin_allowed(origin.rstrip("/")):
                    request.state.user = user
                    audit(request, "cross_site", "high", detail=f"{request.method} {path} from {origin[:100]}")
                    return JSONResponse({"detail": "Cross-site request refused."}, status_code=403)
            request.state.user = user
            request.state.via_token = bool(token)
            if user and user.blocked:
                audit(request, "blocked_access", "warning", detail=f"{request.method} {path}")
                return JSONResponse({"detail": "This account has been blocked."}, status_code=403)
            if settings.auth_required and path not in PUBLIC_PATHS and not user and not request.state.superuser:
                return JSONResponse({"detail": "Sign in to use Crowdpod."}, status_code=401)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if path.startswith("/api/") and "artifacts/" not in path:
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if path.startswith("/api/auth/"):
            response.headers["Cache-Control"] = "no-store"
        if secure_cookies:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(trusted_origins),
        allow_origin_regex=None if settings.public else r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Content-Type", "Authorization"],
        allow_credentials=True,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts())

    def audit(request: Request, kind: str, severity: str = "info", *, user=None, email: str = "", detail: str = "") -> None:  # type: ignore[no-untyped-def]
        app.state.audit.record(kind, severity=severity, user=user or getattr(request.state, "user", None),
                               email=email, ip=client_ip(request), detail=detail)

    def is_admin(request: Request) -> bool:
        """The emails in CROWDPOD_ADMIN_EMAILS, and nobody else once that list is set. Only a local
        install without the list falls back to whoever signs in on this machine. (A tunnel such as ngrok
        makes every visitor look local, so set the list before sharing even a local Crowdpod.)"""
        user = request.state.user
        if request.state.superuser or (user and user.email in settings.admin_emails):
            return True
        if settings.public or settings.admin_emails:
            return False
        return bool(user and (request.client.host if request.client else "") in LOCAL_CLIENTS)

    def set_session(response: Response, user) -> None:  # type: ignore[no-untyped-def]
        token = app.state.accounts.new_session(user)
        response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_TTL, httponly=True, samesite="lax",
                            secure=secure_cookies, path="/")

    @app.get("/api/auth/config")
    async def auth_config() -> dict[str, Any]:
        return {"required": settings.auth_required, "google": settings.google_enabled}

    @app.get("/api/auth/me")
    async def me(request: Request) -> dict[str, Any]:
        user = request.state.user
        return {"user": {**user.public(), "admin": is_admin(request)} if user else None,
                "required": settings.auth_required, "mode": settings.mode}

    @app.post("/api/auth/register")
    async def register(body: RegisterRequest, request: Request, response: Response) -> dict[str, Any]:
        key = f"signup:{client_ip(request)}"
        try:
            signups.check(key)
            signups.failed(key)  # every attempt counts towards the hourly limit
            user = app.state.accounts.register(body.name, body.email, body.password)
        except AuthError as e:
            if e.status == 429:
                audit(request, "signup_limit", "warning", email=body.email.strip().lower())
            raise HTTPException(e.status, str(e))
        audit(request, "register", user=user, detail="password")
        set_session(response, user)
        return {"user": user.public()}

    @app.post("/api/auth/login")
    async def login(body: LoginRequest, request: Request, response: Response) -> dict[str, Any]:
        keys = (f"email:{body.email.strip().lower()}", f"ip:{client_ip(request)}")
        try:
            limiter.check(*keys)
            user = app.state.accounts.check_password(body.email, body.password)
        except AuthError as e:
            if e.status == 401:
                limiter.failed(*keys)
            kind = {401: "login_failed", 429: "lockout", 403: "blocked_access"}.get(e.status, "login_failed")
            attempted = body.email.strip().lower()[:200]
            audit(request, kind, "warning", email=attempted, detail=f"for {attempted}")
            raise HTTPException(e.status, str(e))
        limiter.succeeded(*keys)
        audit(request, "login", user=user, detail="password")
        set_session(response, user)
        return {"user": user.public()}

    @app.post("/api/auth/logout")
    async def logout(request: Request, response: Response) -> dict[str, bool]:
        app.state.accounts.end_session(request.cookies.get(SESSION_COOKIE))
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"ok": True}

    @app.get("/api/auth/google/start")
    async def google_start() -> Response:
        if not settings.google_enabled:
            raise HTTPException(404, "Google sign-in isn't set up on this server.")
        url, state = google.start(settings.google_client_id, f"{settings.public_url}/api/auth/google/callback")
        response = RedirectResponse(url, status_code=302)
        # ties the sign-in to this browser, so nobody can finish it for you from elsewhere
        response.set_cookie(OAUTH_COOKIE, state, max_age=600, httponly=True, samesite="lax", secure=secure_cookies, path="/")
        return response

    @app.get("/api/auth/google/callback")
    async def google_callback(request: Request, state: str = "", code: str = "", error: str = "") -> Response:
        back = f"{settings.app_url}/login/"
        claims: dict[str, Any] = {}
        if not settings.google_enabled:
            raise HTTPException(404, "Google sign-in isn't set up on this server.")
        try:
            if error:
                raise AuthError("Google sign-in was cancelled.")
            if not state or not hmac.compare_digest(state, request.cookies.get(OAUTH_COOKIE, "")):
                raise AuthError("This Google sign-in didn't start in this browser. Try again.")
            nonce, verifier = google.take(state)
            claims = await google_identity(
                code, verifier, nonce, client_id=settings.google_client_id, client_secret=settings.google_client_secret,
                redirect_uri=f"{settings.public_url}/api/auth/google/callback",
            )
            user = app.state.accounts.google_user(str(claims["sub"]), str(claims["email"]), str(claims.get("name", "")))
        except AuthError as e:
            from urllib.parse import quote

            if e.status == 403:
                audit(request, "blocked_access", "warning", email=str(claims.get("email", "")))

            response = RedirectResponse(f"{back}?error={quote(str(e))}", status_code=302)
            response.delete_cookie(OAUTH_COOKIE, path="/")
            return response
        response = RedirectResponse(f"{settings.app_url}/app/", status_code=302)
        response.delete_cookie(OAUTH_COOKIE, path="/")
        audit(request, "login", user=user, detail="google")
        set_session(response, user)
        return response

    def pipe() -> Pipeline:
        return app.state.pipeline

    def owner_id(request: Request) -> str | None:
        user = request.state.user
        return user.id if user else None

    def legacy_visible(request: Request) -> bool:
        """Runs from before sign-in existed have no owner: on your own computer, its admins see them."""
        return not settings.public and is_admin(request)

    def run_or_404(run_id: str, request: Request) -> dict[str, Any]:
        """The run, if this caller may see it. Someone else's run is 'not found', not 'forbidden',
        so run ids can't be probed."""
        exists, owner = pipe().store.run_owner(run_id)
        if not exists or not (request.state.superuser or owner == owner_id(request)
                              or (owner is None and legacy_visible(request))):
            raise HTTPException(404, "run not found")
        return pipe().store.get_run(run_id)  # type: ignore[return-value]

    @app.get("/api/health")
    async def health(request: Request) -> dict[str, Any]:
        if settings.auth_required and not request.state.user:
            return {"ok": True}  # says nothing about the setup until you sign in
        brain = pipe().runtime.current().brain
        return {"ok": True, "provider": brain.label, "archetypes": len(pipe().vault.archetypes)}

    def local_only(request: Request) -> None:
        """Server-wide settings: an admin on a public site; this machine otherwise."""
        if settings.public or settings.admin_emails:
            if not is_admin(request) or request.state.via_token:
                audit(request, "admin_denied", "warning", detail=f"{request.method} {request.url.path}")
                raise HTTPException(403, "Only an administrator can change this site's settings.")
            return
        host = request.client.host if request.client else ""
        if host not in LOCAL_CLIENTS:
            raise HTTPException(403, "model settings can only be changed from the machine running Crowdpod")

    def resolve(update: BrainUpdate) -> BrainSettings:
        """Form values plus the saved key when the form left the key untouched."""
        saved = pipe().runtime.current().brain
        data = update.model_dump()
        if data["api_key"] is None:
            # reuse the saved key only for the same provider and endpoint, so a key is never
            # sent to a different service than the one it was entered for
            same = saved.provider == update.provider and saved.base_url == BrainSettings._url(update.base_url)
            data["api_key"] = saved.api_key if same else ""
        return BrainSettings.model_validate(data)

    @app.get("/api/settings")
    async def get_settings_(request: Request) -> dict[str, Any]:
        local_only(request)
        return pipe().runtime.current().public()

    # ------------------------------------------------------------ personal access tokens (for agents)
    def session_user(request: Request):  # type: ignore[no-untyped-def]
        """Token management needs a real browser session: a leaked token can't mint more tokens."""
        if request.state.via_token or not request.state.user:
            raise HTTPException(403, "Manage tokens from the website while signed in.")
        return request.state.user

    @app.get("/api/tokens")
    async def list_tokens(request: Request) -> list[dict[str, Any]]:
        return app.state.accounts.list_tokens(session_user(request))

    @app.post("/api/tokens")
    async def create_token(body: TokenRequest, request: Request) -> dict[str, Any]:
        user = session_user(request)
        try:
            token, info = app.state.accounts.create_token(user, body.name)
        except AuthError as e:
            raise HTTPException(e.status, str(e))
        audit(request, "token_created", detail=f"{info['id']} ({info['name']})")
        return {"token": token, **info}  # the only time the token itself is shown

    @app.delete("/api/tokens/{token_id}")
    async def revoke_token(token_id: str, request: Request) -> dict[str, bool]:
        user = session_user(request)
        if not app.state.accounts.revoke_token(user, token_id):
            raise HTTPException(404, "token not found")
        audit(request, "token_revoked", detail=token_id)
        return {"ok": True}

    @app.put("/api/settings", dependencies=[Depends(local_only)])  # checked before the body is read
    async def put_settings(body: SettingsUpdate, request: Request) -> dict[str, Any]:
        local_only(request)
        try:
            saved = pipe().runtime.save(RuntimeSettings(brain=resolve(body.brain), browser=body.browser))
        except ValueError as e:
            raise HTTPException(422, str(e))
        return saved.public()

    @app.get("/api/settings/mcp")
    async def mcp_setup(request: Request) -> dict[str, Any]:
        """Copy-paste MCP setup for the signed-in user's own agent. TOKEN stands for a personal
        token they create on the same page; it is never filled in by the server."""
        source = os.environ.get("CROWDPOD_SOURCE_URL", "").strip()
        if settings.public or source:
            # remote users install the MCP server from the published source and point it here
            pkg = f"git+{source or 'https://github.com/deeptech760-stack/crowdpod'}#subdirectory=backend"
            args = ["--python", "3.12", "--from", pkg, "crowdpod", "mcp"]
            command = "uvx"
        else:
            args = ["--directory", str(Path(__file__).resolve().parents[2]), "run", "crowdpod", "mcp"]
            command = "uv"
        env = {"CROWDPOD_API_URL": settings.public_url}
        if settings.public:  # your own computer uses its local token; a hosted site needs a personal one
            env["CROWDPOD_TOKEN"] = TOKEN_PLACEHOLDER
        quoted = " ".join(f'"{a}"' if " " in a else a for a in args)
        env_flags = " ".join(f"-e {k}={v}" for k, v in env.items())
        toml_env = ", ".join(f'{k} = "{v}"' for k, v in env.items())
        return {
            "api_url": settings.public_url,
            "needs_token": settings.public,
            # live visits drive Chromium on the agent's computer, so it needs a browser installed once
            "browsers": " ".join([command, *args[:-2], "playwright", "install", "chromium"]),
            "claude_code": f"claude mcp add crowdpod {env_flags} -- {command} {quoted}",
            "codex": f'[mcp_servers.crowdpod]\ncommand = "{command}"\nargs = {json.dumps(args)}\nenv = {{ {toml_env} }}',
            "claude_desktop": json.dumps({"mcpServers": {"crowdpod": {"command": command, "args": args, "env": env}}}, indent=2),
            "opencode": json.dumps({"mcp": {"crowdpod": {"type": "local", "command": [command, *args],
                                                         "environment": env, "enabled": True}}}, indent=2),
        }

    @app.post("/api/settings/test", dependencies=[Depends(local_only)])
    async def test_brain(body: BrainUpdate, request: Request) -> dict[str, Any]:
        """One tiny JSON request to the model, without saving anything."""
        local_only(request)
        brain = resolve(body)
        if brain.provider == "mock":
            return {"ok": True, "label": brain.label, "ms": 0, "detail": "The offline brain needs no connection."}
        start = time.perf_counter()
        try:
            provider = make_provider(brain)
        except ValueError as e:
            return {"ok": False, "label": brain.label, "ms": 0, "detail": str(e)}
        try:
            await asyncio.wait_for(provider.complete_json(
                'You check a connection. Reply with JSON only: {"ok": true}', "Are you there?",
                Ping, task="ping", context={},
            ), timeout=60)
            ms = round((time.perf_counter() - start) * 1000)
            return {"ok": True, "label": brain.label, "ms": ms, "detail": f"The model answered in {ms} ms."}
        except Exception as e:
            return {"ok": False, "label": brain.label, "ms": 0, "detail": brain.redact(f"{type(e).__name__}: {str(e)[:300]}")}
        finally:
            await provider.aclose()

    @app.post("/api/settings/models", dependencies=[Depends(local_only)])
    async def list_models(body: BrainUpdate, request: Request) -> dict[str, Any]:
        """Model names the endpoint offers, to fill the picker."""
        local_only(request)
        brain = resolve(body)
        if brain.provider == "mock" or (brain.provider == "openai" and not brain.base_url):
            return {"models": []}
        if brain.provider == "anthropic" and not brain.api_key:
            raise HTTPException(422, "Enter your Anthropic API key first")
        probe = brain.model_copy(update={"model": brain.model or "probe"})
        provider = make_provider(probe)
        try:
            return {"models": await asyncio.wait_for(provider.list_models(), timeout=20)}  # type: ignore[attr-defined]
        except Exception as e:
            raise HTTPException(502, brain.redact(f"Couldn't list models: {type(e).__name__}: {str(e)[:200]}"))
        finally:
            await provider.aclose()

    # ------------------------------------------------------------ admin console
    def admin_only(request: Request) -> None:
        """Administrators only, from a signed-in browser (never with an agent's token)."""
        if not is_admin(request) or (settings.public and request.state.via_token):
            audit(request, "admin_denied", "warning", detail=f"{request.method} {request.url.path}")
            raise HTTPException(403, "Administrators only.")

    @app.get("/api/admin/overview")
    async def admin_overview(request: Request) -> dict[str, Any]:
        admin_only(request)
        a = app.state.audit
        me = request.state.user
        users = [{**u, "you": bool(me and u["id"] == me.id)} for u in a.users()]
        return {"stats": a.stats(), "users": users, "kinds": KINDS,
                "email_alerts": a.mailer.settings.configured, "alert_to": list(a.alert_to)}

    @app.get("/api/admin/events")
    async def admin_events(request: Request, user_id: str | None = None, only: str | None = None,
                           limit: int = 200) -> list[dict[str, Any]]:
        admin_only(request)
        return app.state.audit.events(user_id=user_id, severity=only, limit=limit)

    @app.post("/api/admin/users/{user_id}/block")
    async def admin_block(user_id: str, body: BlockRequest, request: Request) -> dict[str, bool]:
        admin_only(request)
        target = app.state.accounts.get(user_id)
        if not target:
            raise HTTPException(404, "user not found")
        me = request.state.user
        if target.email in settings.admin_emails or (me and me.id == target.id):
            raise HTTPException(409, "Administrators can't be blocked here. Remove them from CROWDPOD_ADMIN_EMAILS first.")
        app.state.accounts.set_blocked(user_id, True, body.reason)
        app.state.audit.record("blocked", user=target, ip=client_ip(request),
                               detail=f"by {me.email if me else 'owner'}: {body.reason or 'no reason given'}")
        return {"ok": True}

    @app.post("/api/admin/users/{user_id}/unblock")
    async def admin_unblock(user_id: str, request: Request) -> dict[str, bool]:
        admin_only(request)
        target = app.state.accounts.get(user_id)
        if not target:
            raise HTTPException(404, "user not found")
        app.state.accounts.set_blocked(user_id, False)
        me = request.state.user
        app.state.audit.record("unblocked", user=target, ip=client_ip(request), detail=f"by {me.email if me else 'owner'}")
        return {"ok": True}

    @app.post("/api/admin/alerts/test")
    async def admin_test_alert(request: Request) -> dict[str, Any]:
        admin_only(request)
        a = app.state.audit
        sent = a.mailer.send(a.alert_to, "[Crowdpod] Test alert", "Alert emails from your Crowdpod site work.\n")
        return {"sent": sent, "to": list(a.alert_to),
                "detail": "Sent." if sent else "Email isn't set up: set CROWDPOD_SMTP_* (see SECURITY.md)."}

    @app.get("/api/archetypes")
    async def archetypes() -> list[dict[str, Any]]:
        return [a.model_dump() for a in pipe().vault.archetypes.values()]

    @app.post("/api/personas/sample")
    async def sample(body: SampleRequest) -> dict[str, Any]:
        """One person from an archetype, with their character brief: for an agent driving its own browser."""
        vault = pipe().vault
        if body.archetype not in vault.archetypes:
            raise HTTPException(404, f"Unknown persona. Choose one of: {', '.join(vault.archetypes)}")
        p = sample_persona(vault.archetypes[body.archetype], secrets.randbelow(1 << 30), 0, "mcp")
        return {"persona": p.model_dump(), "brief": vault.persona_system_prompt(p)}

    @app.post("/api/runs", status_code=202)
    async def create_run(req: RunRequest, request: Request) -> dict[str, str]:
        if req.mix and set(req.mix) - set(pipe().vault.archetypes):
            raise HTTPException(422, f"unknown archetypes in mix: {sorted(set(req.mix) - set(pipe().vault.archetypes))}")
        owner = owner_id(request)
        if req.crowd_size > settings.max_crowd:
            raise HTTPException(422, f"The crowd can have at most {settings.max_crowd} people here.")
        if req.hands:
            if req.hands.personas > settings.max_visitors:
                raise HTTPException(422, f"At most {settings.max_visitors} visitors per run here.")
            try:
                check_url(req.hands.url, allow_private=settings.allow_private_urls)
            except BlockedURL as e:
                audit(request, "ssrf", "high", detail=f"{req.hands.url[:200]} ({e})")
                raise HTTPException(422, f"That website can't be visited: {e}.")
        if not request.state.superuser:
            now = time.time()
            refusal = ""
            if pipe().store.count_runs(owner, now - 3600) >= settings.runs_per_hour:
                refusal = f"You can start {settings.runs_per_hour} simulations an hour. Try again later."
            elif pipe().store.count_runs(owner, now - 86400, statuses=("queued", "running")) >= settings.concurrent_runs:
                refusal = "Wait for your running simulations to finish first."
            elif req.hands and pipe().store.count_runs(owner, now - 86400, with_hands=True) >= settings.hands_runs_per_day:
                refusal = f"You can send visitors to a website {settings.hands_runs_per_day} times a day."
            if refusal:
                audit(request, "quota", "warning", detail=refusal)
                raise HTTPException(429, refusal)
        suspicious = looks_like_injection(req.brief.name, req.brief.pitch, req.brief.target_hint, req.context_notes,
                                          req.hands.goal if req.hands else "")
        if suspicious:
            # flagged for the owner; the prompts already treat all of this as data, so the run goes ahead
            audit(request, "injection", "warning", detail=f'"{suspicious}" in {req.brief.name[:80]}')
        try:
            run_id = pipe().start(req, owner=owner)
        except ValueError as e:
            raise HTTPException(422, str(e))
        task = asyncio.create_task(pipe().execute(run_id, req))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return {"run_id": run_id}

    @app.get("/api/runs")
    async def list_runs(request: Request) -> list[dict[str, Any]]:
        return pipe().store.list_runs(owner=owner_id(request), everyone=request.state.superuser,
                                      unowned=legacy_visible(request))

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str, request: Request) -> dict[str, Any]:
        return run_or_404(run_id, request)

    @app.get("/api/runs/{run_id}/reactions")
    async def reactions(run_id: str, request: Request, segment: str | None = None, verdict: str | None = None,
                        offset: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        run_or_404(run_id, request)
        offset = max(0, offset)
        return pipe().store.get_reactions(run_id, segment=segment, verdict=verdict, offset=offset, limit=min(limit, 500))

    @app.get("/api/runs/{run_id}/docs")
    async def docs(run_id: str, request: Request) -> dict[str, str]:
        run_or_404(run_id, request)
        d = pipe().store.get_docs(run_id)
        if not d:
            raise HTTPException(404, "documents not ready")
        return d.model_dump()

    @app.get("/api/runs/{run_id}/audience")
    async def audience(run_id: str, request: Request) -> dict[str, Any]:
        """The research and the personas generated for this run (empty when it used the built-in ones)."""
        run_or_404(run_id, request)
        return {
            "research": pipe().store.get_extra(run_id, "research"),
            "personas": [a.model_dump(exclude={"body"}) for a in pipe().store.get_archetypes(run_id).values()],
        }

    @app.get("/api/runs/{run_id}/hands")
    async def hands(run_id: str, request: Request) -> list[dict[str, Any]]:
        run_or_404(run_id, request)
        return [s.model_dump() for s in pipe().store.get_sessions(run_id)]

    @app.get("/api/runs/{run_id}/artifacts/{path:path}")
    async def artifact(run_id: str, path: str, request: Request) -> FileResponse:
        run_or_404(run_id, request)
        base = (settings.artifacts_dir / run_id).resolve()
        target = (base / path).resolve()
        if not target.is_relative_to(base) or not target.is_file():
            raise HTTPException(404, "no such artifact")
        if target.suffix.lower() not in (".png", ".md", ".json"):
            raise HTTPException(404, "no such artifact")
        return FileResponse(target, headers={"Content-Disposition": "inline", "Cache-Control": "private, max-age=3600"})

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str, request: Request, after: int = 0) -> StreamingResponse:
        run_or_404(run_id, request)
        # a reconnecting browser (e.g. after a proxy timeout) resumes where it stopped
        resume = request.headers.get("last-event-id", "")
        after = max(after, int(resume) if resume.isdigit() else 0)
        bus = pipe().bus

        async def stream() -> AsyncIterator[str]:
            q = bus.subscribe(run_id)  # subscribe before replay so nothing falls in between
            try:
                last = after
                for e in pipe().store.get_events(run_id, after):
                    last = e.seq
                    yield f"id: {e.seq}\nevent: {e.type}\ndata: {json.dumps(e.data, ensure_ascii=False)}\n\n"
                    if e.type in TERMINAL:
                        return
                while True:
                    try:
                        e = await asyncio.wait_for(q.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": keep-alive\n\n"
                        continue
                    if e.seq <= last:
                        continue
                    last = e.seq
                    yield f"id: {e.seq}\nevent: {e.type}\ndata: {json.dumps(e.data, ensure_ascii=False)}\n\n"
                    if e.type in TERMINAL:
                        return
            finally:
                bus.unsubscribe(run_id, q)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @app.post("/api/runs/{run_id}/personas/{persona_id}/interview")
    async def interview(run_id: str, persona_id: str, body: InterviewRequest, request: Request) -> dict[str, str]:
        run = run_or_404(run_id, request)
        p = pipe().store.get_persona(run_id, persona_id)
        if not p:
            raise HTTPException(404, "persona not found")
        product = run["request"]["brief"]["name"]
        vault = pipe().vault.extended(pipe().store.get_archetypes(run_id))  # include generated personas
        system = vault.persona_system_prompt(p)
        user = f"You were shown a product called {product}: {run['request']['brief']['pitch']}\n\nQuestion: {body.question}"
        provider = make_provider(pipe().runtime.current().brain)
        try:
            context = {"persona": p, "archetype": vault.archetypes[p.archetype_id],
                       "question": body.question, "product": product}
            try:
                answer = await provider.complete_text(system, user, task="interview", context=context)
            except Exception as e:
                if provider.name == "mock":
                    raise
                fallback = await make_provider(BrainSettings()).complete_text(system, user, task="interview", context=context)
                answer = f"{fallback} (offline brain answered: the model failed with {type(e).__name__})"
        finally:
            await provider.aclose()
        return {"persona_id": persona_id, "answer": answer}

    return app


app = create_app()
