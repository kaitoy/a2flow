---
title: System Settings
sidebar_position: 12
---

# System Settings

Navigate to [http://localhost:3000/admin/system-settings](http://localhost:3000/admin/system-settings) to configure the mail server that [notification email](./notifications.md#email-delivery) is sent through. Like [Tenants](./users-and-groups.md#tenants), this section is restricted to **Super Admin** — the settings are platform-wide rather than tenant-scoped, so there is no tenant-admin carve-out, and the backend rejects reads as well as writes from anyone else with HTTP 403 (`FORBIDDEN`).

There is exactly one settings record for the whole deployment. It is seeded on first startup with email delivery **off**, so a fresh install keeps notifications in-app until an operator turns it on.

| Field | Purpose |
|---|---|
| `appBaseUrl` | Where notification email links back to, e.g. `https://a2flow.example.com`. Left empty, messages are sent without a link. |
| `smtpEnabled` | Master switch. While off, notifications stay in-app and nothing is sent. |
| `smtpHost` / `smtpPort` | The relay to hand messages to. |
| `smtpSecurity` | `starttls` (default), `ssl` (implicit TLS), or `none`. |
| `smtpUsername` / `smtpPassword` | SMTP AUTH credentials. Leave the username empty for a relay that needs none. |
| `smtpFromEmail` / `smtpFromName` | The sender address, and the optional display name shown beside it. |

The password is **write-only**, the same treatment [secrets](./secrets.md) and user passwords get: it is stored as Fernet ciphertext and never returned by the API. The form therefore shows the field blank with a "Saved" placeholder once one is stored, and saving with it left empty keeps the stored value rather than clearing it. Enabling delivery without a host or a sender address is rejected with HTTP 422 (`INVALID_SYSTEM_SETTINGS`).

A **Send test email** button delivers a fixed test message using the *saved* settings, so a misconfiguration surfaces immediately rather than the next time a workflow raises a notification. The recipient is fixed server-side to the signed-in super admin's own address — it cannot be pointed anywhere else — and a relay failure comes back as HTTP 502 (`EMAIL_SEND_FAILED`) with the underlying reason logged server-side only.

`appBaseUrl` and `smtpHost` deliberately skip the SSRF host check that [Agent Skill](./agent-skills.md) repository URLs and [MCP server](./mcp-servers.md) URLs go through: both legitimately name a host inside the deployment's own network, and neither is fetched on a caller's behalf.
