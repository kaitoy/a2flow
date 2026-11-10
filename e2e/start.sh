#!/usr/bin/env bash
# Starts A2Flow for the e2e suite: the backend with the scripted LLM
# (backend/scripts/e2e_server.py) on 127.0.0.1:8099, then the production
# frontend build on 127.0.0.1:3099, all against throwaway state that is removed
# when the runner stops this script. `e2e run` launches it through
# e2e.config.ts; build the frontend (`pnpm build` in frontend/) first.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
state="$(mktemp -d)"
# Git Bash on Windows: hand the backend a path native Python can open.
if command -v cygpath >/dev/null; then state="$(cygpath -m "$state")"; fi
pids=()
trap 'kill "${pids[@]}" 2>/dev/null || true; rm -rf "$state"' EXIT
trap 'exit 143' TERM INT

# ADMIN_PASSWORD is also in tests/login.ts.
export DB_URL="sqlite:///$state/e2e.db"
export SKILLS_DIR="$state/skills"
export SECRET_KEY_FILE="$state/secret.key"
export ADMIN_PASSWORD=e2e-admin-pass-123
export DEMO_DATA=true
export LLM_MODEL=e2e-fake
export CORS_ORIGINS=http://127.0.0.1:3099

(cd "$root/backend" && exec uv run python -m scripts.e2e_server) &
pids+=($!)
until curl -sf http://127.0.0.1:8099/api/v1/health >/dev/null; do
  kill -0 "${pids[0]}" 2>/dev/null || { echo "backend exited during startup" >&2; exit 1; }
  sleep 1
done

(cd "$root/frontend" && BACKEND_BASE_URL=http://127.0.0.1:8099 \
  exec ./node_modules/.bin/next start --hostname 127.0.0.1 --port 3099) &
pids+=($!)
wait "${pids[1]}"
