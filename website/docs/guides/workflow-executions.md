---
title: Workflow Executions
sidebar_position: 4
---

# Workflow Executions

Navigate to [http://localhost:3000/admin/workflow-executions](http://localhost:3000/admin/workflow-executions) to browse every `WorkflowExecution`. Each row links to its workflow session (`/workflow-executions/{id}/session`) and to the nested **Workflow Tasks** admin page (`/admin/workflow-executions/{id}/workflow-tasks`), a **read-only** view of the run's tasks — the task templates are edited on the workflow's [task templates](./workflows.md#adjusting-the-task-templates), and a run's statuses are advanced by the execution agent (and the approval flow), so a run's history stays faithful to what actually ran. A **Draft** column badges runs started from a still-`draft` workflow ([pre-publish test runs](./workflows.md#running-a-workflow), left out of the [operations metrics](../operations/metrics.md)) and doubles as a Yes/No filter to hide them; the same badge shows next to the status on the execution's detail page. A row's **Delete** action removes the `WorkflowExecution` after a confirmation prompt: the record, its tasks (cascade), and its workflow session are all deleted. The Workflow Tasks page offers a **Table / Graph** toggle: the Graph view renders the task DAG with [React Flow](https://reactflow.dev/), stacking the tasks in a single vertical column in dependency order so prerequisites sit above the tasks that depend on them, with each task branching rightward into the MCP servers it binds tools from and then into the individual tools (read-only; pan / zoom / fit).

| Operation | Path |
|-----------|------|
| List all executions | `GET /admin/workflow-executions` |
| Delete an execution | `DELETE /api/v1/workflow-executions/{id}` |
| View an execution's tasks | `GET /admin/workflow-executions/{id}/workflow-tasks` |
| View an execution's MCP tool calls | `GET /admin/workflow-executions/{id}/tool-invocations` |

A **Tool Invocations** page (`/admin/workflow-executions/{id}/tool-invocations`, reached from the run's detail header) lists the MCP tool calls the [proxy](https://github.com/kaitoy/a2flow/blob/master/backend/README.md#mcp-proxy) decided on for that run — `allowed` ones that went upstream and `denied` ones a policy vetoed — with the tool, the server, the denial reason, and the presented certificate. Arguments appear only as a digest; the raw values are never stored. A call to a [mocked](./tool-mocks.md) tool is absent here whichever way it went: the proxy checks it like any other call, but a call that was always going to be answered from a snapshot reached no server, so neither its approval nor its refusal is recorded. The run's chat transcript is where a stubbed call is inspected. A **Mocked** badge on the run marks one that stubbed any of its tools.

A run also carries a **lifecycle** of its own: it starts `running` and reaches `completed` or `failed` — with a `finishedAt` timestamp — once it has at least one task and every task has reached a terminal state (`completed` / `failed` / `skipped`). A run whose tasks include a failure ends `failed`. This is evaluated after every task write, whether the write came from the execution agent or from the REST task endpoints, and the recorded `finishedAt` is never moved by a later edit. A run with no tasks at all stays `running`. These fields are server-managed — they cannot be set through the API — and are what the [operations metrics](../operations/metrics.md) count.
