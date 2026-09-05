# Two images from one source tree, sharing every layer up to `base`:
#
#   target: backend    -- the API and the email worker
#   target: mcp-proxy  -- the sandbox that launches registered MCP servers
#
# The split is not packaging tidiness. A registered MCP server is third-party
# code, and it now runs only in the second image; the first no longer needs the
# ~200MB of Node.js that launching one requires, and the second has no business
# holding the skill store. What each stage adds is what only that stage uses.
#
# Python version matches backend/.python-version.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS base

WORKDIR /app

# Install dependencies first so source changes do not invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

# Run as non-root. /app/.cache/uv is the uv cache, resolved from HOME so that
# `uvx` finds it too -- the MCP SDK spawns stdio servers with only the variables
# `get_default_environment()` deems safe to inherit (PATH, HOME, ...), so a
# UV_CACHE_DIR set here would not reach a `uvx`-launched server on its own.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --no-create-home --home-dir /app \
        --shell /usr/sbin/nologin app \
    && mkdir -p /app/.cache/uv \
    && chown -R app:app /app
ENV HOME=/app \
    UV_CACHE_DIR=/app/.cache/uv


FROM base AS backend

# curl is used by compose.yml's backend healthcheck to probe /api/v1/health.
#
# /var/lib/a2flow/skills and /var/lib/a2flow/mcp-tls are pre-created and chowned
# because they are the mount points for compose.yml's named volumes -- Docker
# seeds a new named volume's ownership from the image path it overlays, so this
# is what makes the first skill clone and the first certificate write (both as
# `app`) succeed instead of hitting a root-owned mount point.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/lib/a2flow/skills /var/lib/a2flow/mcp-tls \
    && chown -R app:app /var/lib/a2flow
USER app

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-graceful-shutdown", "30"]


FROM base AS mcp-proxy

# Node.js, so stdio MCP servers registered as npm packages can be launched with
# `npx`. Copied from the official image rather than installed from apt because
# bookworm still ships the end-of-life Node 18. (`uvx` needs nothing extra: the
# base image already provides uv.) Only this stage gets it -- this is the only
# process that launches an MCP server.
#
# /app/.npm is npx's package cache, written the first time a stdio MCP server
# registered as an npm package is launched. Derived from HOME for the same
# reason as the uv cache above.
COPY --from=node:22-bookworm-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-bookworm-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && mkdir -p /app/.npm \
    && chown -R app:app /app/.npm
USER app

EXPOSE 8443

CMD ["uv", "run", "--no-sync", "python", "-m", "mcp_proxy"]
