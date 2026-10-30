# Progress

## 2026-10-30: first working version

Done and verified:
- **Backend engine.** Vault loader, seeded crowd sampler, offline provider, OpenAI-compatible provider (adapted upstream client), batched crowd reactions with per-batch fallback, aggregation, architect (BRD/PRD), Hands agent with a Playwright driver, SQLite store, event bus with replayable SSE, FastAPI API and a CLI.
- **Backend tests.** `uv run pytest` gives 14 passed. They cover sampling, parsing, the pitch storyline, fallback, two real-Chromium Hands sessions (one persona gives up looking for the price, another finds calendar sync), the full pipeline and the API, including the SSE stream, interviews and path-traversal blocking.
- **Frontend.** The pre-built UI is rebranded to Crowdpod, and the voice and Sarvam multilingual feature is removed. New `/app` (text-only idea form) and `/app/run` (live crowd wall, signal, BRD/PRD, Hands replay, persona interviews).
- **Frontend checks.** `tsc`, `eslint` and `next build` are clean, and `npx playwright test` gives 5 passed.
- **End to end.** A Playwright script against the running API and the static build submitted a new idea through the form and watched it to completion. It checked the interview, the PRD tab and replay on reload, and confirmed no horizontal overflow at 390 and 768 px and no console errors. The same flow was also run by hand in Chrome.

Known limits:
- The offline provider judges ideas by keywords. Real use needs a model endpoint (see README).
- The 8 archetypes are consumers in Bengaluru. Ideas aimed at other audiences need idea-specific archetypes (ARCHITECTURE §9.2).
- The login screen is front-end only.
- Competitor comparison isn't built yet.

Next: ARCHITECTURE.md §9.
