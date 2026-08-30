---
title: Audit Logs
sidebar_position: 12
---

# Audit Logs

Audit Logs collects the four records A2Flow keeps of what it did on your behalf: the tool calls its agents made, the sessions where one person acted as another, the authority each granted approval carried, and the mail it sent. Every one is append-only — nothing in the screen edits or removes a record, which is what makes it evidence.

Open **Audit Logs** in the admin sidebar. Four tabs sit above the table:

| Tab | One row is |
|---|---|
| **Tool Invocations** | One decision the tool proxy made about one tool call |
| **Impersonations** | One session where an administrator acted as another user |
| **Certificates** | The authority issued when one approval was granted |
| **Emails** | One notification message queued for delivery |

Each list behaves like every other admin table — sorting, filtering, the column picker, paging — see [Admin UI](./admin-ui.md#the-list-screen). Clicking a row's first cell opens a read-only detail page that shows the long values a table cell clips.

## Who sees it

The section is shown to **Admin** and **Super Admin** only. Everyone else gets an access-denied screen, and it does not appear in their sidebar.

That is stricter than most sections, whose reads stay open to anyone signed in. These lists span every run, account and message in the tenant, so the participant-level access that lets you see *your own* run's records is not enough here. The narrower views remain where they were: a run's own tool calls are still on its [Tool Invocations](./workflow-executions.md#tool-invocations) page, and an approval's certificate is still on the [approval](./approvals.md) itself.

A Super Admin sees whichever tenant the tenant switcher has selected, and can select **All tenants** to browse across all of them at once. In that mode each list gains a **Tenant** column.

## Tool Invocations

The tool calls that reached the proxy, and what it decided about each: `allowed` ones that went upstream, `denied` ones a rule vetoed.

| Column | Notes |
|---|---|
| **Tool** / **Server** | What was called, and where |
| **Decision** | `allowed` or `denied` |
| **Denial Reason** | Why a refused call was refused, in the rule's own words |
| **Workflow Execution** | The run the call belonged to — links to it |
| **Approval** / **Certificate** | Which approval authorized the call, when one did |
| **Arguments Digest** | A fingerprint of what the call asked for |

The arguments themselves are never stored — only the fingerprint the presented signature covers, which is what lets a recorded call be re-checked later without keeping what it carried. The detail page shows the full fingerprint, the signature, and the exact instant that was signed.

Calls to a [mocked](./tool-mocks.md) tool are absent here whichever way they went, since a stubbed call reaches no server. The run's chat transcript is where those are inspected.

## Impersonations

One row per session where an administrator acted as another user, from the moment they started until they stopped. A row with no **Ended At** is a session still in progress, marked **Active**.

| Column | Notes |
|---|---|
| **Impersonator** | Who acted — links to their account |
| **Target User** | Whose account they acted as — links to it |
| **State** | **Active** while the session is open, **Ended** once it closes |
| **Started At** / **Ended At** | When it began and finished |

Rows are scoped by the **impersonated** account's tenant, not the actor's. That is deliberate: a Super Admin belongs to no tenant, so scoping on the actor would hide their sessions from every tenant — exactly the ones an administrator most needs to see. See [Impersonation](../concepts/impersonation.md).

## Certificates

What each granted approval actually authorized. A certificate is issued the moment an approval on a task is approved, and it is what lets that task call its bound tools — so this list is the record of tool authority granted and spent.

| Column | Notes |
|---|---|
| **Serial** | Identifies the certificate — the value the Tool Invocations list shows against calls that presented it |
| **Approval** | The approval it was issued for — links to it |
| **State** | **Live**, or **Revoked** once the authority is spent |
| **Allowed Tools** | The tools this approval granted |
| **Not Before** / **Not After** | The window it is valid in |
| **Revoked At** / **Revocation Reason** | When and why it stopped counting |

**Allowed Tools** is read back out of the issued certificate itself rather than from a separate copy, so what this screen shows can never differ from what the approval actually authorized — even if the run's task bindings were rewritten afterwards. No key material is ever shown or downloadable.

## Emails

The notification messages A2Flow has queued for delivery, and how each fared.

| Column | Notes |
|---|---|
| **To** / **Subject** | Who it was addressed to, and about what |
| **Status** | `pending`, `sending`, `sent` or `failed` |
| **Attempts** | How many delivery attempts have been made |
| **Sent At** | When it went out |
| **Last Error** | Why the most recent attempt failed |

A message that could not be delivered lands in `failed` and is **kept** rather than removed, so a notification that never arrived stays visible with its reason recorded. The message body is frozen when the notification is produced, not composed at send time — the detail page shows it in full, exactly as delivered.

A Super Admin can delete a `sent` or `failed` row; an Admin cannot, and a row still `pending` or `sending` is refused for either, since the mail worker may be holding it. See [Notifications](./notifications.md) for how these messages come to be queued, and [System Settings](./system-settings.md) for the mail server they go through.
