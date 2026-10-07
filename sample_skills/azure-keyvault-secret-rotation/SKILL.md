---
name: azure-keyvault-secret-rotation
description: Rotate a secret in Azure Key Vault -- write a freshly generated random value as the secret's new version -- through the registered Azure MCP server, gated by a manager's explicit approval of the exact vault and secret before anything is written. Use this skill whenever the user wants to rotate, renew, regenerate, refresh, or replace the value of a Key Vault secret (a password, an API key, a connection-string credential) through the connected MCP tooling. It agrees the exact target with the user, gets explicit manager approval, then writes the new version and reports its version id -- never writing before approval comes back approved, and never showing the secret value.
---

# Azure Key Vault Secret Rotation

Rotate a secret in Azure Key Vault through the registered **Azure MCP Server**. The core principle: overwriting the wrong secret breaks whatever reads it, and a secret value that ends up in a chat transcript is a leaked secret, so you **agree the exact vault and secret with the user, get a manager's explicit approval of that exact target, write only what was approved, then confirm the new version -- and never show the value**. Never write anything before an approval has come back approved.

## How rotation works in Key Vault

There is no dedicated "rotate" operation. Writing a secret under a name that already exists adds a **new version** of it, and the new version becomes the current one: anything that reads the secret without naming a version picks it up. Earlier versions stay in the vault, still enabled, so an application that pinned an old version keeps working until someone disables it.

## Handling the value

The new value is a secret from the moment it is generated:

- Generate it with the **Secret Value Generator**'s `generate_secret_value` tool. Never make one up yourself.
- Pass it only to the write in step 3. Never write it in a chat message, a summary, an approval request, or a task status, and never echo it back to confirm it.
- Never read a secret's value: do not call `keyvault_secret_get` with a `secret` name, since that returns the value. Calling it **without** a `secret` name lists the vault's secrets, and that is the only read you need.

## Workflow

### 1. Agree the target

Ask the user for whatever isn't already given. You need:

- **Vault** -- the Key Vault's name.
- **Secret** -- the name of the existing secret to rotate.

Do not guess either. List the vault's secrets with `keyvault_secret_get`, passing only the vault, and have the user choose one from that list. If the secret they name is not there, say so and stop: rotating means adding a version to an existing secret, and writing a new name would create an unrelated secret instead.

Once you have both, summarize the finalized target back to the user before moving on. This exact summary is also what the approver decides on in the next step.

### 2. Get manager approval

This step is mandatory. Before anything is written, a manager must explicitly approve the exact target from step 1 -- not the idea of a rotation, that exact secret in that exact vault.

Address the request to a **team** of managers rather than to one named person whenever you can, so the rotation is not blocked on one person's availability. Name a single person only when the decision genuinely belongs to them.

The request needs a short title naming the target (e.g. "Rotate Key Vault secret: `<secret>` (`<vault>`)") and a body carrying the finalized target verbatim, plus one line saying that applications reading the secret's current version will pick up the new value. It must not contain a secret value -- none exists yet. Tell the user in plain text that the request has gone out and who it went to.

Then wait for the decision. If it comes back approved, continue to step 3. If it comes back rejected, stop -- write nothing -- and tell the user the manager declined, including any comment they left. If there is nobody who can approve, stop as well and say so: writing without an approval is not an option.

### 3. Write the new version

Act on exactly what was approved. Nothing may change between the approval and the write; if the target has to change, go back to step 2 and have the new target approved.

1. Generate the value with `generate_secret_value` (the default length of 32 is fine unless the user asked for another).
2. Write it with the **Azure MCP Server**'s `keyvault_secret_create` tool, addressed at the approved vault and secret name, with that value.

If the call returns an error (permission denied, the vault does not exist, etc.), report the exact error to the user and stop -- do not retry against a different vault or name, and do not generate and try another value.

### 4. Confirm the rotation

Don't stop at "the call succeeded". List the vault's secrets again with `keyvault_secret_get` (vault only) and check that the secret now shows the update you just made. Report the new version id and when it was created, taken from the write's result -- never the value.

Remind the user that the previous version is still enabled: once everything that reads the secret has picked up the new value, they may want to disable the old version in the Azure portal.

## Reporting format

Close with a short, factual summary:

```
Rotated Key Vault secret <secret> (<vault>).
  Manager approval: approved by <approver>
  New version: <version id>
  Previous version: still enabled -- disable it once every consumer has switched over
```

If the manager rejected the request, the write failed, or the new version could not be confirmed, replace the success summary with what happened at that step and state clearly that the rotation is not confirmed complete.
