---
title: Admin UI
sidebar_position: 1
---

# Admin UI

The admin area lives at [http://localhost:3000/admin](http://localhost:3000/admin).

## Welcome page

[http://localhost:3000/admin](http://localhost:3000/admin) is the welcome landing page. It renders inside the admin shell (sidebar + app bar) and greets the user with quick-action cards that link to a new chat (Super Admin only — see [Chat session access](../concepts/authorization.md)) and each admin section the user's roles allow. This is where the user lands when visiting the site root (`/`), after signing in, and when clicking the **A2Flow** logo in the app bar from any screen.

Every admin list table shares interactive features: **per-column sorting and filtering** (applied server-side via the list APIs' `s` and `q` query parameters, so they cover the whole dataset rather than just the current page), **drag-to-resize column widths** (kept for the session, not persisted), and **hover tooltips** that reveal the full text of any cell clipped to its column width.

Where a record has a **detail page**, the list's identifier column links to it. That page is the one screen for the record: its attributes plus every action it supports — saving edits, deleting it, and whatever else the record type offers (publishing a workflow, pulling a skill's repository). A detail page is titled with the **record's own name** rather than with the operation, and the breadcrumb trail above the title ends on that same name, so the path reads `Admin › Workflows › my-workflow` and every crumb before the last links back up. [Workflow executions](./workflow-executions.md) are the exception: a run is a history rather than a record to edit, so its row opens its workflow session or its read-only task list instead.

Each table also has a **column picker** — the ▥ button next to Refresh — listing every column the table can show, with a "Show all" / "Hide all" bulk toggle and a "Reset to default" action. The panel always fits the screen: it opens above the button when there is no room below, scrolls its column list internally while keeping the bulk toggle and the reset action in view, and splits into two columns once the table has more than eight toggleable ones — so even the widest list (agent skills, at seventeen columns) stays fully reachable on a short laptop screen. Each table ships a default set, and some columns (an MCP server's transport, a secret's reference, an agent skill's ref and revision, a user's email and verification flag) start hidden so the columns that matter most get the width. The identifier column and the Actions column are always shown and are not listed. Choices are remembered per table in the browser's local storage, so they survive a reload; only the departures from the defaults are stored, which keeps a table's later columns arriving at their intended default. Hiding a column that a sort or filter is currently using clears that sort or filter, so the rows on screen are never ordered or narrowed by a criterion nothing on the page can show.

## List query parameters

Every collection endpoint accepts a shared set of `limit` / `offset` / sort (`s`) / filter (`q`) query parameters, with camelCase field names. See [.claude/rules/api-conventions.md](https://github.com/kaitoy/a2flow/blob/master/.claude/rules/api-conventions.md) for the full reference.
