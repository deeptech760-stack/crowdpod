# Hosting Crowdpod for other people

Crowdpod has two parts:

| Part | What it is | Where it runs |
|---|---|---|
| Web app (`frontend/`) | A static Next.js export | Vercel, or any static host |
| API (`backend/` + `vault/`) | FastAPI, SQLite, Chromium browser agents, long-running jobs and live updates | A container host with a persistent disk (Render, Railway, Fly.io, a VPS) |

Vercel can't run the API: it needs Chromium, a database file that persists and jobs that run for
minutes. Vercel serves the web app and forwards `/api/*` to the API. The site is then a single
origin: the sign-in cookie stays first-party and the live updates stream through the same address.

```
browser ──> https://crowdpod.vercel.app ──(/api/*)──> https://crowdpod-api.example.com
              static web app (Vercel)                   API container (Dockerfile)
```

## 1. The API

Build the image from the repository root (the `Dockerfile` there):

```
docker build -t crowdpod-api .
docker run -p 8000:8000 -v crowdpod-data:/data --env-file crowdpod.env crowdpod-api
```

On Render, Railway or Fly.io, point a new service at the repository; they detect the Dockerfile.
Attach a persistent volume at `/data` (the database, settings and screenshots live there). The
container listens on `$PORT` when the platform sets it.

`crowdpod.env` (or the platform's environment settings):

```
# the address people open (the Vercel site); Google redirects back here
CROWDPOD_PUBLIC_URL=https://crowdpod.vercel.app
CROWDPOD_APP_URL=https://crowdpod.vercel.app
# the API's own host name, as the proxy sends it
CROWDPOD_ALLOWED_HOSTS=crowdpod-api.example.com
# you: opens the admin console and the model settings, gets security alerts
CROWDPOD_ADMIN_EMAILS=you@gmail.com
# Google sign-in (step 3)
CROWDPOD_GOOGLE_CLIENT_ID=...
CROWDPOD_GOOGLE_CLIENT_SECRET=...
# security alerts by email (see SECURITY.md)
CROWDPOD_SMTP_HOST=smtp.gmail.com
CROWDPOD_SMTP_USER=you@gmail.com
CROWDPOD_SMTP_PASSWORD=...
CROWDPOD_SMTP_FROM=you@gmail.com
# where agents install the MCP server from (your fork)
CROWDPOD_SOURCE_URL=https://github.com/you/crowdpod
```

The image already sets `CROWDPOD_MODE=public` (strict limits, admin-only settings, no machine
token, browsers can't reach private networks) and `CROWDPOD_TRUST_PROXY=1`.

Check it: `https://crowdpod-api.example.com/api/health` answers `{"ok": true}`.

## 2. The web app on Vercel

1. In `frontend/vercel.json`, replace `YOUR-API-HOST` with the API's host
   (`crowdpod-api.example.com`).
2. Create a Vercel project from the repository with **Root Directory** set to `frontend`.
3. Deploy. On any host other than localhost the web app calls `/api/...` on its own origin, and
   Vercel forwards it. No environment variable is needed. `vercel.json` also adds the security headers (CSP, HSTS, frame and content-type rules).

## 3. Google sign-in

In Google Cloud Console → APIs & Services → Credentials → Create OAuth client ID (Web application):

- Authorised JavaScript origin: `https://crowdpod.vercel.app`
- Authorised redirect URI: `https://crowdpod.vercel.app/api/auth/google/callback`

Put the client id and secret in the API's environment and restart it. The sign-in page's
**Continue with Google** button turns on by itself. While the OAuth consent screen is in
"Testing", only the test users you list there can sign in. Publish it to let anyone in. The basic
`openid email profile` scopes don't need Google's verification review.

## 4. First sign-in and settings

1. Open the site and sign in with the email in `CROWDPOD_ADMIN_EMAILS`. **Admin** appears in the
   header.
2. **Settings:** choose the model that plays the crowd for everyone, with your API key, or keep the
   offline simulation. The key stays on the API server.
3. **Admin:** **Send a test email** to check alerts.

## 5. How visitors use it

- **On the website:** sign up (email or Google), enter an idea, watch the crowd and read the
  BRD/PRD.
- **With their own agent:**
  1. Settings → **Create token**, then copy the setup for Claude Code, Codex, Claude Desktop or
     OpenCode. The token is filled in. It needs [uv](https://docs.astral.sh/uv/).
  2. Run the Chromium install command shown there once, for live browser visits.
  3. Ask the agent to test an idea. The simulations run on your site (your model); live visits
     run in Chromium on the visitor's computer, driven by their own agent.

## Updating

- **API:** redeploy the container. The database migrates itself on start.
- **Web app:** Vercel redeploys on push.
- **Backups:** back up the `/data` volume (`crowdpod.sqlite3` holds accounts, runs and the audit log).
