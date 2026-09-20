---
title: Demo data
sidebar_position: 4
---

# Demo data

Setting `DEMO_DATA=true` on the backend registers everything two approval-gated, mutating examples need — "launch an EC2 instance" and "restart a GKE pod" — in the seeded **Default** tenant, so there is something to run without registering every piece by hand. The [workflow](../guides/workflows.md) itself is deliberately not seeded — these records are the ingredients you generate one from, and the [Walkthrough](./walkthrough.mdx) is the tour that does it.

## Enabling it

Add the flag to `backend/.env` and restart the backend. With [Docker Compose](./docker-compose.md) it is already on: `compose.yml` sets `DEMO_DATA: ${DEMO_DATA:-true}`.

```env
DEMO_DATA=true
DEMO_PASSWORD=change-me-now-123
DEMO_AWS_ACCESS_KEY_ID=AKIA...
DEMO_AWS_SECRET_ACCESS_KEY=...
DEMO_AWS_REGION=us-east-1
DEMO_GCP_CREDENTIALS_JSON='{"type":"service_account",...}'
```

- `DEMO_PASSWORD` is shared by all eight demo users and has the same generate-and-log-once fallback as `ROOT_PASSWORD` / `ADMIN_PASSWORD`. It is only consulted while one of the accounts is missing.
- The AWS credentials and the Google Cloud credential are optional. Left unset, a `REPLACE_ME` placeholder is stored instead, so the demo is complete in shape and you fill the real values in from the [Secrets](../guides/secrets.md) page.
- `DEMO_AWS_REGION` is the region the demo AWS MCP server's tools act on. It defaults to `us-east-1`.
- `DEMO_GCP_CREDENTIALS_JSON` is a Google Cloud credential JSON on a single line — a service account key, or the authorized-user JSON `gcloud` writes after a one-time sign-in with an OAuth client ID and secret. The GKE MCP server mints its access token from it; Google's MCP servers do not accept API keys. See [Google Cloud MCP servers](../guides/mcp-servers.md#google-cloud-mcp-servers) for how to obtain either.

