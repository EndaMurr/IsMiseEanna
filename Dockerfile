FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first so this layer is cached across code-only changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY README.md ./
RUN uv sync --frozen --no-dev

# Run as a dedicated, unprivileged user rather than root - this container is
# directly reachable from the internet (via Fly's proxy) as an OAuth
# resource server. /data is the mounted volume (see fly.toml); create it
# with the right ownership now so a fresh volume inherits it on first mount.
RUN useradd --system --create-home --home-dir /data appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data /app

# The Garmin session token cache lives under $HOME (see garmin_client.py's
# GARMINTOKENS handling) - point it at the mounted volume so a login persists
# across restarts/redeploys instead of needing GARMIN_EMAIL/PASSWORD every time.
ENV HOME=/data
ENV GARMINTOKENS=/data/.garminconnect
ENV MCP_TRANSPORT=streamable-http
ENV MCP_HOST=0.0.0.0
ENV PORT=8000

USER appuser

EXPOSE 8000

CMD ["uv", "run", "ismiseeanna-mcp"]
