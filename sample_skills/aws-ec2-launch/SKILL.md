---
name: aws-ec2-launch
description: Launch an AWS EC2 instance through a registered MCP tool, gated by a manager's explicit approval. Use this skill whenever the user wants to launch, start, spin up, provision, or create an EC2 instance — including requests phrased as "launch a new EC2 instance", "spin up a t3.medium for the staging environment", "I need an EC2 box for load testing", "provision a new instance in ap-northeast-1", or "start an EC2 server for the demo tomorrow". Also use it when the user describes a need for new AWS compute capacity and the implied action is to create an instance, even if they don't say "EC2" explicitly (e.g. "I need a new server on AWS"). This skill gathers the full instance configuration, obtains a manager's approval before touching any infrastructure, launches the instance through a bound MCP tool, and then asks the user to confirm the result — it never launches anything without both a complete configuration and an explicit approval.
---

# AWS EC2 Launch

Launch an AWS EC2 instance. The core principle: a running instance costs money and adds a target to the account's attack surface, so you **gather the full configuration, get a manager's explicit approval of exactly that configuration, launch it through the bound MCP tool, then ask the user to confirm the result**. Never launch before an approval has come back `approved`.

## Workflow

### 1. Gather the instance parameters

Ask the user for whatever isn't already given. At minimum, you need:

- **AMI** — which image to boot (an AMI id, or a description you can resolve to one, e.g. "latest Amazon Linux 2023").
- **Instance type** — e.g. `t3.medium`.
- **Region** (and availability zone if it matters to them).
- **Key pair** — which key pair to attach for SSH access.
- **Security group(s)** and **subnet/VPC** — where the instance lands on the network.
- **Name** — the `Name` tag, so the instance is identifiable afterward.
- **Count** — how many instances.

Do not guess network- or access-related fields (security group, subnet, key pair) — a wrong choice here can expose the instance publicly or hand it the wrong permissions. Ask instead of defaulting. For a genuinely low-stakes field (e.g. count defaulting to 1), you may propose a default, but say what you're defaulting to and let the user override it.

Once you have everything, summarize the finalized configuration back to the user before moving on. This exact summary is also what goes into the approval request in the next step.

### 2. Get manager approval

This step is mandatory. Before launching anything, get explicit approval from a manager.

Approval can be addressed either to a team or to one named person. Prefer a team, so the launch is not blocked on one manager's availability.

Call `list_user_groups` to find groups that can approve. If there's exactly one, address the request to it. If there's more than one, ask the user which team should approve rather than guessing. If there are none, fall back to `list_users` to find users holding the `approver` role and apply the same rule: exactly one means treat them as the manager, more than one means ask. If neither yields an eligible destination, tell the user no eligible approver exists and stop — do not launch.

Call `request_approval` with a short `title` (e.g. "Launch EC2 instance: `<name>`") and a `description` containing the finalized configuration from step 1, addressed to exactly one destination — `approver_group_id` for a team, or `approver` for one person, never both. Then explain the request to the user in plain text and call `render_approval` with the returned `approval_id` so the approver sees Approve/Reject controls in chat. When the request goes to a team, every eligible member is notified and the first decision from any of them settles it. Wait for the decision (re-check with `get_approval` if needed).

`workflow_task_id` must be the id of the task that **launches** the instance — the one with the EC2 tool bound to it — not this approval step. The approval authorizes only the task it names, and a step whose job is to ask for a go-ahead binds no tools, so naming it would authorize nothing. Call `list_workflow_tasks` to find the launch task's id.

```
list_workflow_tasks()
list_user_groups()
request_approval(title="Launch EC2 instance: <name>", workflow_task_id=<launch_task_id>, approver_group_id=<group_id>, description="<finalized configuration>")
render_approval(approval_id=<approval_id>)
```

If the decision is `approved`, continue to step 3. If it is `rejected`, stop — do not launch anything, and tell the user clearly that the manager declined, including any comment they left.

### 3. Launch the instance

Call `list_mcp_tools` to find the EC2-launch tool bound to this task. Its exact name and input schema depend on which MCP server is registered — do not assume a specific tool name ahead of time. Map the approved configuration from step 1 onto that tool's actual input schema, translating names/units as needed (e.g. "AMI" → the schema's `image_id` field) — use only the fields the schema actually accepts, never fields it doesn't have.

```
list_mcp_tools()
call_mcp_tool(server_id=<server_id>, tool_name=<tool_name>, arguments={...})
```

If the call returns an error (invalid AMI, insufficient permissions, quota exceeded, etc.), report the exact error to the user and stop — do not retry with silently altered parameters or guess a fix.

### 4. Ask the user to confirm the result

Show the user exactly what the tool returned — instance id(s), state, and any other details it reported (IP addresses, etc.). Then explicitly ask the user to confirm the result themselves (e.g. that the instance reaches `running` in the AWS console, or that the details match what they expected) rather than declaring success on their behalf. Wait for their confirmation before closing out.

## Reporting format

Close with a short, factual summary:

```
Launched EC2 instance for <name>.
  Manager approval: approved by <approver>
  Instance: <instance-id>  (state: <state>)
  User confirmed: yes
```

If the manager rejected the request, the launch call failed, or the user's confirmation surfaces a problem, replace the success summary with what happened at that step and state clearly that the instance is not confirmed launched.
