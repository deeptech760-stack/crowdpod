"""HTTP API for the UI: REST for data, Server-Sent Events for live runs."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from .config import Settings, get_settings
from .events import TERMINAL, EventBus
from .llm import get_provider
from .models import RunRequest
from .pipeline import Pipeline
from .store import Store
from .vault import Vault


class InterviewRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    tasks: set[asyncio.Task[None]] = set()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = Store(settings.db_path)
        provider = get_provider(settings)
        app.state.pipeline = Pipeline(settings, Vault(settings.vault_dir), store, EventBus(store), provider)
        yield
        for t in tasks:
            t.cancel()
        await provider.aclose()
        store.close()

    app = FastAPI(title="Crowdpod", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_methods=["*"], allow_headers=["*"],
    )

    def pipe() -> Pipeline:
        return app.state.pipeline

    def run_or_404(run_id: str) -> dict[str, Any]:
        run = pipe().store.get_run(run_id)
        if not run:
            raise HTTPException(404, "run not found")
        return run

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "provider": pipe().provider.name, "archetypes": len(pipe().vault.archetypes)}

    @app.get("/api/archetypes")
    async def archetypes() -> list[dict[str, Any]]:
        return [a.model_dump() for a in pipe().vault.archetypes.values()]

    @app.post("/api/runs", status_code=202)
    async def create_run(req: RunRequest) -> dict[str, str]:
        if req.mix and set(req.mix) - set(pipe().vault.archetypes):
            raise HTTPException(422, f"unknown archetypes in mix: {sorted(set(req.mix) - set(pipe().vault.archetypes))}")
        run_id = pipe().start(req)
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
        answer = await pipe().provider.complete_text(system, user, task="interview", context={
            "persona": p, "archetype": pipe().vault.archetypes[p.archetype_id],
            "question": body.question, "product": product,
        })
        return {"persona_id": persona_id, "answer": answer}

    return app


app = create_app()
