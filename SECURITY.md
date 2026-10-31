# Security

Crowdpod runs AI personas and real browsers on behalf of whoever signs in, so a public site has
three kinds of risk. People may misuse the site itself (other users' data, the owner's model key).
They may aim the server's browsers at things they shouldn't reach (the server's own network, third
parties). And they may turn the models against the site through prompt injection. This document lists
every control, why it exists, and where it lives. `backend/tests/test_security.py` attacks each one
(35 tests).

## Threat model

| Asset | Threat | Main controls |
|---|---|---|
| Users' ideas, personas, results | Reading or changing another user's runs (IDOR) | Ownership checks on every run route, 404 for others |
| Accounts | Password guessing, stolen sessions, CSRF, account pre-hijacking | scrypt, lockout, HttpOnly SameSite cookies, Origin check, Google takes over unverified accounts |
| Owner's model API key and settings | Reading or changing them | Admin-only settings, key never sent to the browser |
| Server's network and cloud metadata | SSRF through the browser agents | URL checks before and during every visit, read-only browsing |
| Third-party websites | Using Crowdpod's browsers to spam forms or act on other sites | Read-only browsing (no POST), visit quotas, audit log |
| The owner's money and server | Abuse of the model and of Chromium | Per-user quotas, crowd and visitor caps, body size limit |
| Model behaviour | Prompt injection through ideas or visited pages | Untrusted content fenced as data, closed action set, flagging |

## Controls

