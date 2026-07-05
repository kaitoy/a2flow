# Frontend image: Next.js standalone server on port 3000.
#
# Build context must be the REPOSITORY ROOT (not frontend/), because the
# build needs backend/ to generate two gitignored artifacts:
#   - backend/openapi.yaml          (exported from the FastAPI app)
#   - frontend/src/generated/       (a2ui catalog download + openapi-ts output)
#
#   docker build -f frontend/Dockerfile .

# --- Stage 1: export the backend OpenAPI spec -------------------------------
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS openapi

WORKDIR /backend
COPY backend/ .
# Dev dependencies are required: the export script imports pyyaml.
RUN uv sync --frozen --no-install-project \
    && uv run --no-sync python -m scripts.export_openapi

# --- Stage 2: build the Next.js app -----------------------------------------
FROM node:24-slim AS build

# Backend origin baked into the Next.js rewrites at build time.
ARG BACKEND_BASE_URL=http://backend:8000
ENV BACKEND_BASE_URL=${BACKEND_BASE_URL}

RUN corepack enable

WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ .
COPY --from=openapi /backend/openapi.yaml /app/backend/openapi.yaml

# Run the prebuild steps explicitly: `pnpm exec` bypasses the package.json
# `prebuild` hook, which would shell out to `uv` (unavailable in this stage).
RUN node --use-system-ca scripts/download-a2ui-schema.mjs \
    && pnpm exec openapi-ts \
    && pnpm exec next build

# --- Stage 3: runtime --------------------------------------------------------
FROM node:24-slim

ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000

WORKDIR /app
# outputFileTracingRoot is the frontend dir itself, so the standalone bundle
# places server.js at its top level.
COPY --from=build --chown=node:node /app/frontend/.next/standalone ./
COPY --from=build --chown=node:node /app/frontend/.next/static ./.next/static
COPY --from=build --chown=node:node /app/frontend/public ./public

USER node

EXPOSE 3000

CMD ["node", "server.js"]
