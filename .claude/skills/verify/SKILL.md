---
name: verify
description: Launch a2flow (backend + frontend) against throwaway state and drive it end to end. Use when confirming a change works in the real app rather than only in tests.
---

# Verifying a2flow by running it

Run the backend and frontend against a scratch database and skill store, never
the developer's `backend/a2flow.db` — it predates Alembic and has no
`alembic_version` stamp, so `alembic upgrade head` fails on it with
`table users already exists`.

## TLS: the clone will fail without this

This machine intercepts TLS, so anything that talks HTTPS from Python (notably
the dulwich skill clone) dies with
`CERTIFICATE_VERIFY_FAILED: Basic Constraints of CA cert not marked critical`.
`uv run --native-tls` only fixes uv's own downloads, not the app's. The app
needs the OS trust store injected before any import that touches `ssl`:

```python
# run_backend.py  (keep it outside the repo, e.g. in the scratchpad)
import os
import sys

import truststore

truststore.inject_into_ssl()
sys.path.insert(0, os.getcwd())  # uvicorn must import `main` from backend/

import uvicorn

uvicorn.run("main:app", host="127.0.0.1", port=8099)
```

## Launch

```powershell
$sp = "<scratchpad>"
New-Item -ItemType Directory -Force "$sp\st\sk" | Out-Null
$env:DB_URL = "sqlite:///$sp/st/v.db"
$env:SKILLS_DIR = "$sp\st\sk"
$env:ADMIN_PASSWORD = "verify-pass-123"
$env:SECRET_KEY_FILE = "$sp\st\k.key"
cd backend
uv run --native-tls --with truststore python "$sp\run_backend.py"
```

Keep `SKILLS_DIR` **short**. A skill clone writes
`<skill_id>/.tmp-xxxxxxxx/.git/objects/pack/pack-<40 hex>.pack` beneath it, and
a deep root pushes that past Windows' 260-char `MAX_PATH`; dulwich then fails
with `WinError 3` mid-clone.

Frontend (only needed for UI work):

```powershell
cd frontend
$env:BACKEND_BASE_URL = "http://127.0.0.1:8099"
pnpm dev --port 3099
```

Open the UI at **`http://localhost:3099`**, never `http://127.0.0.1:3099`. Next's
dev server blocks cross-origin access to its own dev resources, so on `127.0.0.1`
the client chunks never load, the page never hydrates, and every form falls back
to a native GET — the login form just bounces back to `/login?username=…&password=…`
with no console error to explain it. The only clue is a
`Cross-origin access to Next.js dev resources is blocked by default` line in the
`pnpm dev` log.

## Drive the API

Auth is a session cookie plus a CSRF header echoing the `a2flow_csrf` cookie:

```bash
LOGIN=$(curl -s -c /tmp/cj.txt -X POST http://127.0.0.1:8099/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"verify-pass-123"}')
CSRF=$(grep a2flow_csrf /tmp/cj.txt | awk '{print $7}')
ADMIN_ID=$(echo "$LOGIN" | python -c "import json,sys; print(json.load(sys.stdin)['data']['id'])")

# AgentSkill is tenant-scoped and gated behind `developer`; the seeded admin
# only holds `admin` by default. Grant itself `developer` too (self-granting
# a non-super_admin role is allowed — UserService.update only gates
# super_admin grant/revoke).
curl -s -b /tmp/cj.txt -H "X-CSRF-Token: $CSRF" -X PATCH \
  http://127.0.0.1:8099/api/v1/users/$ADMIN_ID \
  -H 'Content-Type: application/json' \
  -d '{"roles":["admin","developer"]}'

curl -s -b /tmp/cj.txt -H "X-CSRF-Token: $CSRF" -X POST \
  http://127.0.0.1:8099/api/v1/agent-skills \
  -H 'Content-Type: application/json' \
  -d '{"name":"s","repoUrl":"https://github.com/octocat/Hello-World","repoPath":""}'
```

`admin` (`ADMIN_PASSWORD`) is the seeded Default-tenant account — it's the
right login for any tenant-scoped route like the one above. Don't switch this
to `root`/`ROOT_PASSWORD`: `root` holds `super_admin` and is therefore
platform-scoped (`tenant_id` is always `null` for a super_admin, by DB
constraint), so it can never pass a tenant-scoped route's authorization check
at all. Only reach for `root` to verify something genuinely platform-wide,
e.g. the Tenants admin page.

`https://github.com/octocat/Hello-World` is a good clone target: tiny, public,
stable HEAD (`7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`).

Registering a skill clones **in the background**, so poll
`GET /api/v1/agent-skills/{id}` until `syncStatus` leaves `pending`. A clone
takes ~4s.

## Gotchas

- **dulwich floods stderr** with per-object progress (`copying pack entries:
  N/M`), hundreds of KB per clone. Filter it or the log is unreadable:
  `Select-String -NotMatch "objects:|deltas:|pack entries|generating index"`.
- **GitHub answers 401, not 404, for a repository that does not exist** (it
  refuses to leak existence). So the "bad URL" path is an auth failure, not a
  not-found — worth remembering when picking a repo to force a clone failure.
- The Chrome extension may refuse `localhost:<port>`; if browser automation
  returns `Permission denied by user`, the UI cannot be driven from here.