### 1. Authentication
- **Passwords:** hashed with scrypt (N=2^14, r=8, p=1, 16-byte salt). Never stored or logged in clear. Unknown emails take the same time to fail as wrong passwords. (`auth.py`)
- **Sessions:** a random 256-bit token in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` on https). Only its SHA-256 hash is stored. Sessions expire after 14 days and end on sign-out.
- **Google sign-in:** OpenID Connect with `state` bound to the browser by a cookie, a `nonce`, and PKCE (S256). The ID token comes straight from Google's token endpoint over TLS. Its audience, issuer, expiry, nonce and `email_verified` are all checked.
- **Existing accounts:** signing in with Google using the email of an existing password account opens that same account. That account's email was never verified, so someone else could have registered it first (pre-account hijacking). The old password, sessions and tokens are therefore ended at that moment, and from then on the account signs in with Google.
- **Lockout:** 5 wrong passwords for an email or an address lock it for a minute. 5 sign-ups per address per hour.

### 2. Personal access tokens (for MCP agents)
- **Format:** `cpat_` plus 256 random bits. The prefix lets secret scanners spot leaks. Only the hash is stored, and the token is shown once.
- **Scope:** a token acts as its user for simulations and results. It can't create or list tokens, open the admin console, or change settings. A leaked token can't escalate.
- **Limits:** at most 10 per user. They can be revoked at any time and stop working while the account is blocked.
- **Public mode:** the machine-local MCP token (`data/mcp-token`) doesn't exist, so the only way in is a user's own token.

### 3. Authorization
- **Runs:** every `/api/runs/{id}/…` route checks the owner. Someone else's run answers 404, so ids can't be probed. Run lists only show your own.
- **Admin:** server settings (model, API key, browser options) and the admin console are for `CROWDPOD_ADMIN_EMAILS` only, from a signed-in browser, never with a token. This is checked before the request body is read. In local mode, anyone signed in from the same machine is an admin.

### 4. Cross-site attacks
- **CSRF:** cookie-authenticated `POST/PUT/DELETE` requests must come from the site's own origin (`CROWDPOD_APP_URL`, `CROWDPOD_ALLOWED_ORIGINS`), on top of `SameSite=Lax`.
- **CORS:** allows only those origins. Other sites can't read responses.
- **Host header:** an allow-list blocks DNS rebinding against the API.
- **Headers:** every API response has `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Content-Security-Policy: default-src 'none'`, and `Strict-Transport-Security` on https. Sign-in responses are `no-store`. The web app gets a strict CSP and the same headers from `frontend/vercel.json`.
- **XSS:** the API only returns JSON. React renders all user and model text as text. No HTML from users or models is ever injected.

### 5. The browser agents (SSRF and abuse of third parties)
- **Before a run:** the URL must be `http(s)` on port 80/443 with no credentials, and its host must resolve only to public addresses. This refuses loopback, private ranges, link-local and cloud metadata (`169.254.169.254`), `.local`, `.internal`, and decimal or short IP forms. (`netguard.py`)
- **During a run:** every request a page makes goes through the same check, re-resolved each time, so redirects and DNS rebinding can't reach the internal network. WebSockets and WebRTC are disabled.
- **Read-only browsing:** on a public site, requests other than GET/HEAD are refused. Visitors can read sites but can't submit forms, sign up, post or buy anything on them.
- **Isolation:** each visitor gets its own browser context: no downloads, no service workers, no permissions. Chromium runs as an unprivileged user in the container.
- **Agent actions:** limited to click / type / scroll / back / done / give_up. Clicks and typing can only target elements on the current page (ids like `e12`, checked twice). Typed text is capped at 200 characters, and the agents are told never to type real personal data. The model can't navigate to arbitrary URLs.

### 6. Prompt injection
- **Visited pages:** page text is fenced between `<<<PAGE … PAGE>>>` and the prompt says it's the website's own text, never instructions, even if it claims to be from Crowdpod.
- **Ideas:** the idea, notes and goals are given to the models as material to judge, not as instructions. The models have no tools, no secrets in their context, and no way to act beyond the closed action set above. A successful injection can at most skew one run's verdict for the user who wrote it.
- **Flagging:** ideas and goals with typical injection phrases ("ignore previous instructions", "system prompt", …) are flagged in the audit log for the owner to review. The run still goes ahead.
- **MCP brief:** the live-visit tool fences page text the same way for the user's own agent.

### 7. Resource limits (public mode)
- **Per user:** 10 simulations an hour, 2 at once, browser visits 5 times a day.
- **Per run:** at most 500 people in a crowd and 3 visitors.
- **Requests:** bodies over 256 KB are refused, and every text field has a length cap.

### 8. Secrets
- **Model key:** stored server-side only (`data/settings.json`, owner-only permissions). The API reports only whether a key is set and its last characters. A saved key is only reused for the provider and address it was entered for.
- **Never in logs:** passwords, tokens and keys are never logged or written to the audit log.
- **Config:** environment variables (Google client secret, SMTP password). Nothing secret is in the repository or the web bundle.

### 9. Monitoring, alerts and blocking
- **What is recorded:** every sign-in (email, method, IP, time) and every guardrail that fires is written to the `audit` table, kept for 90 days. (`audit.py`)
- **Admin console:** `/app/admin/` lists every account (Google or password, last seen, IP, runs, warnings) and the security log, filterable by account.
- **Email alerts:** go to `CROWDPOD_ALERT_EMAILS`, or the admins if that's unset, for:
  - **High severity:** SSRF attempts and cross-site requests.
  - **Bursts:** any account or address with 5 or more warnings in an hour.

  At most one email per account and kind of event every 30 minutes. Mail is sent over SMTP on a background thread.
- **Blocking:** the owner decides; nothing is blocked automatically. Blocking ends the user's sessions, stops their tokens and refuses their sign-ins (password or Google). Unblocking restores access. Admins can't be blocked from the console.

### 10. Supply chain and deployment
- **Dependencies:** pinned in `uv.lock` and `package-lock.json`, with major versions bounded in `pyproject.toml`. `pip-audit` and `npm audit` reported no known vulnerabilities (2026-10-31).
- **Container:** runs as a non-root user, keeps data on a volume, and starts in public mode. Public mode refuses to start with sign-in turned off and warns about a non-https URL or a missing admin list.
- **API docs:** turned off on a public site.

## Setting up email alerts

Any SMTP server works. With Gmail, create an app password (Google Account → Security → 2-Step Verification → App passwords) and set:

```
CROWDPOD_SMTP_HOST=smtp.gmail.com
CROWDPOD_SMTP_PORT=587
CROWDPOD_SMTP_USER=you@gmail.com
CROWDPOD_SMTP_PASSWORD=<the app password>
CROWDPOD_SMTP_FROM=you@gmail.com
CROWDPOD_ADMIN_EMAILS=you@gmail.com
```

Then use **Send a test email** in the admin console.

## Known limits

- **Client IP:** behind a proxy (`CROWDPOD_TRUST_PROXY=1`) the address comes from `X-Forwarded-For`. Anyone who can reach the API directly, bypassing the proxy, can forge it. Restrict the API host to the proxy where the platform allows it. Lockouts also key on the email, and quotas on the account, so a forged address doesn't bypass them.
- **In-memory limits:** lockouts and pending Google sign-ins live in memory, which is fine for one API instance. Several instances would need a shared store.
- **No email verification:** password sign-up doesn't verify email addresses. Google sign-in does, and takes over an unverified account with the same email (above).
- **Injection flagging:** detection is a phrase list. It informs the owner but isn't a filter; the real defence is that model output can't do anything dangerous.

## Reporting a vulnerability

Please open a private security advisory on the GitHub repository rather than a public issue.
