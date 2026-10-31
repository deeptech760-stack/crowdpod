# Crowdpod architecture

Crowdpod tests a product idea against a crowd of simulated people before you build it. The founder describes any idea in plain text. The crowd reacts, an architect writes a BRD and a PRD from those reactions, and (optionally) the crowd's "hands" use a real website in a browser. The pitch calls these three parts **a crowd, an architect and hands**.

This document covers how they work, how the backend and UI fit together, and what is still to do.

## 1. What a run does

| Pitch promise | What the code does |
|---|---|
| "Thousands of AI personas, each with a budget, a mood and a reason to say no" | Samples a crowd of 1 to 5,000 personas from handwritten archetypes. Each persona judges the idea and returns a verdict, a price they would pay, a quote, their biggest objection and the feature they'd pay for. |
| "Crowdpod tells you who your real market is" | Plain statistics over the reactions: adoption and willingness to pay for each segment, plus the most common objections and requests. The segment that would bring in the most paying customers is named, and the headline says when that differs from who the founder guessed. |
| "An architect writes your BRD and PRD" | Turns those statistics and a few chosen quotes into two Markdown documents. Both end with questions to put to real people. |
| "Hands: every persona opens a real browser" | Gives a handful of personas a real Chromium session through Playwright. Each one looks at the page, thinks out loud, clicks and scrolls, and either reaches their goal or gives up when patience runs out. Every step is saved with a screenshot. |
| "Point the same crowd at your competitor's website" | The same Hands run with another URL. *(A side-by-side comparison view is still to do.)* |
| Works on stage without a network | A built-in offline provider gives reproducible results with no model, key or network. The UI labels runs that used it. |

## 2. Main design decisions

### 2.1 Reuse the upstream swarm engine's parts, not its whole runtime

Crowdpod includes code adapted from an open-source swarm-simulation engine. It's listed in `NOTICE`, which AGPL-3.0 requires us to keep. That engine runs thousands of agents on simulated social networks to forecast public opinion, using a knowledge graph and a hosted memory service. We copied the parts that fit and left out the runtime:

| Taken from upstream | Where it lives now |
|---|---|
| LLM client: JSON-mode request, fallback when an endpoint rejects `response_format`, response parsing that refuses truncated or doubled JSON, GPT-5 parameter handling | `backend/src/crowdpod/llm/openai_compat.py` |
| JSON cleaning and parsing, and coercion of odd model output (dicts or lists where a string was expected) | `backend/src/crowdpod/llm/json_utils.py` |
| Async retry with exponential backoff | `backend/src/crowdpod/retry.py` |
| Persona schema: identity fields (name, age, gender, MBTI, profession) kept apart from behaviour fields (mood, sentiment bias, activity) | `backend/src/crowdpod/models.py` (`Persona`) |

Why not run the whole engine:

- **It answers a different question.** It simulates people influencing each other over many rounds. Crowdpod's first question needs independent judgements. The pitch's Wisdom of Crowds argument depends on that independence: the median of independent guesses is accurate, and herding ruins it. A word-of-mouth round is a later step (section 9).
- **No spending.** Its memory runs on a hosted service that needs an API key, and its recommended model is paid. Crowdpod has to run for free.
- **Size.** A graph database, a memory service and a social-platform simulator are a lot to keep alive for a three-minute demo.

From the UXAgent paper (CHI EA 2025, arXiv 2504.09407) we took the design of the Hands:

- Observe the page as a simplified list of visible elements with stable IDs.
- Record think-aloud alongside the action trace.
- Allow interviews after a session.

Both sources agree that simulated users help you decide what to ask real users but don't replace them. The UI and every document say so.

### 2.2 Personas are Markdown notes in an Obsidian vault

```
vault/                         a normal Obsidian vault
  personas/archetypes/*.md     one note per archetype: YAML frontmatter + prose
  templates/persona-system.md  system prompt for a single persona (Hands, interviews)
  templates/crowd-batch.md     prompt for judging a batch of personas in one call
  templates/hands-step.md      prompt for one browser step
  templates/architect.md       BRD/PRD prompt
  runs/                        reserved for exported runs
```

