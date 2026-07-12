# Backend image: FastAPI + Google ADK agent served by uvicorn on port 8000.
# Python version matches backend/.python-version.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

# Install dependencies first so source changes do not invalidate this layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .

# Run as non-root. /var/lib/a2flow/skills is pre-created and chowned here
# because it's the mount point for compose.yml's `skills` named volume — Docker
# seeds a new named volume's ownership from the image path it overlays, so this
# is what makes the first skill clone (as `app`) succeed instead of hitting a
# root-owned mount point.
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --no-create-home --home-dir /app \
        --shell /usr/sbin/nologin app \
    && mkdir -p /var/lib/a2flow/skills \
    && chown -R app:app /app /var/lib/a2flow/skills
ENV HOME=/app \
    UV_CACHE_DIR=/app/.cache/uv
USER app

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
