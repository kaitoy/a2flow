---
title: Users, groups and tenants
sidebar_position: 2
---

# Users, groups and tenants

Three admin sections cover who may sign in and what they belong to: the individual accounts, the named bundles that grant roles in bulk, and the tenant every one of them sits inside.

## Users

Navigate to [http://localhost:3000/admin/users](http://localhost:3000/admin/users) to manage application users.

| Operation | Path |
|-----------|------|
| List all users | `GET /admin/users` |
| Create a new user | `GET /admin/users/new` |
| A user's detail page — edit / delete | `GET /admin/users/{id}` |

Each user record stores a username (unique within its tenant, and separately unique among platform-scoped users with no tenant), first name, last name, email, an `enabled` flag, an `emailVerified` flag, and the user's [roles](../concepts/authorization.md). Passwords are hashed with [bcrypt](https://pypi.org/project/bcrypt/) before persistence and are never returned by the API. On edit, leaving the password field blank keeps the existing password. Users are persisted in `a2flow.db`.

**Roles.** The create form and the detail page include a roles picker (one checkbox per role); the list shows each user's roles in a **Roles** column. Roles are stored as a JSON list, so they cannot be sorted or filtered server-side via the list API's `s` / `q` parameters. The **Super Admin** checkbox is disabled unless the signed-in user is a Super Admin — the backend rejects granting or revoking it otherwise. Because Super Admin is mutually exclusive with every other role, checking it disables every other role checkbox (and vice versa), with a divider and hint explaining why — the backend rejects any combination of the two regardless.

**Roles from groups.** The picker edits **direct** grants only. Roles the user inherits from a [user group](./users-and-groups.md#user-groups) are shown beneath it under **Roles from groups**, as read-only chips — editing the user cannot change them, only editing the group can. The list's **Roles** column shows both, with inherited roles as muted chips so it stays obvious which grants this page can change. See [Roles and authorization](../concepts/authorization.md) for how the two combine.

**Groups.** The current group memberships show as removable chips; a **Select groups…** button opens a modal table of the tenant's user groups, paged and filtered server-side, for adding more. It is hidden for a platform-scoped account (a Super Admin, or the seeded system user), which can never belong to a tenant's group. Membership is read through `GET /api/v1/users/{id}/groups` and written as a separate request (`PUT /api/v1/users/{id}/groups`), only when the selection actually changed. The same membership is editable from the other side, on each [group's](./users-and-groups.md#user-groups) detail page.

**Impersonate.** Each row eligible under the [impersonation rules](../concepts/authorization.md) shows an **Impersonate** action — hidden for the signed-in user's own row, for any `super_admin` row, and, unless the viewer is a Super Admin, for any `admin` row; confirming navigates to the welcome page acting as that user. See [Roles and authorization](../concepts/authorization.md) for who can impersonate whom and how to stop.

**Profile.** A signed-in user reviews their own account from the **Profile** page (toolbar profile button → **Profile**, at `/profile`). The page opens with an identity card: an aurora banner, the user's avatar across its lower edge, and their display name as the page heading, with the `@username` handle, their roles, and the `enabled` / `emailVerified` flags as status pills beside it. Below it the remaining attributes are split into two **read-only** cards — **Account** (username, email, first and last name) and **Access** (roles, **Roles from Groups**, and **Groups**). The backend only accepts self-service updates to the avatar (everything else requires the `admin` role and the admin user detail page), so these attributes render as plain text rather than as disabled inputs. **Roles from Groups** are the roles inherited from the user's group memberships, shown as the same muted chips as the admin user detail page (see [Roles from groups](./users-and-groups.md#users) above); **Groups** are the memberships themselves, read through `GET /api/v1/users/{id}/groups`. The avatar is the page's one editable thing, and clicking it is how you edit it.

**Avatars.** Every user has an avatar shown on the toolbar profile button and in the admin user list and detail page. By default it is a deterministic SVG generated client-side with [boring-avatars](https://github.com/boringdesigners/boring-avatars) (the `beam` variant) — no image is stored and no network call is made. The seed is the user's tenant and username (`{tenantId}/{username}`), since usernames are only unique within a tenant: the same username in two tenants gets two distinct faces. A platform-scoped user (a `super_admin`, and the seeded system user) has no tenant and is seeded from the username alone. A signed-in user manages their own avatar from a dialog on the [Profile page](./users-and-groups.md#users), opened by clicking the avatar in the page's identity card: **upload** a custom image (PNG, JPEG, WebP, or GIF, up to 2 MB) or remove it, and **customize** the generated avatar by editing the color palette it is drawn from. Uploading commits immediately and closes the dialog; the palette is the dialog's only unsaved state, so **Reset to default** just rewinds the swatches and **Save** is what commits them (and closes the dialog too). A palette that matches the application default is stored as no palette at all, so resetting and saving clears the record rather than writing a copy of the default into it, and closing the dialog discards anything not saved. The palette is stored as `UserRead.avatarConfig.colors` (an ordered list of up to eight `#rrggbb` values) and applied wherever the avatar renders; the seed still decides which colors land where, so each user stays visually distinct even on a shared palette. When no palette is saved, the application default from `frontend/src/lib/avatar-palette.ts` is used. Avatar editing is self-service only — the admin user detail page shows the avatar read-only, with no upload or customization controls. An uploaded image is stored in a dedicated `user_avatars` table and served from `GET /api/v1/users/{id}/avatar`, with `UserRead.avatarUpdatedAt` acting as a presence marker and cache-busting key; uploading or removing it refreshes the signed-in user everywhere, so the toolbar profile button updates immediately. Precedence is **uploaded image → custom-palette avatar → default-palette avatar**; removing the image or resetting the palette falls back to the next option.

**Audit ownership.** Every persistent record stores `createdBy` / `updatedBy` as a foreign key to `users.id`, populated from the **authenticated session** (see [Authentication](../concepts/authentication.md)). A write whose acting user does not exist is rejected with HTTP 422 (`FOREIGN_KEY_VIOLATION`). To resolve the bootstrap "who creates the first user" problem, a hidden, login-disabled **system user** is seeded on startup when the `users` table is empty, and it owns the initial seeded `root` and `admin` users. In the admin UI the raw IDs are never shown — each detail page resolves `createdBy` / `updatedBy` to the user's `first last` name, and list views resolve user IDs the same way.

**Resolving names in bulk.** A screen showing many user references (an audit footer, a table of workflow initiators or approvers) resolves them all through one `POST /api/v1/users/resolve-names` call, which takes up to 1000 IDs and returns `{id, displayName}` for each. It applies the same tenant boundary as `GET /api/v1/users/{id}`: a user outside the caller's tenant is not named, and the ID is simply absent from the response so the UI falls back to showing it raw. Two kinds of account are labelled rather than dropped, since they own records across tenant boundaries and a bare UUID would read as a bug: the seeded system user resolves to **System User**, and any `super_admin` invisible to the caller resolves to **Super Admin** — the same label for all of them, so which individual it was stays undisclosed. A Super Admin caller is exempt from the boundary and sees every real name.

**Deleting a user.** If no other record references the user, it is hard-deleted from the database. If it is still referenced (via any `createdBy` / `updatedBy`), it is instead **soft-deleted**: `deletedAt` is set and the account is disabled, so existing references stay valid and the name still resolves. Soft-deleted users (and the system user) are hidden from the user list but remain fetchable by id.

## User Groups

Navigate to [http://localhost:3000/admin/user-groups](http://localhost:3000/admin/user-groups) to manage user groups — named bundles of users that grant their roles to every member.

| Operation | Path |
|-----------|------|
| List all user groups | `GET /admin/user-groups` |
| Create a new user group | `GET /admin/user-groups/new` |
| A group's detail page — edit / delete | `GET /admin/user-groups/{id}` |

A group belongs to exactly one tenant (its name is unique within that tenant) and stores a description, the **roles it grants**, and its **members**. Every member holds those roles on top of whatever is granted on their own user record — see [Roles and authorization](../concepts/authorization.md) for how the two combine. Nothing is denormalized onto the user, so changing a group's roles or membership takes effect for everyone affected on their very next request.

**Roles granted.** The roles picker is the same one the [Users](./users-and-groups.md#users) pages use, minus **Super Admin** — a group can never grant it, and the option is hidden from every viewer including a Super Admin. Submitting it anyway is rejected with HTTP 422, and a database check constraint backs that up.

**Members.** The current members show as removable chips; a **Select members…** button opens a modal table of the tenant's users, paged and filtered server-side, for adding more. Platform-scoped accounts (Super Admins and the seeded system user) are omitted: they belong to no tenant, so they can never be members — which is also why `super_admin` can never arrive through a group. Supplying members replaces the group's membership wholesale; leaving the field untouched on an edit keeps it as-is. The same membership is editable from the other side, on each [user's](./users-and-groups.md#users) detail page.

Writes require the `admin` role. Reads stay open like every other section, so a viewer without it sees the list and a read-only detail page. **Deleting** a group removes its membership rows with it: the accounts are untouched, but they lose the roles the group was granting them.

## Tenants

Navigate to [http://localhost:3000/admin/tenants](http://localhost:3000/admin/tenants) to manage tenants — the top-level organizational boundary for multi-tenancy. Unlike every other admin section, this one is restricted to **Super Admin**: it is hidden from the sidebar and welcome page for every other role, and the backend rejects writes from anyone else with HTTP 403 (`FORBIDDEN`).

| Operation | Path |
|-----------|------|
| List all tenants | `GET /admin/tenants` |
| Create a new tenant | `GET /admin/tenants/new` |
| A tenant's detail page — edit / delete | `GET /admin/tenants/{id}` |

Each tenant record stores a unique `displayName` (human-readable label), a unique URL-safe `name` (lowercase kebab-case, intended for use in paths or subdomains by later tasks), and an `enabled` flag for deactivating a tenant without deleting it — disabling a tenant blocks sign-in for its users and signs out anyone already logged in on their next request. A [user](./users-and-groups.md#users) belongs to at most one tenant (`User.tenantId`); a tenant cannot be deleted while any user is still assigned to it — the API rejects the delete with HTTP 409 (`CONFLICT_REFERENCED`) instead. A **Default** tenant (`name: default`) is seeded automatically on first startup, holding the initial seeded `admin` user.
