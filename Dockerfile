FROM python:3.11-slim

# uv for fast, reproducible installs from uv.lock (pinned to match the lockfile tooling)
COPY --from=ghcr.io/astral-sh/uv:0.11.30 /uv /uvx /usr/local/bin/

# Keep the project venv OUTSIDE /app so a dev bind-mount over /app can't hide it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Install dependencies first (Docker layer cache: only re-runs when deps change).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY . .

# Identifies the image to Kamal, which refuses to deploy an image whose
# service label does not match the service it is deploying.
LABEL service="backend"

# Drop root. uid 1000 is what the host directory bind-mounted at UPLOAD_DIR
# must be owned by, so the projects app can still write uploads.
RUN useradd -u 1000 -m appuser \
    && chown -R appuser:appuser /app /opt/venv
USER appuser
