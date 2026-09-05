---
name: aws-ec2-launch
description: Launch an AWS EC2 instance, gated by a manager's explicit approval. Use this skill whenever the user wants to launch, start, spin up, provision, or create an EC2 instance — including requests phrased as "launch a new EC2 instance", "spin up a t3.medium for the staging environment", "I need an EC2 box for load testing", "provision a new instance in ap-northeast-1", or "start an EC2 server for the demo tomorrow". Also use it when the user describes a need for new AWS compute capacity and the implied action is to create an instance, even if they don't say "EC2" explicitly (e.g. "I need a new server on AWS"). This skill gathers the full instance configuration, obtains a manager's approval before touching any infrastructure, launches the instance, and then asks the user to confirm the result — it never launches anything without both a complete configuration and an explicit approval.
---

# AWS EC2 Launch

Launch an AWS EC2 instance. The core principle: a running instance costs money and adds a target to the account's attack surface, so you **gather the full configuration, get a manager's explicit approval of exactly that configuration, launch it, then ask the user to confirm the result**. Never launch before an approval has come back approved.

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

Once you have everything, summarize the finalized configuration back to the user before moving on. This exact summary is also what the approver decides on in the next step.

### 2. Get manager approval

This step is mandatory. Before any infrastructure is touched, a manager must explicitly approve the configuration from step 1 — not the idea of a launch, that exact configuration.

Address the request to a **team** of managers rather than to one named person whenever you can, so the launch is not blocked on one person's availability. Name a single person only when the decision genuinely belongs to them.

The request needs a short title naming the instance (e.g. "Launch EC2 instance: `<name>`") and a body carrying the finalized configuration verbatim, so the approver decides on exactly what will be launched. Tell the user in plain text that the request has gone out and who it went to.

Then wait for the decision. If it comes back approved, continue to step 3. If it comes back rejected, stop — launch nothing — and tell the user the manager declined, including any comment they left. If there is nobody who can approve, stop as well and say so: an unapproved launch is not an option.

### 3. Launch the instance

Launch exactly the configuration that was approved. Nothing may change between the approval and the launch; if something has to change, go back to step 2 and have the new configuration approved.

Whatever you launch through may name its fields differently from the terms used here, so map the approved configuration onto the names and units it actually accepts (e.g. "AMI" onto an `image_id` field) and pass only the fields it accepts.

If the launch returns an error (invalid AMI, insufficient permissions, quota exceeded, etc.), report the exact error to the user and stop — do not retry with silently altered parameters or guess a fix.

### 4. Ask the user to confirm the result

Show the user exactly what came back — instance id(s), state, and any other details reported (IP addresses, etc.). Then explicitly ask the user to confirm the result themselves (e.g. that the instance reaches `running` in the AWS console, or that the details match what they expected) rather than declaring success on their behalf. Wait for their confirmation before closing out.

## Reporting format

Close with a short, factual summary:

```
Launched EC2 instance for <name>.
  Manager approval: approved by <approver>
  Instance: <instance-id>  (state: <state>)
  User confirmed: yes
```

If the manager rejected the request, the launch failed, or the user's confirmation surfaces a problem, replace the success summary with what happened at that step and state clearly that the instance is not confirmed launched.
