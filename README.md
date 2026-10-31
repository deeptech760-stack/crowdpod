# Crowdpod

Before you build, ask the crowd. Describe an idea in plain text and Crowdpod:

1. **The crowd.** Hundreds of AI personas, each with a budget, a mood and a reason to say no, judge the idea independently.
2. **The architect.** Writes a BRD and a PRD from the crowd's numbers and quotes: who your real market is, what they'll pay, what to build first, and what to ask real people.
3. **The hands.** A few personas open your website in a real browser, look for what they need, think out loud, and give up when their patience runs out.

It's a simulation. Use it to decide who to talk to first and what to ask them.

## Set up

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) and [Node.js](https://nodejs.org) 20.9 or newer. uv installs the right Python (3.11) by itself.

```sh
# macOS / Linux
scripts/setup.sh
scripts/start.sh

# Windows (PowerShell)
.\scripts\setup.ps1
.\scripts\start.ps1
```

Setup installs the exact versions pinned in `backend/uv.lock` and `frontend/package-lock.json`, plus the Chromium the browser agents use, so everyone gets the same environment. Then open http://localhost:3000/app/.

If you prefer pip, `backend/requirements.txt` lists the same pinned packages; install them into a Python 3.11 virtual environment, then run `pip install -e backend` and `playwright install chromium`.

## A crowd made for each idea

Every run starts by researching the idea's market and designing the people who matter for it, rather than reusing a fixed cast. For a foldable phone, that means Apple upgraders, Samsung Fold owners, creative professionals and EMI buyers, each with realistic budgets in ₹:
- **Purchase budgets** for one-off purchases like a phone.
- **Monthly budgets** for subscriptions.

How the research happens:
- **Claude:** searches the web live and cites its sources.
- **Other models:** work from what they already know, and the run says so.
- **Claude Code or Codex through MCP:** your own agent can do the research and hand Crowdpod the personas, so no API key is needed.
- **Offline brain:** can't research, so it uses the ten built-in personas.

Generated personas are saved as notes in `vault/personas/generated/<idea>-<run>/`, which git ignores. You can read and edit them in Obsidian.

## Choose the brain

Open **Settings** in the app. The brain plays every persona: their verdicts, their thoughts and every click on a website.

| Brain | What you need |
|---|---|
| Offline simulation (default) | Nothing. Free and works without internet, but rule-based: it reads ideas by keywords. Fine for rehearsals and tests, not for real verdicts. |
| Claude | An Anthropic API key. Defaults to Claude Opus 5.5; Sonnet 5.5 and Haiku 5.5 are faster and cheaper. |
| Any OpenAI-compatible model | An address and usually a key: OpenAI, OpenRouter, Groq, Together, or a model on your own computer through LM Studio or Ollama (no key). |

**Test connection** checks the model before you save. Each run remembers which brain it used, and the header shows the current one.

## Use it from Claude Code, Codex, Claude Desktop or OpenCode (MCP)

Crowdpod includes an MCP server, so your own AI tool can use it with its own sign-in and subscription. Crowdpod never sees that login. **Settings → MCP** shows the exact command for your computer, for example:

```sh
claude mcp add crowdpod -- uv --directory /path/to/crowdpod/backend run crowdpod mcp
```

Keep `scripts/start` running. Your agent can then:
- run crowd simulations and read the results, BRD and PRD;
- interview personas;
- play a persona itself in a real Chromium window, seeing a screenshot of each page and choosing every click.

On a hosted Crowdpod, create an access token in **Settings → Access tokens**; the setup shown there then installs the MCP server with `uvx` and points it at the site.

## Host it for other people

The web app goes on Vercel and the API in a container (`Dockerfile`), with an admin console for the owner, email alerts and per-user limits. See [docs/DEPLOY.md](docs/DEPLOY.md).

## Sign-in

Crowdpod requires an account. Open http://127.0.0.1:3000/login/ and choose **Create an account** (email and password, at least 8 characters). Passwords are stored as scrypt hashes, sessions live in an HttpOnly cookie for 14 days, and 5 failed attempts lock that email and address for a minute. Password reset by email isn't available, because a self-hosted Crowdpod has no mail service.

### Google sign-in (optional)

The **Continue with Google** button switches on once the server has a Google OAuth client. Only you can create one; it's free:

1. In the [Google Cloud console](https://console.cloud.google.com/apis/credentials), set up the **OAuth consent screen** (External, and add yourself as a test user).
2. Go to **Credentials → Create credentials → OAuth client ID → Web application**.
3. Under **Authorized redirect URIs**, add `http://127.0.0.1:8000/api/auth/google/callback`.
4. Set these two values, then restart the server:
   ```sh
   export CROWDPOD_GOOGLE_CLIENT_ID=...apps.googleusercontent.com
   export CROWDPOD_GOOGLE_CLIENT_SECRET=...
   ```
5. Open the app at `http://127.0.0.1:3000`, the same host as the redirect address, and use **Continue with Google**.

If you serve Crowdpod under another address, set `CROWDPOD_PUBLIC_URL` (the API) and `CROWDPOD_APP_URL` (the web app) and register the matching redirect URI. A Google account whose verified email matches an existing account signs in to that account. Because a password account's email is never verified, that account's password, sessions and tokens end at that moment and it signs in with Google from then on (this stops someone registering your email before you).

## Security

[SECURITY.md](SECURITY.md) lists every control, the threat it answers and the tests that attack it. In short, on your own computer:

- **API keys** stay on the computer running Crowdpod, in `data/settings.json`, which is created readable by its owner only and ignored by git. They're never sent back to the browser, are removed from error messages, and are only reused for the provider and address they were entered for.
- **The API** listens on `127.0.0.1` only. Model settings can only be read or changed from that machine, and requests with an unexpected `Host` header are refused, which blocks DNS-rebinding attacks from other websites. To reach it under another hostname, list it in `CROWDPOD_ALLOWED_HOSTS`.
- **Browser agents** only visit `http(s)` addresses. Website text goes to the model fenced off as untrusted content, and personas are told not to type personal data. The MCP server runs over stdio, so only the tool that started it can talk to it.

## Without the UI

```sh
cd backend
uv run crowdpod run path/to/brief.json --size 500 --url https://your-site.example --hands 5
```

The brief format is `IdeaBrief` in `backend/src/crowdpod/models.py`. `backend/tests/fixtures/brief-fitness.json` is an example. Environment variables in `backend/env.example` set the defaults until you save something in Settings.

## Personas

Personas live in `vault/`, an Obsidian vault. Each archetype is one Markdown note: the frontmatter holds the numbers the sampler draws from, and the prose becomes the persona's system prompt. Edit a note and the next run uses it. See `docs/ARCHITECTURE.md`.

## Tests

```sh
cd backend && uv run pytest              # engine, API, every brain (against a local fake), MCP, security, real-browser hands
cd frontend && npm run typecheck && npm run lint && npm run build
cd frontend && npx playwright test       # landing page; needs the built site on :3000
```

The tests never call a paid model: a local fake server answers in both the Anthropic and OpenAI formats.

## License

AGPL-3.0. See `LICENSE` and `NOTICE`.
