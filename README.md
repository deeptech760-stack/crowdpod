# Crowdpod

Before you build, ask the crowd. Describe an idea in plain text and Crowdpod:

1. **The crowd.** Hundreds of AI personas, each with a budget, a mood and a reason to say no, judge the idea independently.
2. **The architect.** Writes a BRD and a PRD from the crowd's numbers and quotes: who your real market is, what they'll pay, what to build first, and what to ask real people.
3. **The hands.** A few personas open your website in a real browser, look for what they need, think out loud, and give up when their patience runs out.

It's a simulation. Use it to decide who to talk to first and what to ask them.

## Run it

Requirements: Python 3.11 with [uv](https://docs.astral.sh/uv/), Node.js 20.9+, and Chromium for Playwright.

```sh
# backend: API on http://127.0.0.1:8000
cd backend
uv sync
uv run playwright install chromium   # once, for the hands
uv run crowdpod serve

# frontend: UI on http://localhost:3000 (second terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:3000/app/ and describe an idea.

To serve the UI as static files instead, run `npm run build` and serve `frontend/out/` with any static server.

## Model

By default Crowdpod uses its **offline simulation**. It's rule-based, reproducible, and needs no network or key. That's fine for tests and as a stage backup, but it only reads ideas through keywords. For real results, point it at any OpenAI-compatible endpoint:

```sh
# backend/env.example lists every setting
export CROWDPOD_LLM_PROVIDER=openai
export CROWDPOD_LLM_BASE_URL=...      # the endpoint's /v1 URL
export CROWDPOD_LLM_API_KEY=...       # if the endpoint needs one
export CROWDPOD_LLM_MODEL=...
```

The header of the app shows which provider is active.

## Without the UI

```sh
cd backend
uv run crowdpod run path/to/brief.json --size 500 --url https://your-site.example --hands 5
```

The brief format is `IdeaBrief` in `backend/src/crowdpod/models.py`. `backend/tests/fixtures/brief-fitness.json` is an example.

## Personas

Personas live in `vault/`, an Obsidian vault. Each archetype is one Markdown note: the frontmatter holds the numbers the sampler draws from, and the prose becomes the persona's system prompt. Edit a note and the next run uses it. See `docs/ARCHITECTURE.md`.

## Tests

```sh
cd backend && uv run pytest              # engine, API, real-browser hands
cd frontend && npm run typecheck && npm run lint && npm run build
cd frontend && npx playwright test       # landing page; needs the built site on :3000
```

## License

AGPL-3.0. See `LICENSE` and `NOTICE`.
