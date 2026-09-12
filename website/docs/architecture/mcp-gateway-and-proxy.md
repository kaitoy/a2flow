---
title: MCP gateway and proxy
sidebar_position: 6
---

# MCP gateway and proxy

The agent never talks to a registered [MCP server](../guides/mcp-servers.md) directly. Every call passes through two things A2Flow owns, and they answer two different questions:

| | MCP gateway | MCP proxy |
|---|---|---|
| **Where it runs** | Inside the agent's process, next to the database | In a separate container, holding none of the agent's secrets |
| **What it settles** | *Whether* a call may happen | *Where* it happens — it starts or connects to the server |
| **What it holds** | Identity, the policy chain, tool mocks, secret expansion, the audit record | One call at a time: the server's address or command, the expanded values, the tool and its arguments |

The gateway is the decision-maker, and the rest of this page is mostly about it. The proxy is the sandbox those decisions are handed to — its own section is [below](#the-sandbox).

## What the gateway decides

![Flowchart of the policy chain deciding a tool call: denied calls are refused with what is allowed, allowed calls are answered from a mock or go through credential injection and the MCP proxy to the MCP server, and both a refusal and a real call produce an audit record.](./img/mcp-gateway-and-proxy-policy-chain.svg#gh-light-mode-only)
![Flowchart of the policy chain deciding a tool call: denied calls are refused with what is allowed, allowed calls are answered from a mock or go through credential injection and the MCP proxy to the MCP server, and both a refusal and a real call produce an audit record.](./img/mcp-gateway-and-proxy-policy-chain-dark.svg#gh-dark-mode-only)

| The gateway owns | What it does |
|---|---|
| **Identity** | Establishes which tenant and which run a call belongs to, from the conversation it arrived on |
| **Authorization** | Consults an ordered chain of policies, any of which may veto |
| **Stubbing** | Answers from a [tool mock](#tool-mocks-and-dry-runs) when the run has one for this tool |
| **Credentials** | Expands the registered server's [secret](./secrets.md) references into a connection, at connect time only |
| **Isolation** | Hands the allowed call to the [MCP proxy](#the-sandbox) that actually runs the server |

## The MCP proxy: where a registered server runs {#the-sandbox}

An MCP server you register is not A2Flow's code. A local one is a program A2Flow starts on your behalf; a remote one is a service A2Flow connects out to. Either way, what it does is outside A2Flow's control once it is running.

So it does not run where A2Flow's own secrets are. The proxy is a sandbox: in a Docker Compose deployment it is the **separate `mcp-proxy` container**, which holds none of the following:

| Not in the proxy | Where it stays |
|---|---|
| The database, and everything recorded in it | With the agent |
| The key that [secrets](./secrets.md) are encrypted under | With the agent |
| The credentials for an external secret store | With the agent |
| The LLM provider's API key | With the agent |
| The [agent skill](../guides/agent-skills.md) repositories | With the agent |

What the proxy gets is one call at a time: the address or command for the one server being reached, the values that server needs — already expanded from your secret references — and the tool and arguments. Nothing else is there to find.

![Architecture diagram showing the MCP gateway, which decides whether a call is allowed, mocked, and which credentials it needs, handing exactly one authorized call across a trust boundary into the MCP proxy, which starts or connects to the real MCP server.](./img/mcp-gateway-and-proxy-trust-boundary.svg#gh-light-mode-only)
![Architecture diagram showing the MCP gateway, which decides whether a call is allowed, mocked, and which credentials it needs, handing exactly one authorized call across a trust boundary into the MCP proxy, which starts or connects to the real MCP server.](./img/mcp-gateway-and-proxy-trust-boundary-dark.svg#gh-dark-mode-only)

**The two ends prove who they are to each other.** The channel between them is encrypted, and neither end accepts an unidentified peer: the proxy refuses a connection from anything that does not hold a certificate this deployment issued. Each individual call additionally carries the [certificate](#who-authorized-a-call) of the task making it, and the proxy checks that certificate again before it reaches anything — that it was issued here, has not expired, belongs to the caller, and covers this exact tool.

That second check is not the same question as the first. Being A2Flow does not mean being authorized to call a given tool, and holding a task's certificate does not mean the request is the one A2Flow sent. Both have to hold, so a request cannot keep a valid authorization while quietly pointing the proxy at a different program.

The proxy is a second line, not the decision-maker. Whether the task is still running, whether the approval still stands, whether the certificate was withdrawn — none of that is answerable there, and all of it stays with the gateway.

## The policy chain

| Order | Policy | What it requires |
|---|---|---|
| 1 | **In-progress tool binding** | The `(server, tool)` pair must be bound to a task the run currently has `in_progress`. Listing what a server advertises is deliberately unrestricted — that is how the design agent decides what to bind |
| 2 | **Tool certificate** | The call must present the task's certificate — see [Who authorized a call](#who-authorized-a-call) — and that certificate's signed grant must cover the tool. There is no exemption: a task no approval covers presents the grant its run's initiator holds |
| 3 | **Approved call** | When an approver's decision is what authorizes the task, the call must match the calls that decision listed — see [The calls a decision covers](./approvals.md#the-calls-a-decision-covers). A tool the decision listed as taking any input passes this rule whatever it carries, having already been stopped by rule 2 until the decision was granted. A task running on its initiator's own grant has no such list and is not checked here |

The chain stops at the first veto and is ordered cheapest first, so a call that already fails the binding rule never pays for a signature check. The last rule runs last for a second reason as well: it is the only one that needs to know *which* task is calling, and the rule before it is what establishes that. It also keeps a caller holding no authority at all from learning what an approver agreed to. Adding a rule means adding a policy to the chain rather than editing the gateway, which is what keeps "what may run" readable as one ordered list.

Refusals are written for the caller rather than for a log: a denied call comes back naming the tools that *are* allowed, so the model can correct itself instead of guessing.

## Who authorized a call {#who-authorized-a-call}

Every tool call a run makes carries a **certificate** naming the person whose authority it runs on. A task is granted one when it is marked **In Progress**; whose authority it carries depends on whether an [approval](./approvals.md) covers it.

| The task | Gets its certificate | On whose authority |
|---|---|---|
| Is covered by an approval — its own, or one requested on a task it follows | when it starts, and only once that approval is granted | the approver who granted it |
| Is covered by none | when it is marked **In Progress** | whoever started the run |

The second row is the ordinary case: nobody was asked to weigh the task, so the person who ran the workflow authorizes the tools it binds, and the audit trail records that in as many words rather than leaving the call unattributed.

Three rules follow, and all are visible to whoever operates a workflow:

- **The tools are fixed when the task starts.** A certificate covers exactly the tools bound to the task at that moment. A workflow that binds a tool to a task only after the task has started finds that tool refused — the design agent is told to bind first, but a hand-edited task can still get this wrong. A task an approval covers cannot have its tools edited at all.
- **Asking for an approval closes the door again.** If an approval is requested that covers a task already running on someone's authority, that authority stands down immediately; the task waits for the decision like any other.
- **Each covered task gets its own certificate.** One approval covering a chain of tasks does not put them all on one clock — each is granted its own when it starts.

## What is recorded

| Recorded per decided call | Deliberately not recorded |
|---|---|
| The tool, the server, and whether it was allowed or denied | The arguments themselves — only a digest of them is kept |
| The refusal reason, when denied — for a call outside what was approved, the input at fault and the bound the approver agreed to | The refused input's actual value |
| The certificate presented, and therefore who authorized the call | |

That record is the run's Tool Invocations page, and it is what makes "who authorized this call" answerable after the fact. The certificates themselves are listed under **Audit Logs → Certificates**, one row per grant.

## Tool mocks and dry runs {#tool-mocks-and-dry-runs}

A [tool mock](../guides/tool-mocks.md) lets a **draft** workflow be exercised end to end without its tools' side effects. What matters here is *where* the stub sits.

![Flowchart showing that a tool mock is consulted only after the same policy chain a production call faces: a denied call is refused exactly as in production, and an allowed call is answered from a mock's next response or the real MCP server.](./img/mcp-gateway-and-proxy-tool-mocks.svg#gh-light-mode-only)
![Flowchart showing that a tool mock is consulted only after the same policy chain a production call faces: a denied call is refused exactly as in production, and an allowed call is answered from a mock's next response or the real MCP server.](./img/mcp-gateway-and-proxy-tool-mocks-dark.svg#gh-dark-mode-only)

The stub is consulted **after** the policy chain, never before it. A dry run therefore rehearses the same authorization a real run faces: the tool must still be bound to a task in progress, and the call must still present that task's certificate. The only thing a mock skips is the part that has an effect outside A2Flow — the proxy is never reached.

Two consequences are worth knowing:

- **Responses follow the call count.** The first response answers the run's first call to that tool, the second its second, and the last one repeats once the list runs out. The counter belongs to the run, so it survives the many requests — and the possible replicas — that one agent run spans.
- **A stubbed call leaves no audit record.** That record is for calls that reached, or were stopped on their way to, a real server; a row for a call that was always going to be answered from a snapshot would misread in either direction. The chat transcript is where a stubbed call is inspected, badged `Mocked`.
