---
title: Terminology
sidebar_position: 1
---

# Terminology

The concepts that carry most of the domain, worth keeping straight:

| Term | What it is |
|---|---|
| **[Workflow](../guides/workflows.md)** | A reusable, pre-designed unit of work: an agent skill plus the task templates generated for it. |
| **Design session** | The chat in which a workflow's task templates are produced and refined. Exactly one per workflow, and it exists before any run does. |
| **[Workflow execution](../guides/workflow-executions.md)** | One run of a workflow: the workflow and skill metadata snapshotted at run time, and the parent of the run's `WorkflowTask`s, `Approval`s, and message metadata. |
| **Workflow session** | The chat that one workflow execution happens in — the run-time counterpart of a design session. |
| **[Tenant](./tenants.md)** | The top-level organizational boundary: nearly every record belongs to exactly one, and no request crosses from one into another. |
| **[User group](../guides/users-and-groups.md#user-groups)** | A named bundle of users within a tenant, carrying a set of roles that every member inherits. |
| **[Tag](../guides/tags.md)** | A tenant-wide label for classifying secrets, MCP servers, agent skills, and workflows — one vocabulary shared by all four. |
| **[Agent Skill](../guides/agent-skills.md)** | A `SKILL.md` procedure in a Git repository, versioned like code; a workflow is generated from one, and a run executes its published revision. |
| **[MCP server](../guides/mcp-servers.md)** | A registered Model Context Protocol server whose tools the agent can bind to a workflow's tasks. |
| **[Secret](../guides/secrets.md)** | A named bundle of key/value credential entries, referenced elsewhere as `name/key` and resolved lazily at use time. |
| **[Approval certificate](../guides/approvals.md#human-approval)** | The short-lived X.509 certificate minted when an approval is granted; it freezes the task's tool set at the moment of decision, and the MCP proxy refuses any tool call that does not present it, signed. |
