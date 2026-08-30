---
title: Tenants
sidebar_position: 2
---

# Tenants

A **tenant** is A2Flow's top-level organizational boundary. Nearly every record belongs to exactly one of them, a small set of things deliberately sits above them all, and no request ever crosses from one tenant into another. Creating and editing the tenant records themselves is an admin task, covered under [Tenants](../guides/users-and-groups.md#tenants); this page is about what the boundary means for everything else.

## What a tenant scopes

| Scope | What sits there |
|---|---|
| **Tenant-scoped** | Agent skills, workflows and their design sessions, task templates, workflow executions and their workflow sessions, approvals, secrets, MCP servers, tool mocks, tags, user groups — and most users |
| **Platform-scoped** | The tenant records themselves, [System Settings](../guides/system-settings.md), Super Admin accounts, and the seeded system user |

A [user](../guides/users-and-groups.md#users) belongs to **at most one** tenant. A [user group](../guides/users-and-groups.md#user-groups) belongs to **exactly one** — which is why a group can never grant `super_admin`, a platform-scoped role by definition (see [Effective roles](./authorization.md#effective-roles)). A **Default** tenant is seeded on first startup and holds the initial seeded `admin` user; the seeded `root` user is platform-scoped and has no tenant at all.

## The tenant boundary

Every tenant-scoped read and write resolves within the caller's tenant, and a record that exists only in another tenant is reported as **HTTP 404, not 403** — the boundary hides existence rather than announcing it. That applies to a workflow id typed into a URL as much as to an id passed to an API, and it is why a cross-tenant reference never confirms that the record is real.

The one read that neither returns a record nor pretends it is missing is bulk name resolution: `POST /api/v1/users/resolve-names` drops users outside the caller's tenant from its response so the UI falls back to the raw id, but labels the two account kinds that legitimately own records inside every tenant — see [Resolving names in bulk](../guides/users-and-groups.md#users).

## Acting as a tenant {#acting-as-a-tenant}

A platform-scoped Super Admin has no tenant of their own, yet nearly everything worth looking at belongs to one. A **tenant switcher** in the app header — visible only to Super Admins — is how they pick which tenant to act as. The choice is remembered across reloads and applies everywhere, including the admin section and chat. With no tenant selected, tenant-scoped requests are rejected with HTTP 403.

Switching tenants does not change *roles*: a Super Admin still bypasses every role gate regardless of which tenant is selected.

The switcher only ever appears for a caller who has no tenant of their own. A **tenant-scoped user is always scoped to their own tenant**, and the `X-Tenant-Id` header the switcher sets is ignored for them entirely — sending it by hand grants nothing, so the boundary cannot be escaped from the client.

### All tenants {#all-tenants}

The switcher also offers an **All tenants** option, which browses every tenant's data at once on the read-only admin list and detail pages. With it active, those pages add a **Tenant** column (and field) so rows from different tenants stay distinguishable.

| Selection | Reads | Writes | Chat history | Agent endpoints |
|---|---|---|---|---|
| Own tenant (implicit, every tenant-scoped user) | Own tenant | Own tenant | Own tenant | ✅ |
| One tenant (Super Admin) | That tenant | That tenant | That tenant | ✅ |
| **All tenants** (Super Admin) | Every tenant | ❌ 403 | Every tenant | ❌ 403 |
| Nothing selected (Super Admin) | ❌ 403 | ❌ 403 | ❌ 403 | ❌ 403 |

"Chat history" is `GET /workflows/{id}/messages` and `GET /workflow-executions/{id}/messages`, so a Super Admin reviewing another tenant's workflow or run can read its conversation too. The agent endpoints that *drive* those chats (`POST .../agent`) are writes and always require one concrete tenant to be selected. Under an All tenants selection a workflow id resolves regardless of tenant, so the design session's own role check stands in for the tenant boundary there — see [Design session](./authorization.md#design-session-access).
