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

The scratchpad path is itself deep, so `"$sp\st\sk"` above only survives a
shallow clone target like `octocat/Hello-World`. Adding `$env:DEMO_DATA = "true"`
clones **this** repository, whose own paths run to
`frontend/src/app/admin/workflows/[workflowId]/task-templates/[templateId]/page.test.tsx`,
and that overflows — the clone dies with `FileNotFoundError` (not `WinError 3`)
and the demo skill lands in `syncStatus: failed`. Everything else in the demo
dataset still seeds, so ignore it unless you need the skill.

Since any agent-running verification needs a repo with a `SKILL.md` (see
"Picking the skill repository" below), and the one to hand is this repository,
just default to `$env:SKILLS_DIR = "C:\a2f\sk"` — it clones a2flow without
overflowing.

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
  -d '{"username":"admin","password":"verify-pass-123","tenantName":"default"}')
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

`tenantName` is **required** for `admin`, and omitting it is the one failure
that looks like a wrong password: a tenant-scoped username is unique only
within its tenant, so `AuthService.login` cannot resolve it without the tenant
and answers the same generic `401 UNAUTHENTICATED` / "Invalid username or
password" it gives for a bad password. `default` is the seeded tenant's name
(the kebab-case identifier, not the `Default` display name). Omit `tenantName`
only for a platform-scoped user such as `root`.

`admin` (`ADMIN_PASSWORD`) is the seeded Default-tenant account — it's the
right login for any tenant-scoped route like the one above. Don't switch this
to `root`/`ROOT_PASSWORD`: `root` holds `super_admin` and is therefore
platform-scoped (`tenant_id` is always `null` for a super_admin, by DB
constraint), so it can never pass a tenant-scoped route's authorization check
at all. Only reach for `root` to verify something genuinely platform-wide,
e.g. the Tenants admin page.

Registering a skill clones **in the background**, so poll
`GET /api/v1/agent-skills/{id}` until `syncStatus` leaves `pending`. A clone
takes ~4s.

### Picking the skill repository

Which repo you register depends on how far you need to get:

- **Registration / clone plumbing only** — `https://github.com/octocat/Hello-World`
  with `repoPath: ""`. Tiny, public, stable HEAD
  (`7fd1a60b01f91b314f59955a4e4d4e80d8edf11d`), and shallow enough to clone under
  a scratchpad-deep `SKILLS_DIR`. It reaches `syncStatus: ready`.
- **Anything that actually runs an agent** — Hello-World is useless: it has no
  `SKILL.md`. The skill still clones fine, but the first thing that resolves an
  agent fails. Workflow generation, for instance, lands in
  `status: "failed"` with `generationError: The design run failed
  unexpectedly. Check the server log for details.` — `generationError` carries
  a fixed summary, never the raw reason, so the actual cause (`SKILL.md not
  found in '<skills_dir>/<skill_id>/<sha>'`, which reads like a clone problem
  and is not one) is only in the backend log.

  Use this repository's own sample skill instead:

  ```json
  {"name":"s","repoUrl":"https://github.com/kaitoy/a2flow",
   "repoPath":"sample_skills/aws-ec2-launch"}
  ```

  `repoPath` is the subdirectory holding `SKILL.md`, so a monorepo works as long
  as it points at the skill folder. This is the same skill the demo dataset
  registers. It clones fine **only with a short `SKILLS_DIR`** such as
  `C:\a2f\sk` (see the `MAX_PATH` note under Launch) — verified working there.

### Generating a workflow

`POST /api/v1/agent-skills/{id}/workflows` (`{"name":…,"prompt":…}`) creates the
workflow in `status: "generating"` and runs the initial design agent in the
**background**, so poll `GET /api/v1/workflows/{id}` until the status leaves
`generating` (`draft` on success, `failed` with `generationError` otherwise).
This calls the real LLM configured in `backend/.env` and takes ~30-60s. The
resulting task templates are on `GET /api/v1/workflows/{id}/task-templates`.

### Driving the design chat

`POST /api/v1/workflows/{id}/agent` is an AG-UI SSE stream, not an envelope
route. A design session has no id of its own — read the workflow with
`GET /api/v1/workflows/{id}`, then post a `RunAgentInput` whose `threadId` is
that record's `sessionId`:

```json
{"threadId":"<sessionId>","runId":"r1","state":{},
 "messages":[{"id":"m1","role":"user","content":"Add a task that …"}],
 "tools":[],"context":[],"forwardedProps":{"userId":"<ADMIN_ID>"}}
```

To see which tools the agent actually called, grep the stream for
`"toolCallName":"…"` rather than trying to parse the whole SSE body. The agent
may do less than you asked in one turn — a request to change *and* delete
something often comes back as one edit plus a question — so assert on the tool
calls you observed, not on the ones you hoped for.

## Gotchas

- **dulwich floods stderr** with per-object progress (`copying pack entries:
  N/M`), hundreds of KB per clone. Filter it or the log is unreadable:
  `Select-String -NotMatch "objects:|deltas:|pack entries|generating index"`.
- **GitHub answers 401, not 404, for a repository that does not exist** (it
  refuses to leak existence). So the "bad URL" path is an auth failure, not a
  not-found — worth remembering when picking a repo to force a clone failure.
- **MCP server URLs are DNS-resolved at create time** by the SSRF check in
  `infrastructure/url_safety.py`, so a made-up host like
  `https://mcp.invalid.example/mcp` is rejected with `422 VALIDATION_ERROR`
  before the row exists. To reach the *connect* path (and whatever runs before
  it, e.g. `${secret:…}` resolution), register a resolvable public host such as
  `https://example.com/mcp`: it passes validation, then fails the actual
  connection with `502 MCP_UNREACHABLE`.
- The Chrome extension may refuse `localhost:<port>`; if browser automation
  returns `Permission denied by user`, the UI cannot be driven from here.
