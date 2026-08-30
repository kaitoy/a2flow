---
title: Impersonation
sidebar_position: 4
---

# Impersonation

Impersonation lets a privileged user **act as** another user — to reproduce what that person sees, or to carry out something on their behalf. Every request made while impersonating is attributed to the impersonated user, and every impersonation session is recorded. Starting one requires `admin` (or `super_admin`).

## Who can impersonate whom {#who-can-impersonate-whom}

| Actor ＼ Target | Holds `super_admin` | Holds `admin` | Any other user |
|---|---|---|---|
| **Super Admin** | ❌ | ✅ platform-wide | ✅ platform-wide |
| **Admin** | ❌ | ❌ | ✅ own tenant only |
| Any other role | ❌ | ❌ | ❌ — the action is not offered at all |

The shape of that table is the point: impersonation can never be used to gain a privilege the actor does not already hold. A regular Admin cannot impersonate a fellow Admin, and a Super Admin gains nothing by impersonating one, since they already bypass every gate an Admin would pass.

The **target** is judged on their [effective roles](./authorization.md#effective-roles), so an `admin` inherited from a [user group](../guides/users-and-groups.md#user-groups) protects its holder exactly as a directly granted one does — otherwise the group would be a way around the table above.

Four more targets are refused regardless of roles: **yourself**, the seeded **system user**, a **disabled** user, and a **soft-deleted** one. And for an Admin, a target in another [tenant](./tenants.md) answers **HTTP 404, not 403** — a cross-tenant reference never confirms that the user exists.

## Starting and stopping {#starting-and-stopping}

Start it from the **Impersonate** action on the [Users](../guides/users-and-groups.md#users) list; confirming lands on the welcome page acting as that user. While it is active, a header chip shows "Acting as `<user>`" with a one-click **Stop**.

Only one impersonation is open at a time: starting a new one closes whatever was open before. Stopping is always safe to call, even when nothing is open.

## The effective identity {#effective-identity}

Impersonation is a **request-header override, not a session swap**. The real session cookie never changes; the browser simply attaches the selected user id to each request, and the backend resolves the effective identity from it. Two consequences follow:

- The real actor's own session stays alive underneath, so stopping never requires signing in again.
- Everything a request touches — reads, writes, and the audit `createdBy` / `updatedBy` fields — is attributed to the impersonated user, exactly as if they were signed in themselves. **Role checks run against the impersonated user's effective roles too**, so a Super Admin acting as a Requester is held to a Requester's gates and sees the UI a Requester sees.

The start and stop endpoints are the deliberate exception: they are gated on the **real** actor's roles rather than the effective identity's. Otherwise an admin impersonating a deliberately unprivileged user would fail the role check on their own "stop" call and be stuck there.

## When an impersonation stops being valid {#stale-impersonations}

Eligibility is re-checked on **every** request, not just when impersonation starts — the table above depends on roles, and roles move. If the impersonation no longer holds, the request does not fail: it silently falls back to the real actor and closes the stale record. That covers the target being disabled or deleted, the target being promoted (including by being added to a group that grants `admin`), the actor losing `super_admin`, and the impersonation having been stopped somewhere else.

Failing the request instead would be worse than useless: the selection lives in the browser's local storage, so an error would let one stale value lock a legitimate admin out of the whole application.

## Audit trail {#audit-trail}

Every impersonation session is recorded in a persistent audit trail — who, whom, and when — in the `impersonation_events` table (see the [configuration reference](../operations/configuration.md)). Because the impersonated user is what lands in `createdBy` / `updatedBy`, this trail is the only thing that answers "who was really behind that write?", which is exactly why it is not optional.
