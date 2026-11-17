---
title: Dashboard
sidebar_position: 16
---

# Dashboard

The dashboard shows how your tenant's workflows are running right now: what is in flight, what is waiting for an approval, what failed, and how long runs take from start to finish. Open **Dashboard** at the top of the admin sidebar.

It is built to be left open: every figure re-reads itself every 15 seconds. It comes in two views, and your browser remembers which one you chose. The standard view looks like the rest of the app and follows your light or dark theme. The Mission Control view is made for a wall display: it stays dark whichever theme the rest of the app is in, its figures glow, and something on it is always moving.

Two kinds of run are left out of every figure: test runs started from a workflow that is still a draft, and runs that an [access-control tag](./tags.md#access-control-tags) hides from you.

To see the dashboard filled in before your tenant has run anything, turn on the [demo data](../getting-started/demo-data.md): it comes with about ninety days of made-up runs.

## The toolbar {#the-toolbar}

| Control | What it does |
|---|---|
| **Live** | The dot shows that the figures are current. In the Mission Control view it pulses, and the ring around it empties as the next reading approaches. It changes to **Connection lost** when a reading fails: the figures on screen are then the last ones read, and the dashboard keeps trying. |
| **7 days** / **30 days** / **90 days** | Sets the period covered by **Lead time**, **Runs by workflow** and **Needs attention**. The tiles and the other panels always show the present. |
| **Refresh** | Reads everything again now. |
| **Switch to Mission Control view** | Changes to the Mission Control view. **Switch to standard view** changes back. Both views show the same figures. |
| **Enter full screen** | Fills the screen with the dashboard alone. Press Esc, or **Exit full screen**, to return. |

## The tiles {#the-tiles}

Each tile is one number, a supporting line, and a trace of how the number has moved since you opened the page. In the Mission Control view the number flares briefly whenever it changes.

| Tile | The number | The line under it | Its color changes |
|---|---|---|---|
| **Active runs** | Runs in progress, scheduled ones included | Runs started in the last 24 hours | Never |
| **Pending approvals** | Approval requests awaiting a decision | Approvals decided today | To amber when any has waited over 24 hours |
| **Finished today** | Runs that finished today | The share that completed without a failed task | Never |
| **Failed runs, last 24h** | Runs that finished in failure in the last 24 hours | Tasks that failed in the same period | To red when it is above zero |
| **Email queue** | [Notification emails](./notifications.md#the-delivery-queue) not yet sent | How long the oldest has waited, or how many failed to send | To amber when the oldest has waited over five minutes, to red when any failed |

"Today" starts at midnight in the server's time zone — see [Server settings](../operations/configuration.md#server-settings).

## The panels {#the-panels}

| Panel | What it shows | How to read it |
|---|---|---|
| **Lead time** | The average time from a run's start to its finish, for each day runs finished. The figure in the corner is the average over the whole period. | Hover the chart, or focus it and press the arrow keys, to read one day. A day on which nothing finished has no point. |
| **Approval backlog** | Every pending approval. The ring's amber arc is the share that has waited over 24 hours. Below it are the five longest waits. | Switch between **Approver** and **Workflow** to see who, or which workflow, the approvals are waiting on. A bar turns amber once one of its approvals has waited over 24 hours. |
| **Runs by workflow** | The eight busiest workflows in the period, by runs started. Each bar is split into **completed**, **failed** and **running**. | The figure at the end of a row is its run count, beside the workflow's average lead time. Hover a segment for its count. |
| **Failure causes** | The tasks that failed in the last 24 hours, by the cause recorded with each. | The legend names every cause present and its count. |
| **Needs attention** | The runs with a failed task in the period, newest first, each with its cause. Shown to an Admin only. | Click a run to open it, and scroll the strip sideways to see the rest. In the Mission Control view the strip scrolls by itself and stops while the pointer is on it. |

## Who sees it {#who-sees-it}

**Dashboard** is in the sidebar for Admin, Developer, Requester and Approver. Everyone sees the same figures for the tenant; only **Needs attention** is kept to an Admin, because it quotes task names and failure causes from runs the viewer may not be part of.

To chart the same figures in a monitoring tool of your own instead, see [Operations metrics](../operations/metrics.md).
