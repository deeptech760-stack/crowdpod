# Crowdpod: notes for contributors

Read `docs/ARCHITECTURE.md` first and `docs/PROGRESS.md` for the current state.

## Layout
- `backend/` is Python 3.11, managed with uv. Run everything with `uv run ...` from `backend/`.
- `frontend/` is Next.js 16 (static export). Its own `frontend/AGENTS.md` warns that this Next version differs from older docs. Check `node_modules/next/dist/docs/` before using an unfamiliar API.
- `vault/` is an Obsidian vault holding the persona archetypes and every prompt template. Prompt wording belongs there, not in Python strings.

## Rules
- Ideas are whatever the user types. Don't hard-code any example idea into the product. Test fixtures live in `backend/tests/fixtures/`.
- The default model provider is `mock` (offline, deterministic). Tests must pass with it and must not need a network or a key.
- Every model call goes through `LLMProvider` with a `task` and a structured `context`. If you add a task, add it to `MockProvider` too.
- The UI builds run state only from the SSE event stream. If you add pipeline output, emit an event for it and handle it in `RunView.tsx`.
- Files adapted from the upstream project keep their one-line header pointing to `NOTICE`. The project is AGPL-3.0.
- Persona patience is in simulated seconds (`hands/agent.py`), not wall-clock time.

## Checks before handing over
```sh
cd backend && uv run pytest -q
cd frontend && npx tsc --noEmit && npx eslint . && npx next build
```
