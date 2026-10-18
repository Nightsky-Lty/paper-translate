FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS python-dependencies
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy
ARG PYTHON_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --index-url "$PYTHON_INDEX_URL" uv==0.7.6
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file /tmp/requirements.txt && \
    uv venv /app/.venv && \
    uv pip sync --python /app/.venv/bin/python --index-url "$PYTHON_INDEX_URL" --require-hashes /tmp/requirements.txt

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PAPER_TRANSLATE_DATA=/app/data PAPER_TRANSLATE_LIBRARY=/library
WORKDIR /app
RUN useradd --create-home --uid 1000 paper && \
    mkdir -p /app/data /library && chown paper:paper /app/data
COPY --from=python-dependencies /app/.venv /app/.venv
COPY --from=frontend /build/frontend/dist /app/frontend/dist
COPY server/ /app/server/
COPY scripts/create_access_password.py scripts/parse_mineru4.py /app/scripts/
USER paper
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["/app/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=3).read()"]
# The port is published to host loopback only; Caddy is the sole public entrypoint.
CMD ["/app/.venv/bin/python", "-m", "uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8765", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
