---
title: Workflows
sidebar_position: 3
---

# Workflows

Navigate to [http://localhost:3000/admin/workflows](http://localhost:3000/admin/workflows) to manage Workflows — reusable units of work that pair an Agent Skill with a **pre-designed task list** (the workflow's *task templates*). A workflow's lifecycle is **generate → adjust → publish → execute**: the task templates are designed and settled *before* any run, so executing a workflow starts working immediately instead of redesigning them every time.

| Operation | Path |
|-----------|------|
| Generate a workflow from a skill | "Generate workflow" on [Agent Skills](./agent-skills.md) — the list's row action or the detail page header's icon button (both calling `POST /agent-skills/{id}/workflows`) |
| List all workflows | `GET /admin/workflows` |
| A workflow's detail page — edit / publish / deactivate / discard changes / open its design session | `GET /admin/workflows/{id}` |
| Manage its task templates | `GET /admin/workflows/{id}/task-templates` |
| Run a workflow | "Run" button in the list (calls `POST /workflows/{id}/execute`) |

Each workflow record stores a name, any [tags](./tags.md) it is classified by, a reference to an Agent Skill, a lifecycle **status** (`generating` / `draft` / `failed` / `published` / `modified`), and two description fields: `generatedDescription` — **summarized from the design conversation** by the AI when the workflow is generated and again whenever a `developer` presses the field's **generate action**, editable directly only by a **Super Admin** — and `description`, a free-form field any `developer` can set to override it. Whichever is non-empty (`description` takes precedence, else `generatedDescription`) is handed to the execution agent as run context. Since the override is usually a hand-edit of the AI's summary, the Description field on the detail page carries a **diff action** opening a dialog with a word-level diff from `generatedDescription` to `description`; it reads the values currently in the form, so unsaved edits are diffed too. Workflows are persisted in `a2flow.db`; there is no bare `POST /workflows` — generation is the only way a workflow is born.

## Generating a workflow

**Generate workflow** is reachable from two places, both opening the same modal dialog without leaving the page: the row action in the [Agent Skills](./agent-skills.md) list, and the Generate Workflow icon button in the header of a skill's detail page. Either is disabled until the skill's clone has published a revision. The dialog asks for the workflow **name** (prefilled with the skill name) and the **prompt** describing the work. Because generating navigates away to the new workflow, the detail page offers to save unsaved edits first — declining the prompt leaves the page untouched and does not generate.

Submitting the dialog:

1. Checks that the skill has a published revision (`commitSha`); otherwise HTTP 409 (`SKILL_NOT_READY`). The new workflow (`status: "generating"`) is registered immediately (HTTP 201), carrying the id of the **design session** it will be designed in and pinned to that revision, and the frontend navigates to the workflow's detail page, which polls while generation runs.
2. A **background design run** sends the prompt as the design session's first chat message and drives an *initial-design* agent: following the skill, it breaks the request into steps and registers them as the workflow's **task templates** in one `register_design_tasks` call (a DAG — each step declares a `key` and its `depends_on` predecessors, plus optional MCP `tools` bindings).
3. When the run finishes, the design conversation is summarized (one LLM call) into the workflow's `generatedDescription`, the status becomes **`draft`**, and a **workflow-draft-ready notification** deep-links back to the workflow. Any failure — an LLM error, or a run that registered no templates — lands on the row as **`failed`** with the reason and raises a **workflow-generation-failed notification**. The reason is shown on the workflow's detail page and as a banner in its design chat, which stays usable: writing the task templates from there (or from the admin template editor) recovers the workflow to **`draft`** and clears the failure, since rebuilding the design is what repairs it.

The prompt itself is not stored on the workflow: it lives on as the first message of the design conversation, and the generated summary carries the intent forward.

## Regenerating the description

The AI summary goes stale as the task templates are adjusted, so the **Generated description** field on the workflow detail page carries a **generate action** (`POST /workflows/{id}/generate-description`, developer-gated) that re-summarizes the design conversation on demand — one LLM call — and saves the result straight away. There is no summarization at publish time: whether and when to refresh the summary is the user's call.

The same action is also reachable from the design session's chat input: its "+" menu (developer-gated, hidden while the workflow's task templates are still generating) offers **Generate description**, which previews the change through the same description-diff dialog as the detail page before it's saved — handy for regenerating without leaving the conversation.

