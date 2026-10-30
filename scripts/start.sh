#!/usr/bin/env sh
# Starts the API (port 8000) and the UI (port 3000). Ctrl+C stops both.
cd "$(dirname "$0")/.."
(cd backend && uv run crowdpod serve) &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT INT TERM
echo "Open http://localhost:3000/app/"
cd frontend && npm run dev
