---
title: System Settings
sidebar_position: 12
---

# System Settings

System Settings is where the mail server that [notification email](./notifications.md#email-delivery) goes through is configured. There is exactly one settings record for the whole deployment, seeded on first startup with email delivery **off**, so a fresh install keeps notifications in-app until an operator turns it on.

Open **System Settings** in the admin sidebar. Like [Tenants](./users-and-groups.md#tenants), this section is restricted to **Super Admin** — the settings are platform-wide rather than tenant-scoped, so there is no tenant-admin carve-out, and even reading them is refused for anyone else.

## The settings

| Field | Purpose |
|---|---|
| **Application Base URL** | Where notification email links back to, e.g. `https://a2flow.example.com`. Left empty, messages are sent without a link. |
| **Send notifications by email** | The master switch. While it is off, notifications stay in-app and nothing is sent. |
| **SMTP Host** / **SMTP Port** | The relay to hand messages to. |
| **Security** | **STARTTLS** (default), **SSL/TLS** (implicit TLS), or **None**. |
| **SMTP Username** / **SMTP Password** | SMTP AUTH credentials. Leave the username empty for a relay that needs none. |
| **From Address** / **From Name** | The sender address, and the optional display name shown beside it. |

Switching delivery on without a host or a sender address is refused, so the form cannot be saved into a state that would silently fail later.

Every field here can also be set from the environment, so a deployment can ship its mail configuration rather than leaving it as a manual step — see [Notification email](../operations/configuration.md#notification-email). Those variables are re-applied on every startup, so a value set that way overwrites what was typed here.

The password is **write-only**, the same treatment [secrets](./secrets.md) and user passwords get: it is never shown back. Once one is stored the field shows blank with a "Saved" placeholder, and saving with it left empty keeps the stored password rather than clearing it.

## Checking the configuration

**Send test email** delivers a fixed test message using the *saved* settings, so a misconfiguration surfaces immediately rather than the next time a workflow raises a notification.

1. Save the settings first — the test uses what is stored, not what is on screen.
2. Click **Send test email**.
3. Check your own inbox. The recipient is fixed to the signed-in super admin's own address and cannot be pointed anywhere else.

A relay failure comes back as an error on the page; the underlying reason is logged server-side.
