---
title: System Settings
sidebar_position: 13
---

# System Settings

System Settings is where the mail server that [notification email](./notifications.md#email-delivery) goes through, and the global HashiCorp Vault, are configured. There is exactly one settings record for the whole deployment, seeded on first startup with email delivery **off**, so a fresh install keeps notifications in-app until an operator turns it on. The address users open A2Flow at is not configured here: an operator sets it when deploying — see [Server settings](../operations/configuration.md#server-settings).

Open **System Settings** in the admin sidebar. Like [Tenants](./users-and-groups.md#tenants), this section is restricted to **Super Admin** — the settings are platform-wide rather than tenant-scoped, so there is no tenant-admin carve-out, and even reading them is refused for anyone else.

## The settings

| Field | Purpose |
|---|---|
| **Send notifications by email** | The master switch. While it is off, notifications stay in-app and nothing is sent. |
| **SMTP Host** / **SMTP Port** | The relay to hand messages to. |
| **Security** | **STARTTLS** (default), **SSL/TLS** (implicit TLS), or **None**. |
| **SMTP Username** / **SMTP Password** | SMTP AUTH credentials. Leave the username empty for a relay that needs none. |
| **From Address** / **From Name** | The sender address, and the optional display name shown beside it. |

Switching delivery on without a host or a sender address is refused, so the form cannot be saved into a state that would silently fail later.

Every field here can also be set from the environment, so a deployment can ship its mail configuration rather than leaving it as a manual step — see [Notification email](../operations/configuration.md#notification-email). Those variables are re-applied on every startup, so a value set that way overwrites what was typed here.

The password is **write-only**, the same treatment [secrets](./secrets.md) and user passwords get: it is never shown back. Once one is stored the field shows blank with a "Saved" placeholder, and saving with it left empty keeps the stored password rather than clearing it.

## The global Vault {#global-vault}

The global Vault is the HashiCorp Vault (KV v2 only) that every tenant **without a Vault of its own** reads its [Vault-type secrets](./secrets.md) from. A tenant's admin can connect the tenant's own Vault instead under [Tenant Settings](./users-and-groups.md#tenant-vault), and that one always takes precedence.

| Field | Purpose |
|---|---|
| **Global Vault Address** | The Vault's address, starting with `http://` or `https://`. Unlike a tenant's own Vault, it may be on a private network. Leave it empty and save to disconnect the global Vault. |

Only the address is set here. There is no shared credential: each tenant logs in with **a credential of its own**, which a Super Admin registers on the tenant's page (see [The global Vault credential](./users-and-groups.md#global-vault-credential)). A tenant without one cannot read the global Vault at all.

Tenants are kept apart **by Vault itself**: a secret is read from the **Vault Mount** and **Vault Path** it names, and the policies attached to the tenant's credential decide whether that read is allowed. Issue each tenant a credential whose policy covers only that tenant's data — for example, an AppRole per tenant with a policy like this for the `acme` tenant:

```hcl
path "secret/data/tenants/acme/*" {
  capabilities = ["read"]
}
```

## Checking the configuration

**Send test email** delivers a fixed test message using the *saved* settings, so a misconfiguration surfaces immediately rather than the next time a workflow raises a notification.

1. Save the settings first — the test uses what is stored, not what is on screen.
2. Click **Send test email**.
3. Check your own inbox. The recipient is fixed to the signed-in super admin's own address and cannot be pointed anywhere else.

A relay failure comes back as an error on the page; the underlying reason is logged server-side.
