---
title: Tags
sidebar_position: 10
---

# Tags

Tags are the labels records are classified by. One vocabulary is shared by all six taggable registries, so an `aws` tag narrows secrets and MCP servers alike.

![Flowchart showing one shared tag vocabulary per tenant applied to six taggable registries: Secrets, MCP Servers, Agent Skills, Workflows, Tool Mocks, and User Groups.](./img/tags-vocabulary.svg#gh-light-mode-only)
![Flowchart showing one shared tag vocabulary per tenant applied to six taggable registries: Secrets, MCP Servers, Agent Skills, Workflows, Tool Mocks, and User Groups.](./img/tags-vocabulary-dark.svg#gh-dark-mode-only)

Open **Tags** in the admin sidebar to curate the vocabulary. Each tag has a **Name**, unique within the tenant, an optional **Description**, a **color** picked from a fixed eight-slot palette — an arbitrary color value is refused — and an **Access control** checkbox, off by default, that turns the tag from a plain label into a gate (see [Access-control tags](#access-control-tags)).

Creating a tag requires `admin` **or** `developer`, matching the union of the roles that can write to any of the six taggable resources, so a tag can always be minted by whoever is about to need it. The one exception is the **Access control** checkbox: only an Admin (or Super Admin) can tick or untick it. A Developer sees the flag as a fixed value on the form and can still create the tag or edit its other fields. Reads stay open like every other section.

## Attaching tags to a record

Every taggable record's create form and detail page carries a **Tags** picker: the current selection shows as removable colored chips above a **Select tags…** button, so the field stands as tall as the selection rather than as tall as the vocabulary.

1. Click **Select tags…**. The dialog shows the whole vocabulary as a wrapping grid of colored chips, each one a toggle. A pressed chip takes a stronger fill *and* a leading check, so its state never rests on color alone.
2. Narrow the grid if you need to. Two filters compose: a name box, and a row of the eight palette swatches, any number of which can be pressed at once. Pressing them all off is the cleared state.
3. Confirm with **Select**, or throw the draft away with **Cancel**. A tag you selected and then filtered out of view stays selected.

Attaching tags is gated by the record's own write role, independent of whatever minted the tag itself.

## Filtering by tag

Every taggable list has a **Tags** column showing each record's chips, and its column header menu offers a multi-select. The column keeps every row one line tall: it shows as many chips as its current width holds and counts the rest in a trailing `+N` chip. Click that chip to open a dialog listing every tag on the record, each showing its description on hover. Widen the column, by dragging its edge or by hiding another column, and the counted tags come back as chips. The selection is **conjunctive** — stated in the menu as "Filter (all of)" — so a record must carry *every* tag you pick, and adding one narrows the result. It applies across the whole dataset, not just the page on screen.

Tags are a separate axis from the other column filters, but they follow the same rule about visibility: hiding the Tags column through the [column picker](./admin-ui.md) clears the tag filter, exactly as hiding any other column clears its own.

## Access-control tags {#access-control-tags}

A tag with **Access control** ticked restricts who can see the records it is attached to. Its chip carries a lock glyph wherever it appears — in the Tags list's **Preview** column, in a record's **Tags** column, and in the picker — and the Tags list gains an **Access control** column you can filter on.

Access is decided by your [user groups](./users-and-groups.md#user-groups): a group carries tags of its own, and the tags of all your groups are pooled together.

| A record carries… | You see it when… |
|---|---|
| No access-control tag (only plain tags, or none) | Always — plain tags never restrict anything |
| One or more access-control tags | Your groups, between them, carry **every** one of them |

A record you may not see is simply absent: it is not in the list, and opening a direct link to it says it was not found. An Admin or a Super Admin sees everything: an Admin is exempt from every access-control tag, and a Super Admin is additionally platform-wide and belongs to no group, so no other rule could reach it either.

One guard rail applies when tagging: **you cannot attach an access-control tag your groups do not carry.** The save is rejected with an error, since it would hide the record from you on your next page load. Ask an admin to add you to a group carrying the tag first. Tagging a *user group* is exempt — that is how an admin grants access in the first place.

The restriction is about who can open, edit, run, or delete a record. What a record uses behind the scenes is untouched: a workflow still runs with the agent skill it was generated from and the secrets its MCP servers reference, even for a requester who could not open that skill or secret themselves.

## Workflow execution and approval tags {#execution-and-approval-tags}

A [workflow execution](./workflow-executions.md) shows a **Tags** column and field too, and so does the [approval](./approvals.md) it belongs to — but read-only, and outside the six taggable registries above. When a run starts, it copies the tags its workflow carries at that moment; retagging the workflow afterwards, or deleting it, never changes what an already-started run shows. There is no **Tags** picker on these two screens and no tag filter on their lists — attaching and detaching tags stays on the workflow itself.

An access-control tag copied this way still gates the run and its approvals, exactly as it gates the workflow: if your groups no longer carry a tag the run copied, both the run and every approval under it disappear from your lists and your direct links — even if you started the run yourself or are its designated approver. The same applies to everything you could do inside the run: sending a message in its chat, opening its tasks, and approving or rejecting an approval under it all fail as if the run did not exist. Only an Admin or a Super Admin is exempt, as with any access-control tag. The tag has to be attached to the workflow *before* it runs; retagging the workflow afterwards never reaches runs already started, since the copy happens once, at the moment the run begins.

## Renaming and deleting

**Renaming is safe at any time.** Records reference a tag by identity, never by its name, so every record carrying it follows the new name with nothing to re-sync — which is the whole reason tags are registered up front instead of typed free-form on each record.

**Deleting** a tag works the other way round: rather than being blocked by the records that carry it, it is removed from all of them. The confirmation says so.
