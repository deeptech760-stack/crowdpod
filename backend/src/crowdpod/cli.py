"""Command line: `crowdpod run brief.json` for a run without the UI, `crowdpod serve` for the API."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .config import get_settings
from .events import EventBus
from .llm import get_provider
from .models import HandsRequest, IdeaBrief, RunRequest
from .pipeline import Pipeline
from .store import Store
from .vault import Vault


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    brief = IdeaBrief.model_validate_json(Path(args.brief).read_text(encoding="utf-8"))
    hands = HandsRequest(url=args.url, personas=args.hands, max_steps=args.max_steps) if args.url else None
    req = RunRequest(brief=brief, crowd_size=args.size, seed=args.seed, hands=hands)
    store = Store(settings.db_path)
    provider = get_provider(settings)
    pipe = Pipeline(settings, Vault(settings.vault_dir), store, EventBus(store), provider)
    run_id = pipe.start(req)
    print(f"run {run_id} with provider {provider.name}", file=sys.stderr)
    await pipe.execute(run_id, req)
    await provider.aclose()
    run = store.get_run(run_id)
    assert run
    if run["status"] != "finished":
        print(f"failed: {run['error']}", file=sys.stderr)
        return 1
    s = run["summary"]
    print(s["headline"])
    for seg in s["segments"]:
        print(f"  {seg['label']:<18} n={seg['count']:<4} adopt={seg['adoption_rate']:.0%}  median ₹{seg['median_wtp']:g}")
    for sess in store.get_sessions(run_id):
        print(f"  hands: {sess.persona_name} ({sess.archetype_id}) -> {sess.outcome}: {sess.summary}")
    print(f"artifacts: {settings.artifacts_dir / run_id}")
    return 0


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")  # ₹ on Windows consoles
    parser = argparse.ArgumentParser(prog="crowdpod")
    sub = parser.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the pipeline on a brief JSON file")
    r.add_argument("brief")
    r.add_argument("--size", type=int, default=200)
    r.add_argument("--seed", type=int, default=7)
    r.add_argument("--url", help="website for the Hands to use")
    r.add_argument("--hands", type=int, default=5)
    r.add_argument("--max-steps", type=int, default=15)
    s = sub.add_parser("serve", help="start the API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if args.cmd == "run":
        sys.exit(asyncio.run(_run(args)))
    import uvicorn

    uvicorn.run("crowdpod.api:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
