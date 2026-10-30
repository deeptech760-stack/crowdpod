# Crowdpod frontend

The UI started from the [Brd](https://github.com/Hardik34616/Brd) landing page and was adapted for Crowdpod.

The Crowdpod UI has three parts. The landing page (`/`) and the sign-in screen (`/login`) are front-end only. The workspace (`/app`, `/app/run`) talks to the Crowdpod API.

## Run locally

Requires Node.js 20.9 or newer, and the backend running (see `../README.md`).

```sh
npm install
npm run dev
```

Open http://localhost:3000. The API address defaults to `http://127.0.0.1:8000`. To use another, set `NEXT_PUBLIC_API_URL` before `npm run dev` or `npm run build`.

On Windows PowerShell, use `npm.cmd` if your execution policy blocks `npm.ps1`.

## Checks

```sh
npm run typecheck
npm run lint
npm run build
npm run test:e2e   # landing page; expects the site on http://127.0.0.1:3000
```

## Design and implementation

- Next.js App Router with a static export to `out/`, TypeScript, Tailwind CSS, and self-hosted Instrument Serif and Manrope fonts.
- **Landing page.** GSAP ScrollTrigger runs the desktop scroll story, Motion handles state-driven demo transitions, and CSS handles the ambient motion. Mobile and reduced-motion visitors get a sequential story. The demos on the landing page are illustrative and run in the browser only.
- **Workspace.** `lib/api.ts` is the typed API client. The run page builds its state from the server's event stream (`/api/runs/{id}/events`), so it updates live and replays a finished run on reload. Its styles are in `app/app/app.css` and use the same tokens as `app/globals.css`.
- Input is text only. No microphone or audio is used.

## Organization

- `components/landing/`: landing sections and shared primitives (`UI.tsx`).
- `components/auth/`: the sign-in screen.
- `components/app/`: the workspace (`Workspace`, `RunView`, `CrowdWall`, `SummaryPanel`, `DocsPanel`, `HandsPanel`).
- `components/animations/MotionProvider.tsx`: global scroll integration.