⚠️ Both demo MCP servers can run **mutating** operations, not just reads. The AWS MCP server's credentials can create and delete real AWS resources, and the GKE MCP server's identity can roll out a restart of a workload, or delete a pod, on a real cluster — use throwaway accounts or tightly scoped credentials for both. To try either demo without touching a real provider at all, see [Trying it out](#trying-it-out) below.

## What gets registered

- **[Agent skill](../guides/agent-skills.md) `Demo AWS EC2 Launch`** — gathers the instance configuration, gets a manager's explicit approval of it, then launches the instance through an MCP tool. Its repository is cloned in the background after startup, so the skill shows as `pending` for a moment before it can be used.
- **[Agent skill](../guides/agent-skills.md) `Demo GKE Pod Restart`** — agrees the exact target (project, cluster, namespace, and either a Deployment/StatefulSet name or a single pod name) with the user, gets a manager's explicit approval of that exact target, then, by default, rolling-restarts the workload through the GKE MCP Server — or, when the user wants just one pod gone, deletes that pod so its owning controller recreates it — and reports the outcome. Its repository is cloned the same way, so it also shows as `pending` at first.
- **[MCP server](../guides/mcp-servers.md) `AWS MCP Server`** — a `stdio` server reaching AWS's managed AWS MCP Server, which is where the EC2 tools come from.
- **[MCP server](../guides/mcp-servers.md) `GKE MCP Server`** — a `streamable_http` server reaching Google Cloud's managed GKE (Google Kubernetes Engine) MCP server, the full endpoint. Its `Authorization` header is `Bearer ${gcp-token:demo-gcp-credentials/GOOGLE_CREDENTIALS_JSON}`, so every connection sends a fresh access token minted from the `demo-gcp-credentials` secret, and its tools can manage clusters and their Kubernetes resources, including rolling-restarting a workload or deleting a pod.
- **[Secret](../guides/secrets.md) `demo-aws-credentials`** — the AWS access key id and secret access key the AWS MCP Server reads.
- **[Secret](../guides/secrets.md) `demo-gcp-credentials`** — the Google Cloud credential JSON the GKE MCP Server mints its access token from.
- **[Tool mocks](../guides/tool-mocks.md)** — stubs for the demo run's side-effecting tools: `aws___call_aws` and `aws___run_script` on the AWS MCP Server, each returning a successful launch, `patch_k8s_resource` and `delete_k8s_resource` on the GKE MCP Server, returning a successful rolling restart and a successful pod deletion respectively, and the built-in `request_approval`, returning approved. Selecting them in a draft run's **Run** dialog lets either workflow finish without touching AWS, a real GKE cluster, or waiting on a manager.
- **[Tags](../guides/tags.md)** `AWS` and `GCP` — each an [access-control tag](../guides/tags.md#access-control-tags), so only `Demo AWS Group` / `Demo GCP Group` members (and `admin`, or a super admin) can see the AWS- or GCP-tagged records above. `Approval Required` is a plain tag on both agent skills and restricts nothing.
- **Demo users and groups:**

| User | Role | Access-control group | What they do |
|---|---|---|---|
| `demo-aws-developer` | `developer` | `Demo AWS Group` | Generates the EC2-launch workflow |
| `demo-aws-reviewer` | `reviewer` | `Demo AWS Group` | Publishes the EC2-launch workflow |
| `demo-aws-requester` | `requester` | `Demo AWS Group` | Runs the EC2-launch workflow |
| `demo-gcp-developer` | `developer` | `Demo GCP Group` | Generates the GKE-pod-restart workflow |
| `demo-gcp-reviewer` | `reviewer` | `Demo GCP Group` | Publishes the GKE-pod-restart workflow |
| `demo-gcp-requester` | `requester` | `Demo GCP Group` | Runs the GKE-pod-restart workflow |
| `demo-approver-1`, `demo-approver-2` | `approver` | `Demo Approvers` (both tags) | Approve the launch, or the pod restart |

None of them holds its role directly: each inherits it from a [user group](../guides/users-and-groups.md#user-groups) — `Demo Developers`, `Demo Reviewers`, `Demo Requesters`, and `Demo Approvers`. The AWS and GCP trios each also belong to a second group, `Demo AWS Group` or `Demo GCP Group`, that grants no role of its own — its only purpose is holding the matching access-control tag, so that trio can see the AWS- or GCP-tagged records and everyone else cannot, except `admin` (or a super admin), who [bypasses access-control tags](../guides/tags.md#access-control-tags) entirely and needs no group membership for it. `Demo Approvers` itself carries both the `AWS` and `GCP` access-control tags directly, since an approver is not scoped to one provider — this is also what makes either demo approver an eligible destination for a request addressed to them, whichever of the two demo workflows it comes from.

## Trying it out

The [Walkthrough](./walkthrough.mdx) plays either example through end to end — generate, publish, run, approve, confirm — from a single `root` sign-in, [impersonating](../concepts/impersonation.md) each demo account in turn. Signing in as each account with `DEMO_PASSWORD` works just as well; the table above says who does what.

`Demo AWS Group` and `Demo GCP Group` each see only their own provider's records, so `demo-aws-developer` cannot open `Demo GKE Pod Restart` and `demo-gcp-developer` cannot open `Demo AWS EC2 Launch`. Either approver account works for both examples, since `Demo Approvers` carries both the `AWS` and `GCP` access-control tags directly. A real GKE run needs `DEMO_GCP_CREDENTIALS_JSON` set to a credential whose identity may reach a real GKE cluster.

**No AWS account or GKE cluster?** Do not publish: run the workflow while it is still `draft` — as a `developer`, `demo-aws-developer` (or `demo-gcp-developer` for the GKE story) may do that, and only a draft run's dialog offers the tenant's [tool mocks](../guides/tool-mocks.md). Under **Mock tools**, check the seeded stubs it lists (`aws___call_aws` or `aws___run_script` for the launch, `patch_k8s_resource` or `delete_k8s_resource` for the pod restart, and `request_approval`); the whole workflow then plays through without reaching AWS, a real GKE cluster, or waiting on a human.

## Removing it

Setting `DEMO_DATA=false` (or removing the line) **removes those records again** on the next startup — the flag is declarative in both directions.

Two things survive by design: a demo record something else has come to depend on — a workflow built on the demo skill, for instance — is kept and logged rather than deleted, and a demo user who has created records is soft-deleted so their name still resolves on those records.
