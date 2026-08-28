---
title: Demo data
sidebar_position: 4
---

# Demo data

Setting `DEMO_DATA=true` on the backend registers a ready-made example of the approval-gated "launch an EC2 instance" workflow on startup, so there is something to run without registering every piece by hand. Everything lands in the seeded **Default** tenant:

- two [secrets](../guides/secrets.md) holding an AWS access key id and secret access key,
- an [MCP server](../guides/mcp-servers.md) (`AWS MCP Server`) that reaches AWS's managed AWS MCP Server over `stdio`, through the `mcp-proxy-for-aws` bridge launched with `uvx`, reading those secrets through `${secret:…}` references,
- an [agent skill](../guides/agent-skills.md) pointing at `sample_skills/aws-ec2-launch` in this repository,
- two approver [users](../guides/users-and-groups.md#users), `demo-approver-1` and `demo-approver-2`, two requester users, `demo-requester-1` and `demo-requester-2`, plus a `demo-developer`, each holding **no direct role at all**,
- three [user groups](../guides/users-and-groups.md#user-groups) — `Demo Approvers`, `Demo Requesters`, and `Demo Developers` — granting `approver`, `requester`, and `developer` respectively. `Demo Approvers` and `Demo Requesters` each hold both matching accounts; `Demo Developers` holds its one matching user alone. Every demo account therefore gets its role purely by inheritance, so the demo exercises the group feature itself: take a user out of their group and their access disappears on the next request.

The [workflow](../guides/workflows.md) itself is not seeded — these are the ingredients you generate one from. Turning the flag off and restarting **removes** the same records again, so it is a genuine on/off switch. Records that other data has come to depend on are kept (and logged) rather than deleted, and a demo user who has created records is soft-deleted so their name still resolves.

⚠️ The demo MCP server can run **mutating** AWS operations, not just reads. Whatever credentials you give it can create and delete real resources — use a throwaway account or a tightly scoped IAM policy.

## The seeded records

| Resource | Name | Details |
|---|---|---|
| Secret | `demo-aws-credentials` | `local` type with two entries, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, each Fernet-encrypted like any other secret |
| MCP server | `AWS MCP Server` | `stdio` transport, `uvx mcp-proxy-for-aws@1.6.4 https://aws-mcp.us-east-1.api.aws/mcp --region us-east-1 --metadata AWS_REGION=${env:AWS_REGION}`; its `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` env vars are `${secret:demo-aws-credentials/…}` references to the two entries above, and its `AWS_REGION` env var (from `DEMO_AWS_REGION`) is what the `--metadata AWS_REGION=${env:AWS_REGION}` argument expands to at connection time |
| Agent skill | `Demo AWS EC2 Launch` | `sample_skills/aws-ec2-launch` in this repository (see [Agent skills](../guides/agent-skills.md)) |
| User | `demo-approver-1` | holds **no direct role**; inherits `approver` from `Demo Approvers` — a manager the sample skill can route its approval request to |
| User | `demo-approver-2` | holds **no direct role**; inherits `approver` from `Demo Approvers` — a second manager, showing a group can have more than one member |
| User | `demo-requester-1` | holds **no direct role**; inherits `requester` from `Demo Requesters` — may execute the workflow |
| User | `demo-requester-2` | holds **no direct role**; inherits `requester` from `Demo Requesters` — a second requester, showing a group can have more than one member |
| User | `demo-developer` | holds **no direct role**; inherits `developer` from `Demo Developers` — may build and register the workflow, MCP server, and agent skill |
| User group | `Demo Approvers` | grants `approver`; members `demo-approver-1` and `demo-approver-2` |
| User group | `Demo Requesters` | grants `requester`; members `demo-requester-1` and `demo-requester-2` |
| User group | `Demo Developers` | grants `developer`; sole member `demo-developer` |

Granting each demo account its role through a group rather than directly is deliberate: it makes the demo exercise [role inheritance](../concepts/authorization.md) end to end, so removing a user from their group visibly revokes their access. A database seeded by an older version — where the roles were granted directly — is normalized on the next startup, so the grant never ends up duplicated.

The Workflow itself is deliberately not seeded: these records are the ingredients you assemble one from.

```env
DEMO_DATA=true
DEMO_PASSWORD=change-me-now-123
DEMO_AWS_ACCESS_KEY_ID=AKIA...
DEMO_AWS_SECRET_ACCESS_KEY=...
DEMO_AWS_REGION=us-east-1
```

- `DEMO_PASSWORD` is shared by all five demo users and has the same generate-and-log-once fallback as `ROOT_PASSWORD` / `ADMIN_PASSWORD`. It is only consulted while one of the accounts is missing.
- **AWS MCP Server** is a managed remote server AWS hosts, not something this project runs, so the registered `stdio` server actually launches [`mcp-proxy-for-aws`](https://github.com/aws/mcp-proxy-for-aws) — a thin bridge that SigV4-signs each request with the credentials it finds in its environment and forwards it to the endpoint. It supersedes the deprecated self-hosted `awslabs.aws-api-mcp-server`; see the upstream [migration guide](https://github.com/awslabs/mcp/blob/main/src/aws-api-mcp-server/MIGRATION.md).

  The two regions in the arguments are not the same knob. `--region us-east-1` is the region the *signature* is computed for and is fixed to wherever the endpoint lives, while `--metadata AWS_REGION=${env:AWS_REGION}` (which expands to `DEMO_AWS_REGION`, carried in the row's own `env` — see [`${env:NAME}`](../guides/mcp-servers.md)) is the region the server's *tools* act on. The proxy does not infer the signing region from the endpoint URL, so it stays explicit.

- The AWS credentials are optional. Left unset, a `REPLACE_ME` placeholder is stored instead, so the demo is complete in shape and you fill the real values in from the Secrets page. Set them here to have the demo reach AWS straight after startup. They need permission to call the managed endpoint (the `aws-mcp` service) on top of the permissions for whatever the tools go on to do.

  > **The demo MCP server is not restricted to read-only operations.** Whatever credentials you give it can create, modify, and delete real resources — including running instances that cost money. Point it at a throwaway account, or scope the IAM policy down. (`mcp-proxy-for-aws` has a `--read-only` flag, but the sample workflow launches an instance, so the demo deliberately does not pass it.)

- The agent skill's repository is cloned in the background after startup, so a slow or unreachable remote never delays the server coming up. The skill shows as `pending` until the clone lands, exactly as a skill registered through the API does; a failure is recorded on the skill row with its reason.

Turning the flag off (`DEMO_DATA=false`, or removing it) **removes those records again** on the next startup — the flag is declarative in both directions. Each record is tracked by a fixed id, not by name, so renaming one in the admin UI does not strand it.

Two things survive that removal by design:

- A demo record something else has come to depend on — a Workflow built on the demo skill, a task tool binding on the demo MCP server — cannot be deleted. That is logged at `WARNING` and skipped; the remaining demo records are still removed, and the app starts normally.
- A demo user who has signed in and created records is **soft-deleted** (disabled, `deletedAt` set) rather than removed, so their name still resolves on those records. Re-enabling `DEMO_DATA` revives such an account instead of leaving it disabled.
