#!/usr/bin/env sh
# One-time setup on macOS or Linux: Python packages, Chromium for the browser agents, and the UI.
set -e
cd "$(dirname "$0")/.."

command -v uv >/dev/null 2>&1 || { echo "Install uv first: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "Install Node.js 20.9 or newer: https://nodejs.org"; exit 1; }
node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit(a>20||(a===20&&b>=9)?0:1)' \
  || { echo "Node.js 20.9 or newer is needed (found $(node -v))"; exit 1; }

echo "Backend: Python 3.11 and the exact package versions from uv.lock"
(cd backend && uv sync --frozen && uv run playwright install chromium)

echo "Frontend: the exact package versions from package-lock.json"
(cd frontend && npm ci)

echo "Done. Start Crowdpod with: scripts/start.sh"
