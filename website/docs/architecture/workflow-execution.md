---
title: Running a workflow
sidebar_position: 3
---

# Running a workflow

Running a workflow does not point a run at the workflow. It **copies** the published design onto a new [workflow execution](../guides/workflow-executions.md), and that record is what the run lives in from then on.

![Flowchart showing a published Workflow and its chosen tool mocks copied onto a new Workflow execution snapshot, which opens a Workflow session with all tasks pending at the start.](./img/workflow-execution-snapshot.svg#gh-light-mode-only)
![Flowchart showing a published Workflow and its chosen tool mocks copied onto a new Workflow execution snapshot, which opens a Workflow session with all tasks pending at the start.](./img/workflow-execution-snapshot-dark.svg#gh-dark-mode-only)

| Copied onto the run | Taken from |
|---|---|
| Name and effective description | The last published version — or the current rows, for a workflow still in `draft`, or when a Developer chose to run a `modified` workflow's [unpublished edits](../guides/workflows.md#trying-the-edits-out) |
| Tasks, all `pending`, with their dependencies and tool bindings | The same design's task templates |
| The agent skill revision the run follows | The skill's published revision at that moment |
| The chosen [tool mocks](./mcp-gateway-and-proxy.md#tool-mocks-and-dry-runs), by value | The mocks as they read at that moment |

Nothing in that list is read back from its source later. Editing the workflow, pulling the skill, or deleting either never reaches into a run already under way — and a finished run stays readable after the workflow it came from is gone.

## How the run advances

The workflow session opens with a fixed kickoff message and the execution agent already working. Publishing was the approval of the plan, so there is nothing to confirm before starting.

![Flowchart of the run-advancement loop: list the run's tasks, pick one whose dependencies have completed, mark it in progress, do the work, mark it completed, failed, or skipped, and loop, or settle once every task has ended.](./img/workflow-execution-run-loop.svg#gh-light-mode-only)
![Flowchart of the run-advancement loop: list the run's tasks, pick one whose dependencies have completed, mark it in progress, do the work, mark it completed, failed, or skipped, and loop, or settle once every task has ended.](./img/workflow-execution-run-loop-dark.svg#gh-dark-mode-only)

A run ends `completed` when every task reached a terminal status with no failure among them, and `failed` when at least one failed. The statuses can be watched live in the run's read-only task view, as a table or as the dependency graph.

When a task fails, every task still waiting on it — directly or further down the chain — is set to `skipped`, because it can no longer run. That is what lets the run settle as `failed` instead of waiting forever on a task that will never start. Tasks on other branches that do not depend on the failed one keep running as normal.

## Why in_progress matters

Marking a task `in_progress` is not bookkeeping. It is what unlocks that task's tools: the [gateway](./mcp-gateway-and-proxy.md) allows a call only when the tool is bound to a task the run currently has in progress. A task that has ended can no longer act, and one not yet started never could.

The run's task list and every task's tool bindings are fixed when the run starts — copied from the workflow's published design — and the agent only advances statuses. It cannot add, remove, or re-bind a task. That is also why an [approval](./approvals.md) does not re-read a task's bindings when it matters: it signs the set it saw at the moment the approver decided, so no later change to the workflow can widen a grant already given.
