"""Runs one Crowdpod job from idea to report, publishing events along the way."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from .aggregate import summarise
from .audience import AudienceUnavailable, adopt_audience, build_audience, describe_personas
from .architect import Architect
from .config import Settings
from .crowd import CrowdRunner
from .events import EventBus
from .llm import make_provider
from .llm.base import LLMProvider
from .llm.mock import MockProvider
from .runtime import RuntimeSettings, SettingsStore
from .models import Archetype, CrowdSummary, HandsSession, HandsStep, Persona, Reaction, Research, RunRequest
from .sampler import CrowdSampler
from .store import Store
from .vault import Vault

logger = logging.getLogger("crowdpod.pipeline")
security_log = logging.getLogger("crowdpod.security")

Emit = Callable[[str, dict[str, Any] | None], Awaitable[None]]


def _persona_card(a: Archetype) -> dict[str, Any]:
    """What the UI shows about a generated persona."""
    return {
        "id": a.id, "label": a.label, "share": round(a.weight, 3), "profession": a.profession, "city": a.city,
        "age": a.age, "budget_month": a.budget_month, "purchase_budget": a.purchase_budget,
        "objections": a.objections[:3], "must_haves": a.must_haves[:3], "evidence": a.evidence[:3],
        "note": a.source,
    }


def _mix(req: RunRequest, generated: dict[str, Archetype], vault: Vault,
         described: dict[str, Archetype] | None = None) -> dict[str, float] | None:
    """Crowd weights: generated personas by market share, built-in ones by their own weights, and each
    person the user described as one more segment of average size."""
    builtin = req.mix or {a.id: a.weight for a in vault.archetypes.values()}
    if not generated:
        mix: dict[str, float] | None = req.mix
        base = builtin
    else:
        gen = {a.id: a.weight for a in generated.values()}
        if req.audience != "both":  # "generated", or personas supplied with the request
            mix = base = gen
        else:
            # half the crowd from each, so neither side drowns the other
            gs, bs = sum(gen.values()) or 1, sum(builtin.values()) or 1
            mix = base = {**{k: v / gs for k, v in gen.items()}, **{k: v / bs for k, v in builtin.items()}}
    if not described:
        return mix
    average = sum(base.values()) / max(len(base), 1)
    return {**base, **{aid: average for aid in described}}


def new_run_id() -> str:
    return "r" + secrets.token_hex(4)


def pick_hands_personas(
    crowd: list[Persona], reactions: list[Reaction], summary: CrowdSummary, k: int, preferred: list[str] | None = None
) -> list[Persona]:
    """Cover the segments that matter: any the user asked for, then best, worst and the rest by score.
    Within a segment prefer someone undecided, since they show where the site loses people."""
    order = [s.archetype_id for s in summary.segments]
    if summary.worst_segment in order:
        order.remove(summary.worst_segment)
        order.insert(1 if summary.best_segment else 0, summary.worst_segment)
    for a in reversed(preferred or []):
        if a in order:
            order.remove(a)
            order.insert(0, a)
    verdict = {r.persona_id: r.verdict for r in reactions}
    rank = {"maybe": 0, "adopt": 1, "reject": 2}
    pools: dict[str, list[Persona]] = defaultdict(list)
    for p in sorted(crowd, key=lambda p: (rank[verdict[p.id]], p.id)):
        pools[p.archetype_id].append(p)
    chosen: list[Persona] = []
    while len(chosen) < k and any(pools[a] for a in order):
        for a in order:
            if pools[a] and len(chosen) < k:
                chosen.append(pools[a].pop(0))
    return chosen


@dataclass
class Pipeline:
    settings: Settings
    vault: Vault
    store: Store
    bus: EventBus
    runtime: SettingsStore
    # settings captured when each run was queued, so a change mid-run doesn't affect it
    _snapshots: dict[str, RuntimeSettings] = field(default_factory=dict)
    # told about guardrails that fire during a run: (kind, run_id, detail)
    on_security: Callable[[str, str, str], None] | None = None

    def start(self, request: RunRequest, owner: str | None = None) -> str:
        snapshot = self.runtime.current()
        snapshot.brain.check_ready()
        run_id = new_run_id()
        self.store.create_run(run_id, request, snapshot.brain.label, owner)
        self._snapshots[run_id] = snapshot
        return run_id

    def _blocked(self, run_id: str, url: str, why: str) -> None:
        security_log.warning("blocked browser request run=%s url=%s (%s)", run_id, url[:200], why)
        if self.on_security:
            self.on_security("browser_blocked", run_id, f"{url[:200]} ({why})")

    def _notes_dir(self):  # type: ignore[no-untyped-def]
        # on a public site personas stay in each user's runs, not as shared files on the server
        return None if self.settings.public else self.settings.generated_dir

    async def execute(self, run_id: str, request: RunRequest) -> None:
        snapshot = self._snapshots.pop(run_id, None) or self.runtime.current()
        emit = self.bus.emitter(run_id)
        self.store.set_status(run_id, "running")
        provider: LLMProvider | None = None
        try:
            provider = make_provider(snapshot.brain)
            await emit("run.started", {"provider": snapshot.brain.label, "brief": request.brief.model_dump()})
            await self._run(run_id, request, emit, provider, snapshot)
            self.store.set_status(run_id, "finished")
            await emit("run.finished", {})
        except Exception as e:
            logger.exception("run %s failed", run_id)
            self.store.set_status(run_id, "failed", f"{type(e).__name__}: {e}")
            await emit("run.failed", {"error": f"{type(e).__name__}: {e}"})
        finally:
            if provider:
                await provider.aclose()

    async def _run(
        self, run_id: str, req: RunRequest, emit: Emit, provider: LLMProvider, snapshot: RuntimeSettings
    ) -> None:
        brief = req.brief

        # 1. research the market and design personas for this idea
        generated: dict[str, Archetype] = {}
        research: Research | None = None
        if req.provided_audience:
            # personas designed elsewhere (e.g. by an MCP client with its own web search)
            await emit("research.started", {"count": len(req.provided_audience.personas)})
            research = req.provided_research or Research(summary="Personas supplied with the request.")
            generated = adopt_audience(
                self.vault, brief, req.provided_audience, research, out_dir=self._notes_dir(), run_id=run_id,
            )
            self.store.save_extra(run_id, "research", research.model_dump())
            self.store.save_extra(run_id, "archetypes", [a.model_dump() for a in generated.values()])
            await emit("research.done", research.model_dump())
            await emit("audience.created", {"personas": [_persona_card(a) for a in generated.values()]})
        elif req.audience in ("generated", "both"):
            await emit("research.started", {"count": req.audience_size})
            try:
                research, generated = await build_audience(
                    self.vault, provider, brief, count=req.audience_size, notes=req.context_notes,
                    out_dir=self._notes_dir(), run_id=run_id,
                )
                self.store.save_extra(run_id, "research", research.model_dump())
                self.store.save_extra(run_id, "archetypes", [a.model_dump() for a in generated.values()])
                await emit("research.done", research.model_dump())
                await emit("audience.created", {"personas": [_persona_card(a) for a in generated.values()]})
            except AudienceUnavailable as e:
                await emit("audience.skipped", {"reason": f"{e}. Using the built-in personas instead."})
            except Exception as e:
                logger.exception("audience generation failed for %s", run_id)
                await emit("audience.skipped", {
                    "reason": f"Couldn't generate personas ({type(e).__name__}: {str(e)[:200]}). Using the built-in personas instead.",
                })
        # 1b. the people the user described, each turned into a full persona
        described: dict[str, Archetype] = {}
        if req.described:
            await emit("persona.describing", {"count": len(req.described)})
            try:
                described = await describe_personas(
                    self.vault.extended(generated), provider, brief, req.described, research=research,
                    out_dir=self._notes_dir(), run_id=run_id,
                )
            except Exception as e:  # a model that can't do it: the offline builder always can
                logger.warning("described personas fell back to offline for %s: %s", run_id, e)
                described = await describe_personas(
                    self.vault.extended(generated), MockProvider(), brief, req.described, research=research,
                    out_dir=self._notes_dir(), run_id=run_id,
                )
            everyone = {**generated, **described}
            self.store.save_extra(run_id, "archetypes", [a.model_dump() for a in everyone.values()])
            await emit("audience.created", {"personas": [_persona_card(a) for a in everyone.values()]})

        vault = self.vault.extended({**generated, **described})
        archetypes = vault.archetypes

        # 2. assemble the crowd
        crowd = CrowdSampler(vault, req.seed).sample(
            req.crowd_size, run_id, _mix(req, generated, self.vault, described))
        self.store.save_personas(run_id, crowd)
        counts: dict[str, int] = defaultdict(int)
        for p in crowd:
            counts[p.archetype_id] += 1
        await emit("crowd.assembled", {"size": len(crowd), "segments": counts})

        # 3. reactions
        done = 0

        async def on_reaction(p: Persona, r: Reaction) -> None:
            nonlocal done
            done += 1
            self.store.save_reaction(run_id, r)
            await emit("reaction", {
                "n": done, "of": len(crowd), "persona": {"id": p.id, "name": p.name, "age": p.age,
                "archetype_id": p.archetype_id, "mood": p.mood}, "reaction": r.model_dump(),
            })

        async def on_degraded(ids: list[str], error: str) -> None:
            await emit("crowd.degraded", {"personas": len(ids), "error": error})

        runner = CrowdRunner(vault, provider, batch_size=snapshot.brain.batch_size,
                             concurrency=snapshot.brain.concurrency)
        reactions = await runner.run(brief, crowd, on_reaction, on_degraded)
        await emit("stage.done", {"stage": "crowd"})

        # 4. aggregate
        summary = summarise(brief, crowd, reactions, archetypes)
        self.store.save_summary(run_id, summary)
        await emit("summary", summary.model_dump())

        # 5. architect
        docs = await Architect(vault, provider).write(brief, summary, crowd, reactions, research)
        self.store.save_docs(run_id, docs)
        out = self.settings.artifacts_dir / run_id
        out.mkdir(parents=True, exist_ok=True)
        (out / "brd.md").write_text(docs.brd_md, encoding="utf-8")
        (out / "prd.md").write_text(docs.prd_md, encoding="utf-8")
        await emit("docs", {"brd_md": docs.brd_md, "prd_md": docs.prd_md})

        # 6. hands
        sessions: list[HandsSession] = []
        if req.hands:
            chosen = pick_hands_personas(crowd, reactions, summary, req.hands.personas, req.hands.archetypes)
            sessions = await self._hands(run_id, req, chosen, emit, provider, snapshot, vault)

        # 7. report
        report = {
            "run_id": run_id, "provider": snapshot.brain.label, "brief": brief.model_dump(),
            "summary": summary.model_dump(), "hands": [s.model_dump() for s in sessions],
        }
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _hands(
        self, run_id: str, req: RunRequest, chosen: list[Persona], emit: Emit,
        provider: LLMProvider, snapshot: RuntimeSettings, vault: Vault,
    ) -> list[HandsSession]:
        from .hands.agent import run_session
        from .hands.driver import PlaywrightBrowser

        assert req.hands
        hands = req.hands
        shots = self.settings.artifacts_dir / run_id / "shots"
        semaphore = asyncio.Semaphore(snapshot.browser.parallel)
        await emit("hands.started", {"url": hands.url, "personas": [p.id for p in chosen]})

        async def on_step(p: Persona, step: HandsStep) -> None:
            await emit("hands.step", {"persona_id": p.id, "name": p.name, "step": step.model_dump()})

        browser_cfg = snapshot.browser
        async with PlaywrightBrowser(headless=not browser_cfg.show_windows, slow_mo=browser_cfg.slow_mo_ms) as browser:

            async def one(p: Persona) -> HandsSession:
                async with semaphore:
                    arch = vault.archetypes[p.archetype_id]
                    driver = await browser.driver(
                        p.device, allow_private=self.settings.allow_private_urls,
                        on_block=lambda url, why: self._blocked(run_id, url, why),
                    )
                    try:
                        session = await run_session(
                            driver=driver, provider=provider, vault=vault, persona=p, archetype=arch,
                            url=hands.url, goal=hands.goal_for(arch), max_steps=hands.max_steps,
                            shots_dir=shots, shot_prefix=p.id, on_step=on_step,
                        )
                    finally:
                        await driver.close()
                self.store.save_session(run_id, session)
                await emit("hands.session", session.model_dump(exclude={"steps"}))
                return session

            sessions = await asyncio.gather(*(one(p) for p in chosen))
        await emit("stage.done", {"stage": "hands"})
        return list(sessions)
