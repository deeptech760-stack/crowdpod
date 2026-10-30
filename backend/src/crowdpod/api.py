"""HTTP API for the UI: REST for data, Server-Sent Events for live runs."""

from __future__ import annotations

import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .config import Settings, get_settings
from .events import TERMINAL, EventBus
from .llm import make_provider
from .models import RunRequest
from .pipeline import Pipeline
from .runtime import BrainSettings, BrowserSettings, RuntimeSettings, SettingsStore, defaults_from
from .store import Store
from .vault import Vault


# Requests that can read or change keys must come from this machine.
LOCAL_CLIENTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def allowed_hosts() -> list[str]:
    """Host headers the API answers to. Blocks DNS-rebinding attacks from other websites."""
    extra = [h.strip() for h in os.environ.get("CROWDPOD_ALLOWED_HOSTS", "").split(",") if h.strip()]
    return ["127.0.0.1", "localhost", "[::1]", "testserver", *extra]


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

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = Store(settings.db_path)
        runtime = SettingsStore(settings.data_dir / "settings.json", defaults_from(settings))
        app.state.pipeline = Pipeline(settings, Vault(settings.vault_dir), store, EventBus(store), runtime)
        yield
        for t in tasks:
            t.cancel()
        store.close()

    app = FastAPI(title="Crowdpod", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["*"], allow_headers=["*"],
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts())

    def pipe() -> Pipeline:
        return app.state.pipeline

    def run_or_404(run_id: str) -> dict[str, Any]:
        run = pipe().store.get_run(run_id)
        if not run:
            raise HTTPException(404, "run not found")
        return run

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        brain = pipe().runtime.current().brain
        return {"ok": True, "provider": brain.label, "archetypes": len(pipe().vault.archetypes)}

    def local_only(request: Request) -> None:
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
    async def get_settings_() -> dict[str, Any]:
        return pipe().runtime.current().public()

    @app.put("/api/settings")
    async def put_settings(body: SettingsUpdate, request: Request) -> dict[str, Any]:
        local_only(request)
        try:
            saved = pipe().runtime.save(RuntimeSettings(brain=resolve(body.brain), browser=body.browser))
        except ValueError as e:
            raise HTTPException(422, str(e))
        return saved.public()

    @app.get("/api/settings/mcp")
    async def mcp_setup(request: Request) -> dict[str, Any]:
        """Copy-paste setup for MCP clients, with this machine's backend path filled in."""
        local_only(request)
        backend = str(Path(__file__).resolve().parents[2])
        args = ["--directory", backend, "run", "crowdpod", "mcp"]
        quoted = " ".join(f'"{a}"' if " " in a else a for a in args)
        return {
            "backend_dir": backend,
            "claude_code": f"claude mcp add crowdpod -- uv {quoted}",
            "codex": '[mcp_servers.crowdpod]\ncommand = "uv"\nargs = ' + json.dumps(args),
            "claude_desktop": json.dumps({"mcpServers": {"crowdpod": {"command": "uv", "args": args}}}, indent=2),
        }

    @app.post("/api/settings/test")
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

    @app.post("/api/settings/models")
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

    @app.get("/api/archetypes")
    async def archetypes() -> list[dict[str, Any]]:
        return [a.model_dump() for a in pipe().vault.archetypes.values()]

    @app.post("/api/runs", status_code=202)
    async def create_run(req: RunRequest) -> dict[str, str]:
        if req.mix and set(req.mix) - set(pipe().vault.archetypes):
            raise HTTPException(422, f"unknown archetypes in mix: {sorted(set(req.mix) - set(pipe().vault.archetypes))}")
        try:
            run_id = pipe().start(req)
        except ValueError as e:
            raise HTTPException(422, str(e))
        task = asyncio.create_task(pipe().execute(run_id, req))
        tasks.add(task)
        task.add_done_callback(tasks.discard)
        return {"run_id": run_id}

    @app.get("/api/runs")
    async def list_runs() -> list[dict[str, Any]]:
        return pipe().store.list_runs()

    @app.get("/api/runs/{run_id}")
    async def get_run(run_id: str) -> dict[str, Any]:
        return run_or_404(run_id)

    @app.get("/api/runs/{run_id}/reactions")
    async def reactions(run_id: str, segment: str | None = None, verdict: str | None = None,
                        offset: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        run_or_404(run_id)
        return pipe().store.get_reactions(run_id, segment=segment, verdict=verdict, offset=offset, limit=min(limit, 500))

    @app.get("/api/runs/{run_id}/docs")
    async def docs(run_id: str) -> dict[str, str]:
        run_or_404(run_id)
        d = pipe().store.get_docs(run_id)
        if not d:
            raise HTTPException(404, "documents not ready")
        return d.model_dump()

    @app.get("/api/runs/{run_id}/hands")
    async def hands(run_id: str) -> list[dict[str, Any]]:
        run_or_404(run_id)
        return [s.model_dump() for s in pipe().store.get_sessions(run_id)]

    @app.get("/api/runs/{run_id}/artifacts/{path:path}")
    async def artifact(run_id: str, path: str) -> FileResponse:
        run_or_404(run_id)
        base = (settings.artifacts_dir / run_id).resolve()
        target = (base / path).resolve()
        if not target.is_relative_to(base) or not target.is_file():
            raise HTTPException(404, "no such artifact")
        return FileResponse(target)

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id: str, after: int = 0) -> StreamingResponse:
        run_or_404(run_id)
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
    async def interview(run_id: str, persona_id: str, body: InterviewRequest) -> dict[str, str]:
        run = run_or_404(run_id)
        p = pipe().store.get_persona(run_id, persona_id)
        if not p:
            raise HTTPException(404, "persona not found")
        product = run["request"]["brief"]["name"]
        system = pipe().vault.persona_system_prompt(p)
        user = f"You were shown a product called {product}: {run['request']['brief']['pitch']}\n\nQuestion: {body.question}"
        provider = make_provider(pipe().runtime.current().brain)
        try:
            answer = await provider.complete_text(system, user, task="interview", context={
                "persona": p, "archetype": pipe().vault.archetypes[p.archetype_id],
                "question": body.question, "product": product,
            })
        finally:
            await provider.aclose()
        return {"persona_id": persona_id, "answer": answer}

    return app


app = create_app()
