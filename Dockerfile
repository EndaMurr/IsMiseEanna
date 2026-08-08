FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first so this layer is cached across code-only changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY src ./src
COPY README.md ./
RUN uv sync --frozen --no-dev

# The Garmin session token cache lives under $HOME (see garmin_client.py's
# GARMINTOKENS handling) - point it at the mounted volume so a login persists
# across restarts/redeploys instead of needing GARMIN_EMAIL/PASSWORD every time.
ENV HOME=/data
ENV GARMINTOKENS=/data/.garminconnect
ENV MCP_TRANSPORT=streamable-http
ENV MCP_HOST=0.0.0.0
ENV PORT=8000

EXPOSE 8000

CMD ["uv", "run", "ismiseeanna-mcp"]
