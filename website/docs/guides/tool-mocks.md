---
title: Tool Mocks
sidebar_position: 8
---

# Tool Mocks

Navigate to [http://localhost:3000/admin/mcp-tool-mocks](http://localhost:3000/admin/mcp-tool-mocks) to manage **tool mocks** — stand-ins that let a **draft** workflow run be exercised end to end without its tools' side effects. A mocked tool is not called: the mock's configured result is returned instead, so no request reaches the MCP server, no approval is recorded, and nobody is emailed.

Mocking is chosen **per tool**, not per run, because a dry run is only useful if it stays realistic. A workflow that searches a system and then writes to it can stub only the write — the read still hits the real server, and the agent still reasons over real data. For the same reason a mock buys past the side effect but not past the rules: a mocked MCP call is still checked against the tools the run's current task is allowed to use, and against any approval that task is waiting on, so a workflow that would be refused in production is refused in its dry run too.

A mock targets either one tool of a [registered MCP server](./mcp-servers.md) or a **built-in** A2Flow tool (currently `request_approval` alone — the one whose side effects otherwise need a human to clear before the run can continue).

Its **responses** are an ordered list indexed by call ordinal: the first answers the run's first call to that tool, the second its second, and so on; once the list runs out the last response repeats, so a single response behaves as a constant. That is what lets one mock express a scenario rather than a fixed value — approve the first request, reject the second, and see how the workflow handles both. Each response is one of:

| Kind | Meaning |
|---|---|
| `structured` | A JSON object placed in the result's `structuredContent` — for a tool whose caller reads fields off the result |
| `text` | A string placed in the result's textual content |
| `error` | A message returned as a failed call, so the agent sees the tool report an error |

Mocks are applied by **checking them in the Run dialog** of a draft workflow (see [Running a workflow](./workflows.md#running-a-workflow)); the dialog offers no mocks for a published one. Starting the run **copies** what each chosen mock currently says onto the execution, so editing or deleting a mock afterwards never changes a run already under way — and can never silently turn a stubbed call back into a real one.

What a mocked call sent and returned is visible in the run's chat transcript: its tool line expands to show the arguments and the result, badged **Mocked**. It deliberately does not appear on the run's [Tool Invocations](./workflow-executions.md) page — that page records the decisions the MCP proxy actually made, and a stub never reaches it.

A mocked `request_approval` still validates its destination — a mock skips the side effects, not the checks — so a workflow naming an ineligible approver fails in a dry run exactly as it would for real.

| Operation | Path |
|-----------|------|
| List tool mocks | `GET /admin/mcp-tool-mocks` |
| Create a tool mock | `GET /admin/mcp-tool-mocks/new` |
| Edit or delete a tool mock | `GET /admin/mcp-tool-mocks/{id}` |
