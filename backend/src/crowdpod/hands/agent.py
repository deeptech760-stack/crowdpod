"""Stage 6: one persona uses a real website and thinks out loud."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Awaitable, Callable

from ..llm.base import LLMProvider
from ..llm.mock import MockProvider
from ..models import Archetype, HandsDecision, HandsSession, HandsStep, Persona
from ..sampler import stable_seed
from ..vault import Vault, render
from .driver import BrowserDriver

OnStep = Callable[[Persona, HandsStep], Awaitable[None]]

# Simulated seconds a step costs a person; slower for people less at ease with tech.
# Patience is measured in this simulated time, not in how long the model takes.
_STEP_COST = {"click": (4, 8), "type": (6, 12), "scroll": (6, 10), "back": (3, 5), "done": (1, 2), "give_up": (1, 2)}


def step_seconds(action: str, persona: Persona, rng: random.Random) -> float:
    lo, hi = _STEP_COST[action]
    return round(rng.uniform(lo, hi) * (1.6 - 0.6 * persona.tech_comfort), 1)


def _history_text(steps: list[HandsStep]) -> str:
    if not steps:
        return "(nothing yet, you just arrived)"
    return "\n".join(
        f"{s.index}. {s.action}{' ' + repr(s.target_label) if s.target_label else ''}"
        f"{' ' + s.text if s.text else ''}{' (failed)' if s.error else ''}"
        for s in steps[-8:]
    )


async def run_session(
    *,
    driver: BrowserDriver,
    provider: LLMProvider,
    vault: Vault,
    persona: Persona,
    archetype: Archetype,
    url: str,
    goal: str,
    max_steps: int,
    shots_dir: Path,
    shot_prefix: str,
    on_step: OnStep,
) -> HandsSession:
    rng = random.Random(stable_seed(persona.seed, "hands-time"))
    system = vault.persona_system_prompt(persona)
    steps: list[HandsStep] = []
    elapsed = 0.0
    outcome = "step_limit"

    async def record(decision: HandsDecision, label: str, error: str, page_url: str) -> HandsStep:
        name = f"{shot_prefix}-{len(steps):02d}.png"
        try:
            await driver.screenshot(shots_dir / name)
        except Exception:
            name = ""
        step = HandsStep(
            index=len(steps), t=round(elapsed, 1), thought=decision.thought, action=decision.action,
            target=decision.target, target_label=label, text=decision.text, url=page_url,
            screenshot=name, error=error,
        )
        steps.append(step)
        await on_step(persona, step)
        return step

    try:
        await driver.goto(url)
        for i in range(max_steps):
            obs = await driver.observe()
            user = render(vault.template("hands-step"), {
                "device": persona.device, "goal": goal, "elapsed": f"{elapsed:.0f}s",
                "patience_seconds": persona.patience_seconds, "step": i + 1, "max_steps": max_steps,
                "observation": obs.render(), "history": _history_text(steps),
            })
            context = {
                "persona": persona, "archetype": archetype, "goal": goal, "observation": obs,
                "history": [s.model_dump() for s in steps],
            }
            try:
                decision = await provider.complete_json(system, user, HandsDecision, task="hands", context=context)
            except Exception as e:
                if provider.name == "mock":
                    raise
                # the model failed (quota, timeout, bad reply): the offline brain takes this step
                decision = await MockProvider().complete_json(system, user, HandsDecision, task="hands", context=context)
                decision = decision.model_copy(update={"thought": f"(offline brain: {type(e).__name__}) {decision.thought}"})
            labels = {e["id"]: e["label"] for e in obs.elements}
            error = ""
            if decision.action in ("click", "type") and decision.target not in labels:
                error = f"no element {decision.target!r} on screen"
            elif decision.action not in ("done", "give_up"):
                error = await driver.act(decision)
            elapsed += step_seconds(decision.action, persona, rng)
            await record(decision, labels.get(decision.target, ""), error, obs.url)

            if decision.action == "done":
                outcome = "success"
                break
            if decision.action == "give_up":
                outcome = "gave_up"
                break
            if elapsed >= persona.patience_seconds:
                outcome = "gave_up"
                quit_ = HandsDecision(thought=f"That's {elapsed:.0f} seconds gone. I'm out.", action="give_up")
                await record(quit_, "", "", (await driver.observe()).url)
                break
    except Exception as e:
        outcome = "error"
        steps.append(HandsStep(index=len(steps), t=round(elapsed, 1), thought="", action="give_up", error=f"{type(e).__name__}: {e}"[:300]))

    last = steps[-1].thought if steps else ""
    summary = {
        "success": f"Reached the goal in {elapsed:.0f}s and {len(steps)} steps.",
        "gave_up": f"Gave up after {elapsed:.0f}s: {last}",
        "step_limit": f"Still looking after {len(steps)} steps.",
        "error": f"Session failed: {steps[-1].error if steps else ''}",
    }[outcome]
    return HandsSession(
        persona_id=persona.id, persona_name=persona.name, archetype_id=persona.archetype_id, url=url, goal=goal,
        outcome=outcome, seconds=round(elapsed, 1), summary=summary, steps=steps,
    )
