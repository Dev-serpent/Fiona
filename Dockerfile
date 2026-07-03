# ── Stage 1: Base ──────────────────────────────────────────────────────────
# Installs core dependencies only (no dev/test extras).
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Copy project metadata first for Docker layer caching.
COPY pyproject.toml README.md ./

# Install the HomeBackend service and its optional MQTT dependencies.
# The `home-backend` extra pulls in aiohttp + paho-mqtt.
RUN pip install --no-cache-dir -e ".[home-backend]"

# ── Stage 2: Runtime ──────────────────────────────────────────────────────
FROM base AS runtime

COPY . .

# Default command: start the HomeBackend service.
# Override CMD to run different entrypoints.
CMD ["python", "-m", "HomeBackend"]

# Health check — the /api/health endpoint returns 200 when alive.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/health')"