- The **frontmatter** holds the values the code samples and computes with: weight, ranges for age, budget, patience, tech comfort, price sensitivity and optimism, plus moods, devices, interests, pains, objections, dealbreakers, goals on a website, must-haves and sample voice lines.
- The **prose body** (`## Who I am`, `## How I decide`, `## Reasons I say no`, `## How I talk`) is placed into `persona-system.md` to build that persona's system prompt.
- Anyone can edit a persona in Obsidian without touching code. Changes show up as normal git diffs, and `[[links]]` show how the crowd is made up in the graph view.
- **A crowd of thousands is never written out as thousands of files.** A persona is the result of `(archetype, run seed, index)`. The sampler draws its exact values from the archetype's ranges using a stable hash, so the same seed always gives the same crowd. Sampled personas are stored in SQLite with their run.

The current 8 archetypes come from the pitch: mother, corporate worker, auto driver, CEO, athlete, househusband, dancer and college student. All are set in Bengaluru, with budgets in ₹.

### 2.3 The model is a plug-in; the offline provider is the default

```python
class LLMProvider(ABC):
    async def complete_json(self, system, user, schema, *, task, context) -> BaseModel
    async def complete_text(self, system, user, *, task, context) -> str
```

`task` is one of `crowd`, `architect`, `hands` or `interview`. A real model reads the prompts. The offline provider reads the structured `context` behind those prompts.

- **`mock`, the offline provider (default).** It's deterministic and rule-based:
  - A reaction comes from how well the idea's words match the persona's interests and pains, the price compared with their budget, dealbreaker phrases, and per-person noise.
  - Quotes come from the archetype's voice lines.
  - In the browser it clicks links that match its goal words, scrolls otherwise, and gives up when out of patience.
  - **Limit:** it only understands ideas through keywords. That's fine for tests and as a stage backup, but it isn't a simulation of judgement. Any idea outside the archetypes' vocabulary gets flat results.
- **`anthropic`, Claude** (`llm/anthropic_provider.py`), through the official `anthropic` SDK with the user's API key:
  - JSON answers come back through structured outputs (`messages.parse` with the Pydantic schema), so they are checked against the schema;
  - an effort level is set per brain (default medium);
  - server-side refusal fallback (`fallbacks: "default"`) is turned on;
  - refusals and truncated replies raise errors, which the crowd runner catches (see below).
- **`openai`, any OpenAI-compatible endpoint** (`llm/openai_compat.py`): OpenAI, OpenRouter, Groq, Together, or a local LM Studio or Ollama server.

Which brain to use, and whether it costs anything, is the operator's decision. It's chosen on the **Settings** page and saved to `data/settings.json` (`runtime.py`); environment variables only supply defaults. Each run takes a snapshot of the settings when it's queued and builds its own model client, so changing settings mid-run doesn't affect a running simulation.

Model output is checked against Pydantic schemas. A reply that fails is retried once with the error attached. If a whole crowd batch fails, that batch falls back to the offline provider, and the run emits `crowd.degraded` so the UI can say so.

### 2.4 Thousands of personas, few model calls

- **Batched crowd calls.** One call judges up to 20 personas (`CROWDPOD_CROWD_BATCH_SIZE`), each sent as a short card. 1,000 personas take 50 calls, run in parallel up to `CROWDPOD_LLM_CONCURRENCY`.
- **Statistics without the model.** Segment tables, medians, adoption and objection counts are plain Python.
- **Hands for a few.** Browser sessions go to K personas, 5 by default. The user can choose which segments go first. The rest are picked automatically: the strongest segment, the weakest, then by score, preferring undecided people.
- **Patience in simulated seconds.** Each action costs a person a few seconds, more for people less at ease with tech. That way a slow model doesn't make a persona "impatient".

