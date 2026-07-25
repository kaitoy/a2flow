# Backend image: FastAPI + Google ADK agent served by uvicorn on port 8000.
# Python version matches backend/.python-version.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# curl is used by compose.yml's backend healthcheck to probe /health.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Node.js, so stdio MCP servers registered as npm packages can be launched with
# `npx`. Copied from the official image rather than installed from apt because
# bookworm still ships the end-of-life Node 18. (`uvx` needs nothing extra: the
# base image already provides uv.)
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Install dependencies first so source changes do not invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

# Run as non-root. /var/lib/a2flow/skills is pre-created and chowned here
# because it's the mount point for compose.yml's `skills` named volume — Docker
# seeds a new named volume's ownership from the image path it overlays, so this
# is what makes the first skill clone (as `app`) succeed instead of hitting a
# root-owned mount point.
#
# /app/.npm is npx's package cache, written the first time a stdio MCP server
# registered as an npm package is launched. It is derived from HOME rather than
# from NPM_CONFIG_CACHE on purpose: the MCP SDK spawns stdio servers with only
# the variables `get_default_environment()` deems safe to inherit (PATH, HOME,
# …), so an NPM_CONFIG_CACHE set here would never reach npx. `uvx` resolves
# /app/.cache/uv from the same HOME for the same reason.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --no-create-home --home-dir /app \
        --shell /usr/sbin/nologin app \
    && mkdir -p /var/lib/a2flow/skills /app/.npm /app/.cache/uv \
    && chown -R app:app /app /var/lib/a2flow/skills
ENV HOME=/app \
    UV_CACHE_DIR=/app/.cache/uv
USER app

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "30"]