A `published` workflow becomes `modified` when the summary is rewritten, since a run whose `description` is empty falls back to it and would otherwise drift from the published version. The action returns HTTP 409 (`WORKFLOW_DESCRIPTION_NOT_GENERATABLE`) while generation is still in flight or when there is no design conversation to summarize, and HTTP 502 (`SUMMARIZATION_FAILED`) if the LLM call fails.

## Adjusting the task templates

A draft's task templates can be refined in two ways, in any mix:

- **By chat** — the workflow detail page's **Open design session** button opens `/admin/workflows/{workflowId}/design-session` (the chat has no id of its own, so it is addressed by its workflow): the same chat UI as a run, with the template list down the left edge, driven by an interactive *design* agent whose tools (`register_design_tasks`, `create_design_task`, `list_design_tasks`, `get_design_task`, `update_design_task`, `delete_design_task`) edit the workflow's templates directly. The design agent never executes anything. The design session is shared by every **Developer** in the tenant (plus Super Admins and the workflow's `createdBy`), so a team can refine a design together: it reuses the shared chat plumbing (history poll, A2UI surfaces, per-message sender avatars), and two people hitting send at once collide on the same run lock a workflow session uses.
- **By hand** — the **Task Templates** admin pages (`/admin/workflows/{id}/task-templates`) offer the familiar Table / Graph views (the Graph stacks the templates in one vertical column in dependency order, each branching rightward into the MCP servers it binds tools from and then into the individual tools) plus a create form and a per-template detail page with **Depends on** and **MCP Tools** pickers, backed by `GET /workflows/{id}/task-templates` and the `POST`/`PATCH`/`DELETE /workflow-task-templates` endpoints (developer-gated).

Templates mirror session tasks structurally — title, description, DAG edges (`workflow_task_template_dependencies`), and MCP tool bindings (`workflow_task_template_tool_bindings`, server side `RESTRICT`) — but carry **no status**: the lifecycle belongs to a run, not the design. The same DAG rules apply (same-workflow targets, cycles rejected with HTTP 409 `DEPENDENCY_CYCLE`).

## Publishing

**Publish** (on the workflow detail page, `POST /workflows/{id}/publish`, developer-gated) is what makes a workflow executable. It requires at least one template (and no generation in flight) — otherwise HTTP 409 (`WORKFLOW_NOT_RUNNABLE`). Publishing **freezes the design**: the workflow's name, effective description (`description` if set, else `generatedDescription`), and full template list (edges and tool bindings included) are captured as its published version, replacing the previous one. No LLM runs here — refreshing the AI summary is a [separate, user-triggered action](./workflows.md#regenerating-the-description). Re-adjust → re-publish is allowed at any time; runs already started are unaffected because they copied the task templates (below).

## Editing a published workflow — `modified`

Editing a workflow after it has been published does not silently change what runs. Saving the detail form, regenerating its AI description, or adding / editing / deleting one of its **task templates**, moves the workflow to **`modified`**:

- Runs keep using the **last published version** — its name, effective description, and templates — not the edits.
- The workflow stays runnable by anyone who could run it while `published`; the Run button in the list is not gated differently.
- **Publish** again to promote the edits into future runs.
- **Discard changes** (the undo icon that appears in the detail page's status bar next to Publish, `POST /workflows/{id}/discard-changes`, developer-gated) throws the edits away instead: the task templates are rewritten from the published version — original template ids reused, so the dependency edges survive — the name is restored and the published version's frozen effective description is written back into the workflow's `description` field (`generatedDescription` is left untouched), and the workflow returns to `published`. Discarding a workflow that has no unpublished changes returns HTTP 409 (`WORKFLOW_NOT_MODIFIED`).

Refining the task templates through the **design chat** counts as an edit too: when the design agent adds, changes, or removes a task template of a `published` workflow, the workflow moves to `modified` exactly as a manual edit would.

## Deactivating a workflow

**Deactivate** (the power-off icon that appears in the detail page's status bar next to Publish whenever the workflow is `published` or `modified`, `POST /workflows/{id}/deactivate`, developer-gated) returns a workflow to **`draft`**. This revokes the `requester` role's execute access — the same gate a never-published workflow starts under — while a `developer`/`super_admin` can still run it for testing and the task templates, both description fields, and published snapshot are left exactly as they were. Publishing again promotes it straight back to `published`. Deactivating a workflow that is not currently `published`/`modified` returns HTTP 409 (`WORKFLOW_NOT_DEACTIVATABLE`).

## Running a workflow

Clicking **Run** on a **published** or **modified** workflow — or, for a `developer`/`super_admin` caller, a **draft** one too, for pre-publish testing — creates a **WorkflowExecution** — an independent entity that captures a snapshot of the workflow configuration at execution time.

For a **draft** workflow the Run dialog additionally lists the tenant's [tool mocks](./tool-mocks.md); checking one stubs that tool for this run, so a pre-publish test can be repeated without the tool's side effects. The dialog offers no mocks for a published workflow, and asking for one anyway is rejected with HTTP 409 (`WORKFLOW_NOT_RUNNABLE`) — a published run that quietly did nothing would be worse than no run.

1. The backend rejects any other status outright, and rejects a `draft` workflow for any caller who isn't `developer`/`super_admin`, with HTTP 409 (`WORKFLOW_NOT_RUNNABLE`); it also re-checks the skill's published revision (`SKILL_NOT_READY` otherwise) — the repository was cloned when the skill was registered, so **nothing is cloned here**.
2. A `WorkflowExecution` record is persisted, capturing the workflow name, its effective description (`description` if the user set one, else the AI-generated `generatedDescription`), skill details, the id of the **workflow session** it will run in, and the skill revision the run is **pinned** to (`agentSkillCommitSha`). If the workflow was still `draft` at this point — a pre-publish test run — the record is flagged `isDraft: true`, which keeps it out of the [operations metrics](../operations/metrics.md); the flag never changes afterwards. The workflow's task templates are **copied into the execution as `pending` WorkflowTasks** (dependency edges and tool bindings included, ids remapped), so later template edits never affect this run. For a `modified` workflow the name, description, and templates all come from its **last published version** rather than the edited rows. Any [tool mocks](./tool-mocks.md) chosen for the run are **copied onto the record** at the same time — by value, not by reference — so editing or deleting a mock afterwards cannot change how this run behaves. The ADK session itself is created lazily on the first agent call.
3. The backend returns the `WorkflowExecution` (HTTP 201). The frontend redirects to `/workflow-executions/{workflowExecution.id}/session` — the **workflow session**, the chat the run happens in. It has no record of its own, so it is addressed by its execution's id.
4. On mount, that page fetches the `WorkflowExecution`, and if no prior messages exist it auto-sends a fixed kickoff message via `POST /workflow-executions/{id}/agent`. The page renders the same shared app bar as the regular chat (notification bell, theme toggle, and account menu), with the workflow name shown beside the title; its **A2Flow** logo links to the [welcome page](./admin-ui.md#welcome-page).
5. The `/workflow-executions/{id}/agent` endpoint loads the skill-bound `ADKAgent` (keyed by `agent_skill_id`, the pinned revision, **and the agent role**) and streams AG-UI SSE events back, identical to the regular `POST /agent` endpoint. The agent runs under an **execute-only** instruction — the tasks were approved by publishing, so it **begins immediately**, with the execution's effective description injected server-side as trusted run context.
6. Subsequent user messages continue to flow through `POST /workflow-executions/{id}/agent`, so A2UI rendering, A2UI user actions (e.g. clicking a rendered button), and the full chat experience work normally.

### Agent-managed execution

The execution agent works through the pre-copied WorkflowTasks: it lists the tasks, picks the next runnable one (a `pending` task whose dependencies are all `completed`), marks it `in_progress`, does the work per the skill, and marks it `completed` (or `failed` / `skipped`). When every task reaches a terminal state, a **session-completed notification** is raised. Five tools back this — `create_workflow_task`, `list_workflow_tasks`, `get_workflow_task`, `update_workflow_task`, and `delete_workflow_task` — which resolve the current session from the ADK session id and operate on the same `WorkflowTask` records exposed by the REST API (so the agent can still adjust the run's task list mid-flight when needed). You can watch the statuses update live in the read-only **Workflow Tasks** admin view (Table or Graph). See [backend/README.md](https://github.com/kaitoy/a2flow/blob/master/backend/README.md#agent-task-tools) for the tool reference.

### MCP tools for tasks

WorkflowTasks can use tools from the MCP servers registered in the [MCP Servers](./mcp-servers.md) admin page:

1. **Bind at design time** — while designing, the agent calls `list_mcp_tools`, which queries every registered server concurrently and returns each server's advertised tools (unreachable servers are reported per-server without failing the listing). Steps that need an external tool get a `tools` entry (`[{"server_id": …, "tool_name": …}]`) in `register_design_tasks`; bindings are persisted on the templates and copied onto the run's tasks at execute time, surfaced as `toolBindings` on the REST read models.
2. **Enforce at execution time** — the agent invokes bound tools through the `call_mcp_tool(server_id, tool_name, arguments)` proxy. Every such call goes through A2Flow's own MCP proxy layer, which resolves who is calling, consults its access-control policies, expands the server's secret references, and only then opens a per-call connection to the server — a streamable HTTP request, or a freshly spawned child process for a stdio server. Its first policy is the binding check: the `(server, tool)` pair must be bound to a task currently `in_progress` in the session (the union of bindings when several are in progress). Calls to unbound tools are rejected with an error listing the allowed tools, so a shared, skill-cached agent can never use tools a task wasn't granted. The proxy exists as a layer of its own so that authentication and finer-grained access control can be added in one place later; see [backend/README.md](https://github.com/kaitoy/a2flow/blob/master/backend/README.md#mcp-proxy).

Bound tools appear as chips in the **Tools** column of the Task Templates and Workflow Tasks lists. The template forms include an **MCP Tools** picker that works in two steps, like the Agent Skill auth-password picker: choose a server through a paged dialog, then add one of its tools from a dropdown, each added tool becoming a removable chip. Only the chosen server is queried live, so opening the form costs one plain registry read rather than a connection to every registered server; a server that cannot be reached says so in place of its tool list, and an already-bound tool keeps its chip either way.

Both of those lists show **every** record instead of paginating, which lets the **Depends on** column work as a cross-reference: each dependency is named by its title, and hovering that chip highlights the depended-on task's own row. The design agent is held to terse imperative task titles — 2–4 words, 30 characters — so they read cleanly as chips; its task tools reject a longer one with a message telling it to move the detail into the description. (The limit binds the agent, not people: a title edited through the admin form is still allowed the full 200 characters.) A title that still overflows its chip is clipped and revealed in full on hover.

Workflow executions are independent of regular chat sessions — deleting a workflow does not affect existing `WorkflowExecution` records (the `workflow_id` FK is set to `NULL` on delete, but the snapshot data remains). Deleting a workflow **does** delete its task templates and published version (cascade), and with the row goes the design session it named.

The individual tasks of a run are persisted as `WorkflowTask` records. Each task carries a status (`pending` / `in_progress` / `completed` / `failed` / `skipped`); tasks are listed in `createdAt` order. See [backend/README.md](https://github.com/kaitoy/a2flow/blob/master/backend/README.md#workflow-tasks) for the API reference. Deleting a `WorkflowExecution` cascades to its tasks.

Tasks form a **directed acyclic graph (DAG)** rather than a flat list: each task may depend on zero or more other tasks in the same session via its `dependsOnIds` field (`(task, dependsOn)` edges are stored in the `workflow_task_dependencies` join table). Dependency targets must exist and belong to the same session (otherwise HTTP 422 `FOREIGN_KEY_VIOLATION`), and edges that would introduce a cycle — including a self-dependency — are rejected with HTTP 409 `DEPENDENCY_CYCLE`. Deleting a task cascades to the dependency edges that reference it in either direction.
