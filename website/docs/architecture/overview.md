---
title: How it works
sidebar_position: 1
---

# How it works

A2Flow turns an [Agent Skill](../guides/agent-skills.md) into a workflow whose steps are settled before anything runs, and then executes that workflow inside a chat the agent and the people involved share. Each stage hands the next one a frozen copy of what came before, so a run stays faithful to what was published even after the design moves on.

```mermaid
flowchart LR
  S["Agent Skill<br/>a Git repository"] -->|"Generate workflow"| W["Workflow<br/>task templates and tool bindings"]
  W -->|"Publish, then Run"| X["Workflow execution<br/>a snapshot of the design"]
  X --> C["Workflow session<br/>the chat the run happens in"]
  C --> T["Tasks<br/>one at a time"]
  T -->|"needs a person"| A["Approval gate"]
  T -->|"needs a tool"| P["MCP proxy"]
  A -->|"issues a certificate"| P
  P --> M["MCP server"]
```

| Stage | What happens | Read on |
|---|---|---|
| **Design** | A skill becomes a workflow: an AI design run breaks the request into steps and binds the tools each step needs. | [Designing a workflow](./workflow-design.md) |
| **Run** | Running a workflow copies the published design onto a new workflow execution and opens its chat. | [Running a workflow](./workflow-execution.md) |
| **Converse** | The agent and several people share that chat, and the agent can draw interactive surfaces into it rather than only writing text. | [Sessions](./sessions.md) |
| **Approve** | A task that needs a human decision cannot act until someone decides, and the decision is signed into a certificate. | [Approval gate](./approvals.md) |
| **Act** | Every tool call is decided by a policy chain before it leaves A2Flow, and recorded once it has been. | [MCP proxy](./mcp-proxy.md) |

Behind all of it sit two stores: the [database](./database.md) every record lives in, and the [secret storage](./secrets.md) credentials are resolved from.

## The two chats

A2Flow has exactly two kinds of chat. They are the same machinery pointed at different agents, and the difference between them is what each agent is allowed to do.

| Chat | Driven by | What it may do |
|---|---|---|
| **Design session** | The design agent, following the skill | Writes and rearranges the workflow's task templates. Executes nothing. |
| **Workflow session** | The execution agent, following the skill revision the run is pinned to | Works through the run's tasks, asks for approvals, and calls MCP tools. |

Neither chat is a record of its own. A design session is addressed by its workflow and a workflow session by its workflow execution, and the conversation behind it is created on first use and kept under that id — so reopening either continues where it left off.
