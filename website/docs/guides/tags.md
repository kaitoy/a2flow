---
title: Tags
sidebar_position: 10
---

# Tags

Navigate to [http://localhost:3000/admin/tags](http://localhost:3000/admin/tags) to curate the tenant's **tags** — the labels [secrets](./secrets.md), [MCP servers](./mcp-servers.md), [agent skills](./agent-skills.md), and [workflows](./workflows.md) are classified by. One tag set is shared by all four, so a `aws` tag narrows secrets and MCP servers alike.

| Operation | Path |
|-----------|------|
| List all tags | `GET /admin/tags` |
| Create a new tag | `GET /admin/tags/new` |
| A tag's detail page — rename / recolor / delete | `GET /admin/tags/{id}` |

Each tag stores a **name** (unique within its tenant) and a **color** picked from a fixed eight-slot palette (see [DESIGN.md](https://github.com/kaitoy/a2flow/blob/master/DESIGN.md#colors)) — an arbitrary color value is rejected. Writes require `admin` **or** `developer`, matching the union of roles that can write to any of the four taggable resources, so a tag can always be minted by whoever is about to need it. Reads stay open like every other section.

**Renaming is safe at any time.** Records reference a tag by its id, never its name, so every record carrying it follows the new name with nothing to re-sync — which is the whole reason tags are registered up front instead of typed free-form on each record. **Deleting** a tag, conversely, removes it from every record that carried it rather than being blocked by them; the confirmation says so.

**Attaching tags.** Each taggable resource's create and detail form carries a **Tags** picker, shaped like the [user group](./users-and-groups.md#user-groups) picker: the current selection shows as removable colored chips above a **Select tags…** button, so the field stands as tall as the selection rather than as tall as the vocabulary. The button opens a dialog holding the whole vocabulary as a wrapping grid of colored chips, each one a toggle — a pressed chip takes a stronger fill *and* a leading check, so the state never rests on color alone. Two filters narrow the grid and compose: a name box, and a row of the eight palette swatches, any number of which can be pressed at once (pressing them all off is the cleared state). The choice is a draft until **Select** confirms it; **Cancel** discards it. A tag selected and then filtered out of view stays selected. Attachment is a sub-resource of the record — `PUT /api/v1/{resource}/{id}/tags` with `{"tagIds": [...]}`, replacing the set wholesale — gated by that resource's own write role, independent of whatever minted the tag itself. Creating a tagged record is therefore a create followed by that call; editing writes it only when the selection actually changed.

**Filtering by tag.** Every taggable list has a **Tags** column showing each record's chips, and its column header menu offers a multi-select. The selection is **conjunctive** — a record must carry *every* tag picked, so adding one narrows the result — which the menu states as "Filter (all of)". It is applied server-side through a repeatable `?tag=<id>` query parameter (see [.claude/rules/api-conventions.md](https://github.com/kaitoy/a2flow/blob/master/.claude/rules/api-conventions.md)), so it covers the whole dataset rather than the current page. Tags are a separate axis from the other column filters: hiding the Tags column through the column picker clears the tag filter, exactly as hiding any other column clears its own.
