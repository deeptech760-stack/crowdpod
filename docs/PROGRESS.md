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

## 2026-10-30: choose the brain, MCP, security

Done and verified:
- **Settings page** (`/app/settings`): offline brain, Claude (Anthropic API key, official SDK, structured outputs, refusal fallback), or any OpenAI-compatible model (OpenAI, OpenRouter, Groq, Together, LM Studio, Ollama), with test connection, model list and browser options (visible windows, slow motion, browsers at once).
- **MCP server** (`crowdpod mcp`): 9 tools for crowd runs and for live persona visits driven by the client's own model. A stdio session test covers the full flow.
- **Security:** the key never leaves the server, is redacted from errors and is reused only for the same provider and address; settings are loopback-only; a Host-header check blocks DNS rebinding; browsing is limited to http(s); page text is fenced as untrusted.
- **Personas:** placement officer and campus recruiter archetypes added for portals; per-run visitor goals.
- **Setup:** `scripts/setup.*` and `scripts/start.*`, pinned Python and Node versions, and `backend/requirements.txt`.
- **Tests:** `uv run pytest` gives 31 passed, with every brain tested against a local fake model server, so nothing is billed. A browser check of the settings page saved a custom brain and ran a simulation with it, confirmed the key never appears in the page, and confirmed Claude refuses to save without a key.

Not yet done: testing against a real paid model (needs the operator's key).