## 2.5 Research and generated audiences (stage 1)

A fixed set of archetypes can't judge every idea. Taking the upstream engine's approach of deriving personas from source material, each run (with `audience: "generated"`, the default) starts by researching the market (`audience.py`):

1. **Research.** `provider.research()` writes a market brief.
   - Claude uses Anthropic's server-side web search tool and returns its sources (`grounded: true`).
   - OpenAI-compatible models answer from their own knowledge (`grounded: false`, shown in the UI).
   - The founder's own notes (`context_notes`) are added to the prompt.
2. **Digest.** A structured call turns the brief into a summary, facts, price points and buyer segments (`Research`).
3. **Design.** A structured call returns 3–10 `GeneratedPersona`s, each with:
   - its market share;
   - realistic **purchase** and **monthly** budgets in ₹;
   - objections and must-haves;
   - quotes;
   - the evidence it's based on.

   `to_archetype` clamps every value to sane bounds and drops unknown devices. Each persona is saved as an Obsidian note under `vault/personas/generated/<idea>-<run>/` (git-ignored, since it describes the user's idea).
4. The run then uses `vault.extended(generated)`. The crowd is weighted by market share, and with `audience: "both"`, half comes from the built-in archetypes.

**Callers can bring their own audience.** A caller can send `provided_audience` and `provided_research`; for example, an MCP client that did its own web search with its own subscription. These skip steps 1–3 and work even with the offline brain.

**Fallback.** If the brain can't research (the offline brain), the run falls back to the built-in archetypes and emits `audience.skipped` with the reason.

**Price basis.** Prices are compared like with like:
- a one-time price is weighed against the persona's `purchase_budget`;
- anything recurring is weighed against `budget_month`.

`CrowdSummary.price_unit` says which basis was used, and amounts use Indian digit grouping.

## 3. System overview

```
┌──────────────── frontend/ (Next.js 16, static export) ─────────────────┐
│  /            landing page (rebranded pre-built UI)                     │
│  /login       sign-in screen (front-end only for now)                   │
│  /app         new simulation form + recent runs                         │
│  /app/run?id  live view: crowd wall, signal, BRD/PRD, hands, interviews │
└──────────────┬──────────────────────────────────▲──────────────────────┘
        REST (JSON)                       SSE: run events (replayable)
┌──────────────▼──────────────────────────────────┴──────────────────────┐
│ backend/ FastAPI (crowdpod.api) — RunManager starts runs as asyncio tasks│
├─────────────────────────────────────────────────────────────────────────┤
│ Pipeline: assemble crowd → reactions → aggregate → architect → hands    │
├──────────────┬────────────────┬──────────────────┬──────────────────────┤
│ Vault (md)   │ CrowdSampler   │ LLMProvider       │ BrowserDriver        │
│ vault/       │ seeded         │ mock | openai     │ Playwright Chromium  │
├──────────────┴────────────────┴──────────────────┴──────────────────────┤
│ SQLite data/crowdpod.sqlite3 · artifacts data/artifacts/<run>/           │
│ (brd.md, prd.md, report.json, shots/*.png)                               │
└─────────────────────────────────────────────────────────────────────────┘
```

**How the UI gets live updates.** Every event a run emits is saved with a sequence number and pushed to subscribers. `GET /api/runs/{id}/events` first sends the saved events, then the live ones, and closes after `run.finished` or `run.failed`. The run page builds its whole state from this one stream. Reloading a finished run therefore replays it exactly, and a viewer who joins mid-run catches up. Reactions are buffered in the browser and drawn in batches every 120 ms, so a crowd of 2,000 doesn't stall the page.

## 4. Data model (`backend/src/crowdpod/models.py`)

- **IdeaBrief**: `name`, `pitch`, `category`, `price`, `currency`, `price_period` (`month | year | one_time | free`), `target_hint`, `url`, `competitor_url`. `monthly_price` normalises the price so it can be compared with budgets.
- **Archetype**: the note's frontmatter and body, as described in 2.2.
- **Persona**: `id` (`<run>-<archetype>-<n>`), `archetype_id`, `seed`, identity fields, and behaviour fields (`mood`, `device`, `budget_month`, `patience_seconds`, `tech_comfort`, `price_sensitivity`, `sentiment_bias`).
- **Reaction**: `verdict` (`adopt | maybe | reject`), `willingness_to_pay` (₹/month), `sentiment` (−1 to 1), `quote`, `top_objection`, `must_have`, `reasoning` and `provider`.
- **CrowdSummary**:
  - adoption and interest rates
  - `median_wtp` over everyone, and `median_wtp_interested` over people who didn't reject
  - `price_fit_rate`
  - `segments[]` (`SegmentStats`)
  - `best_segment` and `worst_segment`
  - top objections and must-haves
  - `headline`

  The best segment is the one with the largest share of the whole crowd that adopts and would pay at least the asking price. It must have at least 5 people.
- **HandsSession / HandsStep**: outcome (`success | gave_up | step_limit | error`), simulated seconds, and per step the thought, action, target, URL, screenshot and any error.
- **RunEvent**: `seq`, `run_id`, `type` and `data`. Types are `run.started`, `crowd.assembled`, `reaction`, `crowd.degraded`, `stage.done`, `summary`, `docs`, `hands.started`, `hands.step`, `hands.session`, `run.finished` and `run.failed`.

## 5. API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | status, active provider, archetype count |
| GET | `/api/archetypes` | archetypes from the vault |
| POST | `/api/runs` | start a run: `{brief, crowd_size, mix?, seed?, hands?: {url, personas, max_steps?, archetypes?}}` → `202 {run_id}` |
| GET | `/api/runs` | recent runs |
| GET | `/api/runs/{id}` | status, request and summary |
| GET | `/api/runs/{id}/events` | SSE stream (saved events, then live) |
| GET | `/api/runs/{id}/reactions` | paged reactions; filter by `segment` and `verdict` |
| GET | `/api/runs/{id}/docs` | BRD and PRD Markdown |
| GET | `/api/runs/{id}/hands` | browser sessions with steps |
| GET | `/api/runs/{id}/artifacts/{path}` | screenshots (path traversal blocked) |
| POST | `/api/runs/{id}/personas/{pid}/interview` | ask one persona a question; they answer in character |
| GET / PUT | `/api/settings` | the brain and browser settings; the key is never returned, only `has_key` and the last 4 characters |
| POST | `/api/settings/test` | one tiny JSON request to check a model, without saving |
| POST | `/api/settings/models` | model names the endpoint offers |
| GET | `/api/settings/mcp` | copy-paste MCP setup for Claude Code, Codex and Claude Desktop |

CORS allows any `localhost` or `127.0.0.1` origin, so the UI dev server and the static build can both call the API.

### Security

- **Keys.**
  - Stored only in `data/settings.json`, written with owner-only permissions and git-ignored.
  - Never returned by the API.
  - Removed from any error text before it's returned.
  - A saved key is reused only when the provider *and* the address are unchanged, so it can never be sent to a different service than the one it was entered for.
- **Who can change settings.** The settings endpoints answer only requests from the same machine (loopback). Every endpoint rejects unexpected `Host` headers (`TrustedHostMiddleware`), which blocks DNS-rebinding attacks from other websites; extra hostnames go in `CROWDPOD_ALLOWED_HOSTS`. CORS only allows localhost origins, so other sites can't read responses.
- **Browsing.**
  - Agents visit only `http(s)` URLs.
  - Page text reaches the model fenced as untrusted content with an explicit "not instructions" note.
  - The action set is fixed: click, type, scroll, back, done, give up.
  - Personas are told never to type personal or payment data.
- **MCP.**
  - Runs over stdio, so only the client that launched it can call it.
  - At most 3 live visits at once and 40 steps each.
  - Visit logs are saved under `data/mcp-visits/`.

## 6a. MCP server (`crowdpod mcp`)

Lets Claude Code, Codex, Claude Desktop or any MCP client use Crowdpod with its own sign-in and subscription. Crowdpod never sees that login: using a Claude.ai or ChatGPT login inside a third-party app isn't permitted, so this is the supported way to bring those tools in. It has two groups of tools:

- **Crowd runs** go through the running API, so they also appear in the web UI: `list_personas`, `start_simulation`, `get_results`, `get_documents`, `get_browser_sessions`, `interview_persona`.
- **Live visits** put the client's own model in charge of one persona's browser:
  - `visit_as_persona` returns the persona's full system prompt, the page as text and a screenshot;
  - the client then chooses each `browser_step`;
  - `end_visit` closes the browser and records the outcome.

  This is the "a real model drives the browser" mode, without Crowdpod needing any API key.

## 6. Frontend (`frontend/`)

The frontend started as a pre-built landing page from a teammate's repository. Its components, animations (GSAP, Lenis, Motion), design tokens and fonts are kept. The changes:

- The brand is now Crowdpod, and all copy follows the pitch: friends lie to be nice, a crowd, an architect, hands, Wisdom of Crowds, competitor mode.
- The voice and multilingual feature (the Sarvam AI section, mic input and language panels) is gone. Input is text only.
- The `/app` pages are new and talk to the API through `lib/api.ts`. `NEXT_PUBLIC_API_URL` defaults to `http://127.0.0.1:8000`.
- The app's internal links use full page loads. The static export writes nested-route payloads where the client router doesn't look for them, so client-side navigation would fail.
- The login screen is still front-end only. There are no accounts yet.

## 7. Layout

```
crowdpod/
  AGENTS.md            notes for anyone (human or tool) working here
  README.md            how to run it
  LICENSE, NOTICE      AGPL-3.0, upstream attribution
  docs/                ARCHITECTURE.md (this file), PROGRESS.md
  vault/               Obsidian vault: archetypes and prompt templates
  backend/             Python 3.11, uv, FastAPI, Pydantic 2, Playwright, SQLite
    src/crowdpod/      models, vault, sampler, llm/, crowd, aggregate, architect,
                       hands/, store, events, pipeline, api, cli
    tests/             pytest; fixtures/ holds a test brief and a test website
  frontend/            Next.js 16 app (landing, login, /app)
  data/                runtime database and artifacts (git-ignored)
```

## 8. Honesty and limits

- Every result is a **simulation**. The run page, the BRD and the PRD all say so, and both documents end with questions for real interviews.
- Model personas lean towards stereotypes and towards being agreeable. Countermeasures:
  - archetype notes that spell out reasons to say no and dealbreakers
  - price sensitivity and optimism drawn per persona
  - a batch prompt that tells the model rejection is normal
- The offline provider is a keyword heuristic. A real model is needed for real ideas.

## 9. Next steps

1. **Run with a real model** through an OpenAI-compatible endpoint the operator chooses, then tune the prompts and batch size against real output.
2. **Generate an audience for each idea**, following the upstream engine's approach of deriving personas from the seed material. A model reads the brief and proposes 3 to 5 extra archetypes in the same schema (for example procurement managers for a B2B idea). These are saved to `vault/personas/generated/<run>/` and mixed into the crowd. The fixed 8 archetypes cover consumers in India; arbitrary ideas need this.
3. **Word-of-mouth round** (the upstream engine's core idea): after the independent verdicts, personas see a few others' quotes and may change their minds. The run reports how far the idea spreads, kept separate from the independent result.
4. **Competitor comparison**: one form field, two Hands runs with the same seed, and a side-by-side view of success rate, time to goal and where people gave up.
5. Export a run to the vault (`vault/runs/<id>/`) and keep recorded runs for a stage demo.
6. Real accounts behind `/login` if the app is hosted for others. With AGPL, hosting it publicly means offering the source.
