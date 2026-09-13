---
title: Demo data
sidebar_position: 4
---

# Demo data

Setting `DEMO_DATA=true` on the backend registers everything two approval-gated, mutating examples need — "launch an EC2 instance" and "restart a GKE pod" — in the seeded **Default** tenant, so there is something to run without registering every piece by hand. The [workflow](../guides/workflows.md) itself is deliberately not seeded — these records are the ingredients you generate one from, which is exactly the tour below.

## Enabling it

Add the flag to `backend/.env` and restart the backend. With [Docker Compose](./docker-compose.md) it is already on: `compose.yml` sets `DEMO_DATA: ${DEMO_DATA:-true}`.

```env
DEMO_DATA=true
DEMO_PASSWORD=change-me-now-123
DEMO_AWS_ACCESS_KEY_ID=AKIA...
DEMO_AWS_SECRET_ACCESS_KEY=...
DEMO_AWS_REGION=us-east-1
DEMO_GCP_API_KEY=AIza...
```

- `DEMO_PASSWORD` is shared by all five demo users and has the same generate-and-log-once fallback as `ROOT_PASSWORD` / `ADMIN_PASSWORD`. It is only consulted while one of the accounts is missing.
- The AWS credentials and the Google Cloud API key are optional. Left unset, a `REPLACE_ME` placeholder is stored instead, so the demo is complete in shape and you fill the real values in from the [Secrets](../guides/secrets.md) page.
- `DEMO_AWS_REGION` is the region the demo AWS MCP server's tools act on. It defaults to `us-east-1`.

⚠️ Both demo MCP servers can run **mutating** operations, not just reads. The AWS MCP server's credentials can create and delete real AWS resources, and the GKE MCP server's key can delete a pod on a real cluster — use throwaway accounts or tightly scoped credentials for both. To try either demo without touching a real provider at all, see [Trying it out](#trying-it-out) below.

## What gets registered

- **[Agent skill](../guides/agent-skills.md) `Demo AWS EC2 Launch`** — gathers the instance configuration, gets a manager's explicit approval of it, then launches the instance through an MCP tool. Its repository is cloned in the background after startup, so the skill shows as `pending` for a moment before it can be used.
- **[Agent skill](../guides/agent-skills.md) `Demo GKE Pod Restart`** — agrees the exact target (project, cluster, namespace, pod name) with the user, gets a manager's explicit approval of that exact pod, then deletes it through the GKE MCP Server so its owning controller recreates it, and reports the outcome. Its repository is cloned the same way, so it also shows as `pending` at first.
- **[MCP server](../guides/mcp-servers.md) `AWS MCP Server`** — a `stdio` server reaching AWS's managed AWS MCP Server, which is where the EC2 tools come from.
- **[MCP server](../guides/mcp-servers.md) `GKE MCP Server`** — a `streamable_http` server reaching Google Cloud's managed GKE (Google Kubernetes Engine) MCP server, the full endpoint. It sends the `demo-gcp-credentials` API key as its `x-goog-api-key` header, and its tools can manage clusters and their Kubernetes resources, including deleting a pod.
- **[Secret](../guides/secrets.md) `demo-aws-credentials`** — the AWS access key id and secret access key the AWS MCP Server reads.
- **[Secret](../guides/secrets.md) `demo-gcp-credentials`** — the Google Cloud API key the GKE MCP Server sends.
- **[Tool mocks](../guides/tool-mocks.md)** — stubs for the demo run's side-effecting tools: `aws___call_aws` and `aws___run_script` on the AWS MCP Server, each returning a successful launch, `delete_k8s_resource` on the GKE MCP Server, returning a successful pod deletion, and the built-in `request_approval`, returning approved. Selecting them in a draft run's **Run** dialog lets either workflow finish without touching AWS, a real GKE cluster, or waiting on a manager.
- **Demo users and groups:**

| User | Role | What they do |
|---|---|---|
| `demo-developer` | `developer` | Generates and publishes the workflow |
| `demo-requester-1`, `demo-requester-2` | `requester` | Run the workflow |
| `demo-approver-1`, `demo-approver-2` | `approver` | Approve the launch, or the pod restart |

None of them holds its role directly: each one inherits it from a [user group](../guides/users-and-groups.md#user-groups) — `Demo Developers`, `Demo Requesters`, and `Demo Approvers`.

## Trying it out

Sign in with `DEMO_PASSWORD` as each account in turn:

1. As **`demo-developer`**, open [Agent Skills](../guides/agent-skills.md) and wait for `Demo AWS EC2 Launch` to finish cloning — **Generate workflow** stays disabled until it has.
2. Use that row's **Generate workflow** action, describe the instance you want, and let the design agent build the task list ([Generating a workflow](../guides/workflows.md#generating-a-workflow)). The workflow lands in `draft`.
3. Review the generated task templates on the workflow's detail page, then **Publish**.
4. As **`demo-requester-1`**, press **Run** on the workflow ([Running a workflow](../guides/workflows.md#running-a-workflow)). The run's chat opens and the agent starts working through the tasks.
5. When the skill asks for approval, sign in as **`demo-approver-1`** and approve it ([Approvals](../guides/approvals.md)). The agent then launches the instance through the MCP tool.

The same five steps work from **`Demo GKE Pod Restart`**: the approval covers the exact pod to delete rather than a launch, and the last step restarts a pod instead of creating anything. A real run there needs `DEMO_GCP_API_KEY` set to a key with permission to reach a real GKE cluster.

**No AWS account or GKE cluster?** Skip step 3 and run the workflow while it is still `draft` — as a `developer`, `demo-developer` may do that, and only a draft run's dialog offers the tenant's [tool mocks](../guides/tool-mocks.md). Under **Mock tools**, check the seeded stubs it lists (`aws___call_aws` or `aws___run_script` for the launch, `delete_k8s_resource` for the pod restart, and `request_approval`); the whole workflow then plays through without reaching AWS, a real GKE cluster, or waiting on a human.

## Removing it

Setting `DEMO_DATA=false` (or removing the line) **removes those records again** on the next startup — the flag is declarative in both directions.

Two things survive by design: a demo record something else has come to depend on — a workflow built on the demo skill, for instance — is kept and logged rather than deleted, and a demo user who has created records is soft-deleted so their name still resolves on those records.
