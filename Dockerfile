# The Crowdpod API: FastAPI, the crowd simulation and the Chromium browser agents.
# The web app is a static site hosted separately (Vercel); see docs/DEPLOY.md.
FROM python:3.11-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PLAYWRIGHT_BROWSERS_PATH=/opt/browsers PATH="/app/backend/.venv/bin:$PATH"
WORKDIR /app

# dependencies first, so code changes don't reinstall them
COPY backend/pyproject.toml backend/uv.lock backend/.python-version backend/
RUN cd backend && uv sync --frozen --no-dev --no-install-project
RUN cd backend && uv run --no-sync playwright install --with-deps chromium

COPY backend/src backend/src
RUN cd backend && uv sync --frozen --no-dev
COPY vault vault
COPY NOTICE LICENSE ./

# run as an unprivileged user; /data holds the database and screenshots (mount a volume there)
RUN useradd --create-home --uid 10001 crowdpod && mkdir -p /data && chown crowdpod /data
USER crowdpod

ENV CROWDPOD_MODE=public CROWDPOD_DATA_DIR=/data CROWDPOD_VAULT_DIR=/app/vault CROWDPOD_TRUST_PROXY=1
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000'))"
CMD ["sh", "-c", "exec crowdpod serve --host 0.0.0.0 --port ${PORT:-8000}"]
