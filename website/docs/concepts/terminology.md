---
title: Terminology
sidebar_position: 1
---

# Terminology

Four terms carry most of the domain, and two of them are chats. They are worth
keeping straight:

| Term | What it is | Stored as |
|---|---|---|
| **Workflow** | A reusable, pre-designed unit of work: an agent skill plus the task templates generated for it. | `workflows` |
| **Design session** | The chat in which a workflow's task templates are produced and refined. Exactly one per workflow, and it exists before any run does. | No table of its own: it is the ADK session named by `Workflow.sessionId`, so its workflow's id identifies it. |
| **Workflow execution** | One run of a workflow: the workflow and skill metadata snapshotted at run time, and the parent of the run's `WorkflowTask`s, `Approval`s, and message metadata. | `workflow_executions` |
| **Workflow session** | The chat that one workflow execution happens in — the run-time counterpart of a design session. | No table of its own: it is the ADK session named by `WorkflowExecution.session_id`, so its execution's id identifies it. |
| **User group** | A named bundle of users within a tenant, carrying a set of roles that every member inherits. | `user_groups`, with membership in `user_group_members` |

So a design session designs a workflow, and a workflow session runs one.
Neither chat is an entity in its own right, so each is addressed by the
record it belongs to — a design session by its workflow, a workflow session
by its execution — and each borrows that record's id as its own address. Their
URLs diverge, though: a design session lives inside the admin UI, at
`/admin/workflows/{workflowId}/design-session` alongside that workflow's other
admin views, while a workflow session lives outside it, at a top-level
`/workflow-executions/{executionId}/session` distinct from that execution's
admin view at `/admin/workflow-executions/{executionId}`. A design session's
owner is its workflow's `createdBy` — the user who generated it — exactly as a
workflow session's is its execution's `initiatorId`. Both chats are **shared**,
and keying the ADK session by that owner is what makes sharing work: everyone
who enters lands in the one conversation instead of forking a private copy. Who
may enter differs — a design session admits the tenant's Developers, a workflow
session admits its execution's designated approvers — but both record who sent
each message, so the chat shows every participant's avatar.
