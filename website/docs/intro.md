---
title: Introduction
slug: /intro
sidebar_position: 1
---

# Introduction

A2Flow is a chat application that connects a [Google ADK](https://google.github.io/adk-docs/) agent to a Next.js UI using the [AG-UI protocol](https://docs.ag-ui.com/concepts/events). The agent supports [A2UI](https://a2ui.org/) — when it needs input from the user it renders interactive A2UI input components (text fields, choice pickers, buttons) so the user can see exactly what to provide, while purely informational replies stream token-by-token as Markdown-rendered text so the user never waits on a tool call.

The frontend uses a **glassmorphism** visual style with a **light/dark theme toggle** (persisted in `localStorage`, defaults to the OS preference). See [DESIGN.md](https://github.com/kaitoy/a2flow/blob/master/DESIGN.md) for the full design system reference. A **notification center** in the top toolbar surfaces unread workflow events such as generated drafts and approval requests, with the full history available from a dedicated Notifications page reachable from the account menu (see [Notifications](./guides/notifications.md)); once a Super Admin has configured an SMTP server under [System Settings](./guides/system-settings.md), the same events are also **emailed** to their recipient.

The UI is **responsive**: below the `md` breakpoint every sidebar (chat session list, admin navigation, workflow task timeline) collapses into an off-canvas drawer opened from a hamburger button in the header, layouts use dynamic-viewport heights so mobile URL bars don't clip the chat input, and touch devices get always-visible controls, ~44px tap targets, 16px form fields (no iOS focus zoom), and Enter-as-newline in the chat input.

```
┌──────────────────────────────────┐    AG-UI RunAgentInput (JSON)    ┌──────────────────────┐
│   Next.js frontend               │  (render_a2ui tool injected by   │  FastAPI backend     │
│   @ag-ui/client                  │ ───────────────────────────────► │  Google ADK agent    │
│   @ag-ui/a2ui-middleware         │   A2UIMiddleware)                 │  AGUIToolset         │
│   Redux Toolkit                  │                                   │  DB SessionService   │
│   Admin UI (/admin)              │ ◄─────────────────────────────── │  SQLite/PostgreSQL   │
└──────────────────────────────────┘  AG-UI events (SSE) incl.        └──────────────────────┘
     :3000                            A2UI (TOOL_CALL_*)                    :8000
```

## Where to go next

- **[Quick start](./getting-started/quick-start.md)** — get the backend and the frontend running on your machine.
- **[Terminology](./concepts/terminology.md)** — workflows, design sessions, executions, and workflow sessions.
- **[Workflows](./guides/workflows.md)** — generate a workflow from an agent skill, adjust it, publish it, run it.
- **[Configuration reference](./operations/configuration.md)** — every environment variable the backend reads.
