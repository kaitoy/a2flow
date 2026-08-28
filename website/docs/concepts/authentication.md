---
title: Authentication
sidebar_position: 2
---

# Authentication

The app requires sign-in. Visiting any page while logged out redirects to `/login`. On first run, log in with the seeded **`root`** user (platform-wide `super_admin` — leave the tenant field blank) or the **`admin`** user seeded inside the **Default** tenant (enter `default` as the tenant): set `ROOT_PASSWORD` / `ADMIN_PASSWORD` before the first startup, or, if left unset, read the randomly generated passwords from `docker compose logs backend` (each printed once and not recoverable afterwards). Manage additional users from the [admin UI](../guides/users-and-groups.md#users). After signing in the user lands on the [welcome page](../guides/admin-ui.md#welcome-page).

- **Session** — login creates a server-side session (`auth_sessions` table) and sets an HttpOnly `a2flow_session` cookie holding an opaque token (only its hash is stored). Sessions use a sliding **idle timeout** (`SESSION_IDLE_TIMEOUT_SECONDS`, default 8 hours).
- **CSRF** — login also sets a readable `a2flow_csrf` cookie; the frontend echoes it in the `X-CSRF-Token` header on every state-changing request (double-submit cookie). The backend rejects mismatches with `403`.
- **Same-origin proxy** — the browser calls the frontend origin (`:3000`); the frontend's proxy (`frontend/src/proxy.ts`) forwards `/api/*` to the backend (`:8000`), so the auth cookies are first-party and `SameSite=Lax` works. Point the proxy elsewhere with `BACKEND_BASE_URL`.

See [backend/README.md](https://github.com/kaitoy/a2flow/blob/master/backend/README.md#authentication) for the endpoint and cookie details.
