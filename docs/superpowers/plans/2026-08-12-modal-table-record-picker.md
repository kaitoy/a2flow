# Modal Table Record Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the checkbox-list membership pickers (`GroupPicker`, `UserPicker`) with a chip field that opens a modal dialog containing a server-paginated, sortable, filterable table.

**Architecture:** A shared `Dialog` shell is extracted from the four hand-written modals first. On top of it, `RecordPickerDialog` drives `DataTable` + `useTableQuery` + `PaginationControls` inside a modal, and `RecordPickerField` renders the current selection as removable `Chip`s plus a button that opens it. `GroupPicker` and `UserPicker` become thin wrappers, exactly as they are over `AsyncCheckboxPicker` today. A new `GET /api/v1/users/{userId}/groups` endpoint replaces the full-list scan the user detail page uses to discover a user's groups.

**Tech Stack:** Next.js 16 / React / TypeScript / Tailwind v4 / `@react-spring/web` / Vitest + Testing Library + MSW on the frontend; FastAPI / SQLModel / pytest on the backend.

**Design spec:** `docs/superpowers/specs/2026-08-12-modal-table-record-picker-design.md`

## Global Constraints

- All documentation, comments, and commit messages are written in **English** (`CLAUDE.md`).
- Every new or modified module, class, function, exported component, type, and interface carries a doc comment: Google-style docstrings in Python, JSDoc in TypeScript. A change without it is not done.
- The `PostToolUse` hook runs Ruff + mypy on `backend/` and Biome on `frontend/` after every `Write`/`Edit`. Fix everything it reports before moving on.
- Biome's hook strips unused imports and rewrites `import { X }` to `import type { X }`. Always add an import and the code using it in the **same** edit call.
- Never run Biome through the Bash tool (`npx biome` silently no-ops there). Use the PowerShell tool.
- Before committing frontend work, run `npx biome ci src` from `frontend/` through the PowerShell tool — `biome ci` errors on unused `biome-ignore` suppressions that the `biome check` hook does not report.
- `git commit` triggers lefthook's pre-commit hook, which runs the full backend and frontend suites. Give the Bash tool `timeout: 300000` for every commit step.
- Do not add an Alembic migration. This change touches no schema.
- `backend/openapi.yaml` and `frontend/src/generated/` are gitignored. They are regenerated, never committed.

---

### Task 1: Extract the shared `Dialog` shell and migrate `ConfirmDialog`

`ConfirmDialog`, `RegistrySearchDialog`, `GenerateWorkflowDialog`, and `DescriptionDiffDialog` each hand-write the same portal + backdrop + focus-trap + spring-animation shell. This task extracts it and converts the simplest caller.

**Files:**
- Create: `frontend/src/components/ui/dialog.tsx`
- Create: `frontend/src/components/ui/dialog.test.tsx`
- Modify: `frontend/src/components/ui/confirm-dialog.tsx` (whole file)

**Interfaces:**
- Consumes: `useDialogA11y` from `@/hooks/useDialogA11y`, `useMotionConfig` from `@/lib/motion`.
- Produces: `Dialog`, `DialogProps`, `DialogSize` from `@/components/ui/dialog`. The panel gets `id={panelId}`, and its `<h2>` gets `id={`${panelId}-title`}`, which `aria-labelledby` points at.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/ui/dialog.test.tsx`:

```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { Button } from "./button";
import { Dialog } from "./dialog";

/** Wraps {@link Dialog} with a real trigger so focus restoration is testable. */
function TriggerHarness({ footer }: { footer?: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        open dialog
      </button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        panelId="test-dialog"
        title="Pick a thing"
        description="Choose carefully."
        footer={footer}
      >
        <button type="button">body button</button>
      </Dialog>
    </>
  );
}

describe("Dialog", () => {
  it("renders nothing until it is opened", () => {
    render(<TriggerHarness />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("names the panel by its title and shows the description", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness />);

    await user.click(screen.getByText("open dialog"));

    const dialog = await screen.findByRole("dialog", { name: "Pick a thing" });
    expect(within(dialog).getByText("Choose carefully.")).toBeInTheDocument();
    expect(dialog).toHaveAttribute("id", "test-dialog");
  });

  it("moves focus into the panel on open", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness />);

    await user.click(screen.getByText("open dialog"));

    const dialog = await screen.findByRole("dialog");
    await waitFor(() =>
      expect(within(dialog).getByRole("button", { name: "body button" })).toHaveFocus()
    );
  });

  it("closes and restores focus on Escape", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness />);

    await user.click(screen.getByText("open dialog"));
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.getByText("open dialog")).toHaveFocus());
  });

  it("closes when the backdrop is clicked", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness />);

    await user.click(screen.getByText("open dialog"));
    await screen.findByRole("dialog");

    const backdrop = document.querySelector('button[aria-hidden="true"]');
    if (!backdrop) throw new Error("backdrop button not found");
    await user.click(backdrop);

    await waitFor(() => expect(screen.getByText("open dialog")).toHaveFocus());
  });

  it("renders the footer below the body", async () => {
    const user = userEvent.setup();
    render(
      <TriggerHarness
        footer={
          <Button type="button" variant="ghost">
            Cancel
          </Button>
        }
      />
    );

    await user.click(screen.getByText("open dialog"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test --run src/components/ui/dialog.test.tsx`
Expected: FAIL — cannot resolve `./dialog`.

- [ ] **Step 3: Implement `Dialog`**

Create `frontend/src/components/ui/dialog.tsx`:

```tsx
/**
 * @module Dialog — the shared modal shell every dialog in the app is built on.
 *
 * Collects what {@link ConfirmDialog}, {@link RegistrySearchDialog},
 * {@link GenerateWorkflowDialog}, and {@link DescriptionDiffDialog} each used to
 * hand-write: a portal to `document.body`, a scrim that closes on click without
 * stealing focus, the fade/scale transition, the `useDialogA11y` focus trap, and
 * a labelled `role="dialog"` panel. Callers supply only their own body.
 */
"use client";

import { animated, useTransition } from "@react-spring/web";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { useDialogA11y } from "@/hooks/useDialogA11y";
import { useMotionConfig } from "@/lib/motion";

/** Maximum width of the dialog panel. */
export type DialogSize = "sm" | "md" | "lg" | "xl";

/** Tailwind max-width utility per {@link DialogSize}. */
const SIZE_CLASS: Record<DialogSize, string> = {
  sm: "max-w-sm",
  md: "max-w-lg",
  lg: "max-w-2xl",
  xl: "max-w-5xl",
};

/** Props for {@link Dialog}. */
export interface DialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Called when the dialog requests to close (backdrop or Escape). */
  onClose: () => void;
  /** DOM id of the panel; its title element derives `${panelId}-title`. */
  panelId: string;
  /** Heading text, and the panel's accessible name. */
  title: string;
  /** Sentence rendered under the heading. */
  description?: string;
  /** Maximum panel width. Defaults to `"md"`. */
  size?: DialogSize;
  /** Cap the panel at 80vh and lay it out as a column so a body child can scroll. */
  scrollable?: boolean;
  /** Action row rendered below the body, right-aligned. */
  footer?: ReactNode;
  /** Extra classes merged onto the panel. */
  panelClassName?: string;
  /** The dialog body. */
  children?: ReactNode;
}

/**
 * Modal dialog with a backdrop, focus trap, Escape handling, and enter/leave
 * animation.
 *
 * Outside-click closing is handled by the backdrop button rather than
 * `useDialogA11y`'s pointerdown listener, so the two never race; the hook is
 * still what traps Tab, closes on Escape, and restores focus to the trigger.
 * The backdrop is `aria-hidden` — it is decorative, and every dialog offers its
 * own labelled way out.
 */
export function Dialog({
  open,
  onClose,
  panelId,
  title,
  description,
  size = "md",
  scrollable = false,
  footer,
  panelClassName,
  children,
}: DialogProps) {
  const config = useMotionConfig("gentle");
  const transitions = useTransition(open, {
    from: { opacity: 0, scale: 0.94 },
    enter: { opacity: 1, scale: 1 },
    leave: { opacity: 0, scale: 0.96 },
    config,
  });

  useDialogA11y({ open, onClose, panelId, closeOnOutsideClick: false });

  // Guard against SSR — createPortal needs document.body, which is not
  // available during Next.js prerendering.
  if (typeof document === "undefined") return null;

  return createPortal(
    transitions(
      (style, item) =>
        item && (
          <div className="fixed inset-0 z-50">
            <animated.button
              type="button"
              style={{ opacity: style.opacity }}
              className="absolute inset-0 h-full w-full cursor-default border-0 bg-black/25 backdrop-blur-[2px]"
              onClick={onClose}
              // Stop the backdrop itself from taking focus on click, so the
              // a11y hook's close handler always restores focus to the
              // trigger instead of leaving it on this transient scrim.
              onMouseDown={(e) => e.preventDefault()}
              tabIndex={-1}
              aria-hidden="true"
            />
            <div className="relative flex min-h-full items-center justify-center p-4 pointer-events-none">
              <animated.div
                id={panelId}
                tabIndex={-1}
                role="dialog"
                aria-modal="true"
                aria-labelledby={`${panelId}-title`}
                style={{
                  opacity: style.opacity,
                  transform: style.scale.to((s) => `scale(${s})`),
                }}
                className={[
                  "w-full rounded-2xl glass-panel-overlay p-6 pointer-events-auto",
                  SIZE_CLASS[size],
                  scrollable ? "flex max-h-[80vh] flex-col" : "",
                  panelClassName ?? "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <h2
                  id={`${panelId}-title`}
                  className={`font-display text-lg font-semibold tracking-tight text-on-surface ${
                    description ? "mb-1" : "mb-4"
                  }`}
                >
                  {title}
                </h2>
                {description && (
                  <p className="mb-4 text-sm text-on-surface-variant">{description}</p>
                )}
                {children}
                {footer && <div className="mt-4 flex items-center justify-end gap-2">{footer}</div>}
              </animated.div>
            </div>
          </div>
        )
    ),
    document.body
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && pnpm test --run src/components/ui/dialog.test.tsx`
Expected: PASS (6 tests).

- [ ] **Step 5: Rewrite `ConfirmDialog` on top of `Dialog`**

Replace the whole of `frontend/src/components/ui/confirm-dialog.tsx`:

```tsx
/** @module ConfirmDialog — modal asking the operator to confirm a destructive or irreversible action. */
"use client";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";

/** Props for {@link ConfirmDialog}. */
interface ConfirmDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Heading naming the action. */
  title: string;
  /** Sentence spelling out what confirming does. */
  description: string;
  /** Called when the operator confirms. */
  onConfirm: () => void;
  /** Called on Cancel, Escape, or a backdrop click. */
  onCancel: () => void;
  /** Label for the confirm button. Defaults to `"Delete"`. */
  confirmLabel?: string;
  /** Style variant for the confirm button. Defaults to `"danger"`. */
  confirmVariant?: "danger" | "primary" | "secondary";
}

/** Modal confirmation dialog with focus trap, keyboard navigation, and backdrop. */
export function ConfirmDialog({
  open,
  title,
  description,
  onConfirm,
  onCancel,
  confirmLabel = "Delete",
  confirmVariant = "danger",
}: ConfirmDialogProps) {
  return (
    <Dialog
      open={open}
      onClose={onCancel}
      panelId="confirm-dialog"
      title={title}
      description={description}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant={confirmVariant} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    />
  );
}
```

- [ ] **Step 6: Run the confirm-dialog tests**

Run: `cd frontend && pnpm test --run src/components/ui/confirm-dialog.test.tsx`
Expected: PASS (6 tests). The panel id, backdrop `aria-hidden`, and button order are all preserved, so no test change should be needed. If one fails, fix the component rather than the test — the DOM contract must not change here.

- [ ] **Step 7: Run every suite that renders a ConfirmDialog**

Run: `cd frontend && pnpm test --run`
Expected: PASS. List pages and detail pages all mount `ConfirmDialog`.

- [ ] **Step 8: Lint**

Run (PowerShell tool, from `frontend/`): `npx biome ci src`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/ui/dialog.tsx frontend/src/components/ui/dialog.test.tsx frontend/src/components/ui/confirm-dialog.tsx
git commit -m "Extract the shared Dialog shell and build ConfirmDialog on it"
```

---

### Task 2: Migrate the remaining three dialogs onto `Dialog`

**Files:**
- Modify: `frontend/src/components/admin/registry-search-dialog.tsx:110-234` (the `createPortal` return)
- Modify: `frontend/src/components/admin/generate-workflow-dialog.tsx:104-203` (the `createPortal` return)
- Modify: `frontend/src/components/admin/description-diff-dialog.tsx:137-221` (the `createPortal` return)

**Interfaces:**
- Consumes: `Dialog` from `@/components/ui/dialog` (Task 1).
- Produces: nothing new. The three components keep their existing props and panel ids.

Each migration deletes the same block — the `useMotionConfig`/`useTransition` pair, the `useDialogA11y` call, the SSR guard, the `createPortal` wrapper, the backdrop button, the centering `<div>`, the `animated.div` panel, and the `<h2>`/description — and keeps the body verbatim inside `<Dialog>`. Drop the now-unused imports (`animated`, `useTransition`, `createPortal`, `useDialogA11y`, `useMotionConfig`) in the same edit.

- [ ] **Step 1: Migrate `RegistrySearchDialog`**

Replace its `return createPortal(...)` block with:

```tsx
  return (
    <Dialog
      open={open}
      onClose={onClose}
      panelId="registry-search-dialog"
      title="Browse MCP Registry"
      description="Search the official MCP registry by name. Only servers A2Flow can register are shown: those reachable over streamable HTTP, and those published as an npm or PyPI package it can launch over stdio."
      size="lg"
      scrollable
      footer={
        <Button variant="ghost" onClick={onClose}>
          Cancel
        </Button>
      }
    >
      <Input
        value={term}
        onChange={(e) => setTerm(e.target.value)}
        placeholder="e.g. github, weather, search…"
        aria-label="Search the MCP registry"
      />

      <div className="mt-4 flex-1 overflow-y-auto">
        {/* body unchanged: the EmptyState / <ul> of servers and the Load more button */}
      </div>
    </Dialog>
  );
```

Keep the contents of `<div className="mt-4 flex-1 overflow-y-auto">` exactly as they are today (the `servers.length === 0` ternary and the `cursor && (...)` Load-more block). Remove the trailing `<div className="mt-4 flex justify-end">` that held Cancel — it is now the `footer`.

- [ ] **Step 2: Run its tests**

Run: `cd frontend && pnpm test --run src/components/admin/registry-search-dialog.test.tsx`
Expected: PASS.

- [ ] **Step 3: Migrate `GenerateWorkflowDialog`**

Its Cancel and Generate buttons live inside the `<form>` that owns submit, so they stay in the body and no `footer` is passed. The panel's conditional `live-edge` class becomes `panelClassName`.

```tsx
  return (
    <Dialog
      open={open}
      onClose={onClose}
      panelId="generate-workflow-dialog"
      title="Generate Workflow"
      description="A design agent follows this skill to break the prompt into the workflow's task list. The draft is registered right away and generation continues in the background."
      // Signature "live edge" while the design run is being handed to the agent.
      // Gated on the 200ms `pending` stage so a fast registration never flashes
      // the light.
      panelClassName={save.status === "pending" ? "live-edge" : undefined}
    >
      <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5">
        {/* body unchanged: both FormFields and the Cancel / Generate row */}
      </form>
    </Dialog>
  );
```

- [ ] **Step 4: Run its tests**

Run: `cd frontend && pnpm test --run src/components/admin/generate-workflow-dialog.test.tsx`
Expected: PASS.

- [ ] **Step 5: Migrate `DescriptionDiffDialog`**

```tsx
  return (
    <Dialog
      open={open}
      onClose={onClose}
      panelId="description-diff-dialog"
      title="Description diff"
      description="Changes the description makes to the generated description."
      size="lg"
      scrollable
      // Signature "live edge" — matches the streaming chat bubbles — while the
      // server is still summarizing the design conversation into the generated
      // description.
      panelClassName={loading ? "live-edge" : undefined}
      footer={
        <Button variant="ghost" onClick={onClose}>
          Close
        </Button>
      }
    >
      {/* body unchanged: the loading / emptyDescription / !changed / diff ternary */}
    </Dialog>
  );
```

The `emptyDescription` computation stays above the `return`. Remove the trailing `<div className="mt-4 flex justify-end">` that held Close.

- [ ] **Step 6: Run its tests**

Run: `cd frontend && pnpm test --run src/components/admin/description-diff-dialog.test.tsx`
Expected: PASS.

- [ ] **Step 7: Run the full frontend suite**

Run: `cd frontend && pnpm test --run`
Expected: PASS.

- [ ] **Step 8: Lint**

Run (PowerShell tool, from `frontend/`): `npx biome ci src`
Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/admin/registry-search-dialog.tsx frontend/src/components/admin/generate-workflow-dialog.tsx frontend/src/components/admin/description-diff-dialog.tsx
git commit -m "Build the remaining dialogs on the shared Dialog shell"
```

---

### Task 3: Add `GET /api/v1/users/{userId}/groups` and its client binding

The user detail page currently discovers a user's groups by fetching every group in the tenant and scanning `memberIds`. This endpoint replaces that scan.

**Files:**
- Modify: `backend/repositories/user_group.py` (Protocol + `SqlUserGroupRepository`)
- Modify: `backend/services/user_group.py`
- Modify: `backend/routers/user.py`
- Modify: `backend/tests/test_user_groups.py`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/test/msw/handlers.ts`

**Interfaces:**
- Produces:
  - `SqlUserGroupRepository.list_for_user(user_id: str) -> list[UserGroupRead]`
  - `UserGroupService.groups_for_user(user_id: str) -> list[UserGroupRead]`
  - `GET /api/v1/users/{user_id}/groups` → `ApiResponse[list[UserGroupRead]]`
  - `getUserGroupsForUser(userId: string): Promise<UserGroup[]>` in `frontend/src/lib/api.ts`

- [ ] **Step 1: Write the failing backend tests**

Append to `backend/tests/test_user_groups.py`:

```python
# ---------- membership read from the user side ----------


async def test_groups_for_user_returns_the_groups_they_belong_to(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    await _create(client, name="Developers", memberIds=["alice"])
    await _create(client, name="Approvers", roles=["approver"], memberIds=["bob"])

    groups = assert_ok(await client.get("/api/v1/users/alice/groups", headers=ADMIN))

    assert [group["name"] for group in groups] == ["Developers"]
    assert groups[0]["memberIds"] == ["alice"]


async def test_groups_for_user_is_readable_without_the_admin_role(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    await _create(client, memberIds=["carol"])

    groups = assert_ok(await client.get("/api/v1/users/carol/groups", headers=NOBODY))

    assert [group["name"] for group in groups] == ["Developers"]


async def test_groups_for_user_is_empty_when_they_belong_to_none(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env
    await _create(client, memberIds=["alice"])

    groups = assert_ok(await client.get("/api/v1/users/bob/groups", headers=ADMIN))

    assert groups == []


async def test_groups_for_user_404s_for_a_user_of_another_tenant(
    group_env: tuple[AsyncClient, AsyncEngine],
) -> None:
    client, _ = group_env

    response = await client.get("/api/v1/users/outsider/groups", headers=ADMIN)

    assert_err(response, 404, "NOT_FOUND")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd backend && uv run pytest tests/test_user_groups.py -k groups_for_user -v`
Expected: FAIL with 405 or 404 responses — the route does not exist yet.

- [ ] **Step 3: Add `list_for_user` to the repository**

In `backend/repositories/user_group.py`, add to the `UserGroupRepository` Protocol, directly after the `group_ids_for_user` declaration:

```python
    async def list_for_user(self, user_id: str) -> _GroupList: ...
```

And to `SqlUserGroupRepository`, directly after `group_ids_for_user`:

```python
    async def list_for_user(self, user_id: str) -> _GroupList:
        """Return this tenant's groups that ``user_id`` belongs to.

        The membership counterpart of :meth:`list`, used by the user detail
        page so it never has to page through every group looking for one
        member.

        Args:
            user_id: Identifier of the user whose memberships to list.

        Returns:
            The groups, ordered by name, each with its membership attached.
        """
        stmt = (
            select(UserGroup)
            .join(
                UserGroupMember,
                onclause=col(UserGroup.id) == UserGroupMember.group_id,
            )
            .where(
                col(UserGroupMember.user_id) == user_id,
                col(UserGroup.tenant_id) == self._tenant_id,
            )
            .order_by(col(UserGroup.name))
        )
        groups = list((await self._db.exec(stmt)).all())
        members = await self._members_for_many([g.id for g in groups])
        return [
            UserGroupRead.from_group(g, member_ids=members.get(g.id, []))
            for g in groups
        ]
```

- [ ] **Step 4: Add `groups_for_user` to the service**

In `backend/services/user_group.py`, directly after `group_ids_for_user`:

```python
    async def groups_for_user(self, user_id: str) -> _GroupList:
        """Return the acting tenant's groups a user belongs to.

        Args:
            user_id: Identifier of the user whose memberships to list.

        Returns:
            The groups, ordered by name, each with its membership attached.
        """
        return await self._repo.list_for_user(user_id)
```

- [ ] **Step 5: Add the route**

In `backend/routers/user.py`, add `UserGroupRead` to the `models.user_group` import and insert the route immediately **before** `set_user_groups`:

```python
@router.get("/{user_id}/groups", response_model=ApiResponse[list[UserGroupRead]])
async def list_groups_for_user(
    user_id: str,
    service: UserServiceDep,
    group_service: UserGroupServiceDep,
    acting_user: CurrentUserDep,
    meta: ApiMetaDep,
) -> ApiResponse[list[UserGroupRead]]:
    """Return the acting tenant's groups the given user belongs to.

    The read counterpart of ``PUT /users/{user_id}/groups``. Reads are open to
    any authenticated caller, as everywhere else, but the user is resolved
    through :class:`~services.user.UserService` first, so a target in another
    tenant reads as 404 rather than confirming that it exists.
    """
    user = await service.get(user_id, acting_user=acting_user)
    groups = await group_service.groups_for_user(user.id)
    return ApiResponse(meta=meta, data=groups)
```

- [ ] **Step 6: Run the backend tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_user_groups.py -v`
Expected: PASS, including the four new tests.

- [ ] **Step 7: Type-check the backend**

Run: `cd backend && uv run mypy .`
Expected: no errors. (The `PostToolUse` mypy hook misreports on some paths; this full run is the authority.)

- [ ] **Step 8: Regenerate the OpenAPI spec and the frontend bindings**

```bash
cd backend && uv run python -m scripts.export_openapi
cd ../frontend && pnpm openapi-ts
```

Expected: `backend/openapi.yaml` contains a `/api/v1/users/{user_id}/groups` GET, and `frontend/src/generated/api/zod.gen.ts` gains a matching response schema export.

- [ ] **Step 9: Find the generated schema's exact export name**

Run: `cd frontend && grep -n "UsersUserIdGroupsGet" src/generated/api/zod.gen.ts`
Expected: one export, most likely `zListGroupsForUserApiV1UsersUserIdGroupsGetResponse`. **Use whatever the grep prints** — the generated names embed the full URL path and the operation id, so they change if either does.

- [ ] **Step 10: Add the client binding**

In `frontend/src/lib/api.ts`, add the schema name from Step 9 to the `@/generated/api/zod.gen` import and add this function next to `listUserGroups`:

```ts
/**
 * Fetch the acting tenant's user groups a given user belongs to.
 *
 * The read counterpart of {@link setUserGroups}. Membership is not carried on
 * the user record, so this is how a user-side screen learns which groups to
 * show without paging through every group in the tenant.
 */
export async function getUserGroupsForUser(userId: string): Promise<UserGroup[]> {
  return fetchEnvelope(
    apiClient.get(`/api/v1/users/${encodeURIComponent(userId)}/groups`),
    zListGroupsForUserApiV1UsersUserIdGroupsGetResponse
  ) as Promise<UserGroup[]>;
}
```

- [ ] **Step 11: Add the MSW handler**

In `frontend/src/test/msw/handlers.ts`, next to the existing `http.put(...users/:userId/groups...)` line:

```ts
  http.get(`${BASE}/api/v1/users/:userId/groups`, () => envelope([USER_GROUP_1])),
```

- [ ] **Step 12: Verify the frontend still builds and passes**

```bash
cd frontend && pnpm build
cd frontend && pnpm test --run
```
Expected: both succeed. A "module not found" on `zod.gen` means the name from Step 9 was transcribed wrong.

- [ ] **Step 13: Commit**

```bash
git add backend/repositories/user_group.py backend/services/user_group.py backend/routers/user.py backend/tests/test_user_groups.py frontend/src/lib/api.ts frontend/src/test/msw/handlers.ts
git commit -m "Add an endpoint listing the groups a user belongs to"
```

---

### Task 4: Give `Chip` a remove button and `Checkbox` a hidden-label mode

Two small primitive extensions the picker needs. Both props are optional, so no existing caller changes.

**Files:**
- Modify: `frontend/src/components/ui/chip.tsx`
- Modify: `frontend/src/components/ui/chip.test.tsx`
- Modify: `frontend/src/components/ui/checkbox.tsx`
- Modify: `frontend/src/components/ui/checkbox.test.tsx`

**Interfaces:**
- Produces: `Chip` accepts `onRemove?: () => void`; `Checkbox` accepts `labelHidden?: boolean`.

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/components/ui/chip.test.tsx`:

```tsx
  it("renders no remove button without onRemove", () => {
    render(<Chip label="Developers" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("calls onRemove when its remove button is pressed", async () => {
    const onRemove = vi.fn();
    const user = userEvent.setup();
    render(<Chip label="Developers" onRemove={onRemove} />);

    await user.click(screen.getByRole("button", { name: "Remove Developers" }));

    expect(onRemove).toHaveBeenCalledTimes(1);
  });
```

Add any missing imports (`userEvent`, `vi`) at the top of the file in the same edit.

Append to `frontend/src/components/ui/checkbox.test.tsx`:

```tsx
  it("keeps the label as the accessible name while hiding it visually", () => {
    render(<Checkbox label="Developers" labelHidden />);
    const box = screen.getByRole("checkbox", { name: "Developers" });
    expect(box).toBeInTheDocument();
    expect(screen.getByText("Developers")).toHaveClass("sr-only");
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && pnpm test --run src/components/ui/chip.test.tsx src/components/ui/checkbox.test.tsx`
Expected: FAIL — `onRemove` and `labelHidden` are not in the prop types.

- [ ] **Step 3: Extend `Chip`**

In `frontend/src/components/ui/chip.tsx`, add to `ChipProps`:

```tsx
  /**
   * When supplied, the chip renders a remove button labelled
   * `Remove ${label}`. Omit it for chips that only display a reference.
   */
  onRemove?: () => void;
```

Destructure `onRemove` in the signature and render it inside the `<span>`, after `{label}`:

```tsx
        {label}
        {onRemove && (
          <button
            type="button"
            aria-label={`Remove ${label}`}
            onClick={onRemove}
            className="ml-1 text-on-surface-variant transition-colors hover:text-error"
          >
            ×
          </button>
        )}
```

The wrapper span already truncates to one line; keep `inline-block` and add nothing else, so an overflowing label still clips and shows its tooltip.

- [ ] **Step 4: Extend `Checkbox`**

In `frontend/src/components/ui/checkbox.tsx`, add to `CheckboxProps`:

```tsx
  /**
   * Hide the label text and drop the row padding, leaving a bare checkbox whose
   * accessible name is still {@link label}. For dense contexts such as a table
   * cell, where the row's other columns already say what is being checked.
   */
  labelHidden?: boolean;
```

Add the bare layout constant next to `ROW`:

```tsx
const BARE = "inline-flex cursor-pointer items-center";
```

and replace the class computation and the label span:

```tsx
  const base = labelHidden ? BARE : ROW;
  const cls = className ? `${base} ${className}` : base;
  return (
    <label className={cls}>
      <input ref={ref} type="checkbox" className="size-4 shrink-0 accent-accent" {...rest} />
      <span className={labelHidden ? "sr-only" : undefined}>{label}</span>
    </label>
  );
```

Remember to destructure `labelHidden` out of the props so it is not spread onto the `<input>`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && pnpm test --run src/components/ui/chip.test.tsx src/components/ui/checkbox.test.tsx`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ui/chip.tsx frontend/src/components/ui/chip.test.tsx frontend/src/components/ui/checkbox.tsx frontend/src/components/ui/checkbox.test.tsx
git commit -m "Add a removable Chip variant and a hidden-label Checkbox"
```

---

### Task 5: Build `RecordPickerDialog`

**Files:**
- Create: `frontend/src/components/admin/record-picker-dialog.tsx`
- Create: `frontend/src/components/admin/record-picker-dialog.test.tsx`

**Interfaces:**
- Consumes: `Dialog` (Task 1), `Checkbox`'s `labelHidden` (Task 4), `useTableQuery`, `DataTable`, `PaginationControls`.
- Produces: `RecordPickerDialog`, `RecordPickerDialogProps<T>`, and `PickerOption` (`{ value: string; label: string }`) from `@/components/admin/record-picker-dialog`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/admin/record-picker-dialog.test.tsx`:

```tsx
import userEvent from "@testing-library/user-event";
import { UsersRound } from "lucide-react";
import { describe, expect, it, vi } from "vitest";
import type { ColumnDef } from "@/components/ui/data-table";
import type { ListQuery } from "@/lib/api";
import { render, screen, waitFor } from "@/test/test-utils";
import { RecordPickerDialog, type RecordPickerDialogProps } from "./record-picker-dialog";

interface Row {
  id: string;
  name: string;
}

const COLUMNS: ColumnDef<Row>[] = [
  { header: "Name", visibility: "always", cell: (r) => r.name },
];

/**
 * Twelve rows, so the first page comes back full and `PaginationControls`
 * enables Next — it disables it whenever `count < limit`.
 */
const ALL: Row[] = Array.from({ length: 12 }, (_, i) => ({
  id: `r${String(i + 1).padStart(2, "0")}`,
  name: `Row ${String(i + 1).padStart(2, "0")}`,
}));

/** Paginate {@link ALL} the way the list API would. */
async function listRows(query: ListQuery): Promise<Row[]> {
  const offset = query.offset ?? 0;
  return ALL.slice(offset, offset + (query.limit ?? 10));
}

function renderDialog(props: Partial<RecordPickerDialogProps<Row>> = {}) {
  const onAssign = vi.fn();
  render(
    <RecordPickerDialog<Row>
      open
      onClose={vi.fn()}
      onAssign={onAssign}
      panelId="test-picker-dialog"
      title="Select rows"
      value={[]}
      listRecords={listRows}
      columns={COLUMNS}
      getId={(r) => r.id}
      getLabel={(r) => r.name}
      emptyMessage="Nothing here."
      emptyIcon={UsersRound}
      {...props}
    />
  );
  return { onAssign };
}

describe("RecordPickerDialog", () => {
  it("lists the records with a checkbox each", async () => {
    renderDialog();
    expect(await screen.findByRole("checkbox", { name: "Row 01" })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Row 10" })).toBeInTheDocument();
  });

  it("pre-checks the records already assigned", async () => {
    renderDialog({ value: ["r01"] });
    await waitFor(() => expect(screen.getByRole("checkbox", { name: "Row 01" })).toBeChecked());
    expect(screen.getByRole("checkbox", { name: "Row 02" })).not.toBeChecked();
  });

  it("reports the checked ids and their labels on Assign", async () => {
    const user = userEvent.setup();
    const { onAssign } = renderDialog();

    await user.click(await screen.findByRole("checkbox", { name: "Row 02" }));
    await user.click(screen.getByRole("button", { name: "Assign" }));

    expect(onAssign).toHaveBeenCalledWith(["r02"], [{ value: "r02", label: "Row 02" }]);
  });

  it("counts the current draft selection", async () => {
    const user = userEvent.setup();
    renderDialog({ value: ["r01"] });

    await user.click(await screen.findByRole("checkbox", { name: "Row 02" }));

    expect(screen.getByText("2 selected")).toBeInTheDocument();
  });

  it("keeps a selection made on a page the operator has paged away from", async () => {
    const user = userEvent.setup();
    const { onAssign } = renderDialog();

    await user.click(await screen.findByRole("checkbox", { name: "Row 01" }));
    await user.click(screen.getByRole("button", { name: /next/i }));
    await screen.findByRole("checkbox", { name: "Row 11" });
    await user.click(screen.getByRole("checkbox", { name: "Row 11" }));
    await user.click(screen.getByRole("button", { name: "Assign" }));

    expect(onAssign).toHaveBeenCalledWith(
      ["r01", "r11"],
      [
        { value: "r01", label: "Row 01" },
        { value: "r11", label: "Row 11" },
      ]
    );
  });

  it("does not report a draft that was cancelled", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { onAssign } = renderDialog({ onClose });

    await user.click(await screen.findByRole("checkbox", { name: "Row 01" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onClose).toHaveBeenCalled();
    expect(onAssign).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test --run src/components/admin/record-picker-dialog.test.tsx`
Expected: FAIL — cannot resolve `./record-picker-dialog`.

- [ ] **Step 3: Implement `RecordPickerDialog`**

Create `frontend/src/components/admin/record-picker-dialog.tsx`:

```tsx
/**
 * @module RecordPickerDialog — modal table for choosing which records to assign.
 *
 * The scalable replacement for a checkbox list: the same `DataTable` +
 * `useTableQuery` + `PaginationControls` trio the admin list pages use, so
 * paging, per-column sort, and per-column filters are all server-side and the
 * dialog behaves exactly like the list page for the same resource.
 */
"use client";

import type { LucideIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { PaginationControls } from "@/components/admin/pagination-controls";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { type ColumnDef, DataTable } from "@/components/ui/data-table";
import { Dialog } from "@/components/ui/dialog";
import { useTableQuery } from "@/hooks/useTableQuery";
import type { ListQuery } from "@/lib/api";

/** One selectable entry: the id stored in the selection and its display label. */
export interface PickerOption {
  /** Record id, as stored in the field's value. */
  value: string;
  /** Human-readable label, shown on the field's chip. */
  label: string;
}

/** Page size of the dialog's table. */
const LIMIT = 10;

/** Props for {@link RecordPickerDialog}. */
export interface RecordPickerDialogProps<T> {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Called when the dialog requests to close (Cancel, backdrop, or Escape). */
  onClose: () => void;
  /** Called with the confirmed selection, and labels for it, on Assign. */
  onAssign: (ids: string[], options: PickerOption[]) => void;
  /** DOM id of the dialog panel; must be unique on the page. */
  panelId: string;
  /** Dialog heading. */
  title: string;
  /** Ids already assigned; the draft is seeded from these on every open. */
  value: string[];
  /** Fetches one page of records for the table. */
  listRecords: (query: ListQuery) => Promise<T[]>;
  /** Columns describing the record, excluding the checkbox column. */
  columns: ColumnDef<T>[];
  /** Extracts a record's id. */
  getId: (row: T) => string;
  /** Extracts a record's chip label. */
  getLabel: (row: T) => string;
  /** Shown by the table when the query returns nothing. */
  emptyMessage: string;
  /** Accent icon for that empty state. */
  emptyIcon: LucideIcon;
}

/**
 * Modal table that returns a set of record ids.
 *
 * The draft selection is kept in component state and survives paging, sorting,
 * and filtering — a record checked on the first page is still checked after the
 * operator has paged past it — which is exactly what a page-at-a-time list
 * cannot express through the rendered checkboxes alone. Labels of every row
 * seen are remembered for the same reason: `onAssign` must be able to name a
 * record that is no longer on screen.
 */
export function RecordPickerDialog<T>({
  open,
  onClose,
  onAssign,
  panelId,
  title,
  value,
  listRecords,
  columns,
  getId,
  getLabel,
  emptyMessage,
  emptyIcon,
}: RecordPickerDialogProps<T>) {
  const { rows, loading, offset, sort, filters, setOffset, setSort, setFilters } = useTableQuery<T>(
    listRecords,
    { limit: LIMIT }
  );
  const [draft, setDraft] = useState<string[]>(value);
  const [labels, setLabels] = useState<Map<string, string>>(new Map());

  // Re-seed the draft on every open, so a cancelled edit never leaks into the
  // next one and an assignment made elsewhere is picked up.
  useEffect(() => {
    if (open) setDraft(value);
  }, [open, value]);

  // Remember what each row seen so far is called.
  useEffect(() => {
    setLabels((prev) => {
      const next = new Map(prev);
      for (const row of rows) next.set(getId(row), getLabel(row));
      return next;
    });
  }, [rows, getId, getLabel]);

  const toggle = useCallback((id: string) => {
    setDraft((prev) => (prev.includes(id) ? prev.filter((v) => v !== id) : [...prev, id]));
  }, []);

  const tableColumns = useMemo<ColumnDef<T>[]>(
    () => [
      {
        // An unlabeled column cannot be offered in the column picker, hence
        // "always"; its cell is interactive, hence noTruncate.
        header: "",
        visibility: "always",
        noTruncate: true,
        width: 44,
        cell: (row: T) => {
          const id = getId(row);
          return (
            <Checkbox
              labelHidden
              label={getLabel(row)}
              checked={draft.includes(id)}
              onChange={() => toggle(id)}
            />
          );
        },
      },
      ...columns,
    ],
    [columns, draft, getId, getLabel, toggle]
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      panelId={panelId}
      title={title}
      size="xl"
      scrollable
      footer={
        <>
          <span className="mr-auto text-sm text-on-surface-variant">
            {draft.length} selected
          </span>
          <Button type="button" variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="primary"
            onClick={() =>
              onAssign(
                draft,
                draft.map((id) => ({ value: id, label: labels.get(id) ?? id }))
              )
            }
          >
            Assign
          </Button>
        </>
      }
    >
      <div className="flex-1 overflow-y-auto">
        <DataTable
          columns={tableColumns}
          rows={rows}
          loading={loading}
          emptyMessage={emptyMessage}
          emptyIcon={emptyIcon}
          getRowKey={getId}
          sort={sort}
          onSortChange={setSort}
          filters={filters}
          onFilterChange={setFilters}
        />
      </div>
      <PaginationControls
        offset={offset}
        limit={LIMIT}
        count={rows.length}
        onPrev={() => setOffset((o) => Math.max(0, o - LIMIT))}
        onNext={() => setOffset((o) => o + LIMIT)}
      />
    </Dialog>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && pnpm test --run src/components/admin/record-picker-dialog.test.tsx`
Expected: PASS (6 tests).

- [ ] **Step 5: Lint**

Run (PowerShell tool, from `frontend/`): `npx biome ci src`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/admin/record-picker-dialog.tsx frontend/src/components/admin/record-picker-dialog.test.tsx
git commit -m "Add RecordPickerDialog, a modal table for picking records"
```

---

### Task 6: Build `RecordPickerField`

**Files:**
- Create: `frontend/src/components/admin/record-picker-field.tsx`
- Create: `frontend/src/components/admin/record-picker-field.test.tsx`

**Interfaces:**
- Consumes: `RecordPickerDialog`, `PickerOption` (Task 5); `Chip`'s `onRemove` (Task 4).
- Produces: `RecordPickerField`, `RecordPickerFieldProps<T>` from `@/components/admin/record-picker-field`.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/admin/record-picker-field.test.tsx`:

```tsx
import userEvent from "@testing-library/user-event";
import { UsersRound } from "lucide-react";
import { describe, expect, it, vi } from "vitest";
import type { ColumnDef } from "@/components/ui/data-table";
import { render, screen, waitFor } from "@/test/test-utils";
import { RecordPickerField, type RecordPickerFieldProps } from "./record-picker-field";

interface Row {
  id: string;
  name: string;
}

const COLUMNS: ColumnDef<Row>[] = [
  { header: "Name", visibility: "always", cell: (r) => r.name },
];

const ALL: Row[] = [
  { id: "a", name: "Alpha" },
  { id: "b", name: "Bravo" },
];

function renderField(props: Partial<RecordPickerFieldProps<Row>> = {}) {
  const onChange = vi.fn();
  const resolveLabels = vi.fn(async (ids: string[]) =>
    ALL.filter((r) => ids.includes(r.id)).map((r) => ({ value: r.id, label: r.name }))
  );
  render(
    <RecordPickerField<Row>
      label="Groups"
      value={[]}
      onChange={onChange}
      resolveLabels={resolveLabels}
      listRecords={async () => ALL}
      columns={COLUMNS}
      getId={(r) => r.id}
      getLabel={(r) => r.name}
      panelId="test-field-dialog"
      dialogTitle="Select rows"
      selectLabel="Select rows…"
      emptyMessage="Nothing here."
      emptyIcon={UsersRound}
      {...props}
    />
  );
  return { onChange, resolveLabels };
}

describe("RecordPickerField", () => {
  it("shows an em dash when nothing is selected", () => {
    renderField();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("resolves a label for each id it starts with", async () => {
    renderField({ value: ["a"] });
    expect(await screen.findByText("Alpha")).toBeInTheDocument();
  });

  it("does not re-resolve labels the caller already supplied", async () => {
    const { resolveLabels } = renderField({
      value: ["a"],
      initialOptions: [{ value: "a", label: "Alpha" }],
    });
    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(resolveLabels).not.toHaveBeenCalled();
  });

  it("removes a selected record through its chip", async () => {
    const user = userEvent.setup();
    const { onChange } = renderField({
      value: ["a", "b"],
      initialOptions: [
        { value: "a", label: "Alpha" },
        { value: "b", label: "Bravo" },
      ],
    });

    await user.click(screen.getByRole("button", { name: "Remove Alpha" }));

    expect(onChange).toHaveBeenCalledWith(["b"]);
  });

  it("applies the dialog's assignment", async () => {
    const user = userEvent.setup();
    const { onChange } = renderField();

    await user.click(screen.getByRole("button", { name: "Select rows…" }));
    await user.click(await screen.findByRole("checkbox", { name: "Bravo" }));
    await user.click(screen.getByRole("button", { name: "Assign" }));

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(["b"]));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("hides the remove buttons and the select button when read-only", async () => {
    renderField({
      value: ["a"],
      initialOptions: [{ value: "a", label: "Alpha" }],
      readOnly: true,
    });

    expect(await screen.findByText("Alpha")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Remove Alpha" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Select rows…" })).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && pnpm test --run src/components/admin/record-picker-field.test.tsx`
Expected: FAIL — cannot resolve `./record-picker-field`.

- [ ] **Step 3: Implement `RecordPickerField`**

Create `frontend/src/components/admin/record-picker-field.tsx`:

```tsx
/**
 * @module RecordPickerField — form field assigning records through a modal table.
 *
 * The successor to the checkbox-list pickers: the current selection reads as a
 * row of chips, each removable on the spot, and changing it opens
 * {@link RecordPickerDialog}, where the full record set is paged and filtered
 * server-side rather than downloaded whole.
 */
"use client";

import type { LucideIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import {
  type PickerOption,
  RecordPickerDialog,
} from "@/components/admin/record-picker-dialog";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import type { ColumnDef } from "@/components/ui/data-table";
import type { ListQuery } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";

/** Props for {@link RecordPickerField}. */
export interface RecordPickerFieldProps<T> {
  /** Field label rendered above the chips. */
  label: string;
  /** Ids of the currently assigned records. */
  value: string[];
  /** Called with the next selection whenever it changes. */
  onChange: (next: string[]) => void;
  /** Render the chips without remove buttons and hide the select button. */
  readOnly?: boolean;
  /**
   * Labels the caller already holds for some of `value` — typically because the
   * screen fetched the records anyway. Ids not covered here are resolved
   * through {@link RecordPickerFieldProps.resolveLabels}.
   */
  initialOptions?: PickerOption[];
  /** Resolves display labels for ids the form starts with. Must be stable. */
  resolveLabels: (ids: string[]) => Promise<PickerOption[]>;
  /** Fetches one page of records for the dialog's table. */
  listRecords: (query: ListQuery) => Promise<T[]>;
  /** Columns describing the record in the dialog. */
  columns: ColumnDef<T>[];
  /** Extracts a record's id. */
  getId: (row: T) => string;
  /** Extracts a record's chip label. */
  getLabel: (row: T) => string;
  /** DOM id of the dialog panel; must be unique on the page. */
  panelId: string;
  /** Heading of the dialog. */
  dialogTitle: string;
  /** Label of the button opening the dialog, e.g. `"Select groups…"`. */
  selectLabel: string;
  /** Shown by the dialog's table when the query returns nothing. */
  emptyMessage: string;
  /** Accent icon for that empty state. */
  emptyIcon: LucideIcon;
}

/**
 * Controlled multi-select over a record set too large to render at once.
 *
 * The dialog is mounted lazily on the first open and then kept mounted, so it
 * costs no request until the operator asks for it and its leave animation still
 * has a component to run on.
 */
export function RecordPickerField<T>({
  label,
  value,
  onChange,
  readOnly = false,
  initialOptions,
  resolveLabels,
  listRecords,
  columns,
  getId,
  getLabel,
  panelId,
  dialogTitle,
  selectLabel,
  emptyMessage,
  emptyIcon,
}: RecordPickerFieldProps<T>) {
  const [open, setOpen] = useState(false);
  const [everOpened, setEverOpened] = useState(false);
  const [labels, setLabels] = useState<Map<string, string>>(
    () => new Map((initialOptions ?? []).map((o) => [o.value, o.label]))
  );

  // Resolve whatever the caller did not supply. Keyed on the joined id list so
  // the fetch runs once per genuinely new set rather than on every render.
  const missingKey = value.filter((id) => !labels.has(id)).join(",");
  useEffect(() => {
    if (missingKey === "") return;
    let cancelled = false;
    resolveLabels(missingKey.split(","))
      .then((options) => {
        if (cancelled) return;
        setLabels((prev) => {
          const next = new Map(prev);
          for (const option of options) next.set(option.value, option.label);
          return next;
        });
      })
      .catch(() => {
        // Failure toast is shown globally by api.ts. Unresolved ids render as
        // their raw id, which is still enough to remove them.
      });
    return () => {
      cancelled = true;
    };
  }, [missingKey, resolveLabels]);

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-label-caps">{label}</span>
      {value.length === 0 ? (
        <ReadOnlyField>{EMPTY_VALUE}</ReadOnlyField>
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {value.map((id) => (
            <Chip
              key={id}
              label={labels.get(id) ?? id}
              onRemove={readOnly ? undefined : () => onChange(value.filter((v) => v !== id))}
            />
          ))}
        </div>
      )}
      {!readOnly && (
        <div>
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              setEverOpened(true);
              setOpen(true);
            }}
          >
            {selectLabel}
          </Button>
        </div>
      )}
      {everOpened && (
        <RecordPickerDialog<T>
          open={open}
          onClose={() => setOpen(false)}
          onAssign={(ids, options) => {
            setLabels((prev) => {
              const next = new Map(prev);
              for (const option of options) next.set(option.value, option.label);
              return next;
            });
            onChange(ids);
            setOpen(false);
          }}
          panelId={panelId}
          title={dialogTitle}
          value={value}
          listRecords={listRecords}
          columns={columns}
          getId={getId}
          getLabel={getLabel}
          emptyMessage={emptyMessage}
          emptyIcon={emptyIcon}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && pnpm test --run src/components/admin/record-picker-field.test.tsx`
Expected: PASS (6 tests).

- [ ] **Step 5: Lint**

Run (PowerShell tool, from `frontend/`): `npx biome ci src`
Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/admin/record-picker-field.tsx frontend/src/components/admin/record-picker-field.test.tsx
git commit -m "Add RecordPickerField, a chip field backed by the picker dialog"
```

---

### Task 7: Convert `GroupPicker` and `UserPicker`, and delete `AsyncCheckboxPicker`

**Files:**
- Modify: `frontend/src/components/admin/group-picker.tsx` (whole file)
- Modify: `frontend/src/components/admin/group-picker.test.tsx` (whole file)
- Modify: `frontend/src/components/admin/user-picker.tsx` (whole file)
- Modify: `frontend/src/components/admin/user-picker.test.tsx` (whole file)
- Delete: `frontend/src/components/admin/async-checkbox-picker.tsx`
- Delete: `frontend/src/components/admin/async-checkbox-picker.test.tsx`

**Interfaces:**
- Consumes: `RecordPickerField` (Task 6).
- Produces: `GroupPicker` gains an optional `initialOptions?: PickerOption[]`; both keep `value`, `onChange`, `readOnly`.

- [ ] **Step 1: Rewrite the picker tests**

Replace `frontend/src/components/admin/group-picker.test.tsx` with:

```tsx
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen } from "@/test/test-utils";
import { GroupPicker } from "./group-picker";

const BASE = "http://localhost:8000";

describe("GroupPicker", () => {
  it("shows a chip for each group the user belongs to", async () => {
    render(<GroupPicker value={["group-1"]} onChange={vi.fn()} />);
    expect(await screen.findByText("Developers")).toBeInTheDocument();
  });

  it("lists the tenant's groups in the dialog", async () => {
    const user = userEvent.setup();
    render(<GroupPicker value={[]} onChange={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Select groups…" }));

    expect(await screen.findByRole("checkbox", { name: "Developers" })).toBeInTheDocument();
  });

  it("assigns the groups checked in the dialog", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<GroupPicker value={[]} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: "Select groups…" }));
    await user.click(await screen.findByRole("checkbox", { name: "Developers" }));
    await user.click(screen.getByRole("button", { name: "Assign" }));

    expect(onChange).toHaveBeenCalledWith(["group-1"]);
  });

  it("shows an empty message when the tenant has no groups", async () => {
    const user = userEvent.setup();
    server.use(http.get(`${BASE}/api/v1/user-groups`, () => envelope([])));
    render(<GroupPicker value={[]} onChange={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Select groups…" }));

    expect(await screen.findByText("This tenant has no user groups yet.")).toBeInTheDocument();
  });

  it("offers neither removal nor selection when read-only", async () => {
    render(<GroupPicker value={["group-1"]} onChange={vi.fn()} readOnly />);

    expect(await screen.findByText("Developers")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Select groups…" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Remove/ })).not.toBeInTheDocument();
  });
});
```

Replace `frontend/src/components/admin/user-picker.test.tsx` with:

```tsx
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { ADMIN } from "@/test/auth-state";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { UserPicker } from "./user-picker";

const BASE = "http://localhost:8000";

describe("UserPicker", () => {
  it("labels each user by name and username in the dialog", async () => {
    const user = userEvent.setup();
    render(<UserPicker value={[]} onChange={vi.fn()} />, { preloadedState: ADMIN });

    await user.click(screen.getByRole("button", { name: "Select members…" }));

    expect(
      await screen.findByRole("checkbox", { name: "Alice Smith (alice)" })
    ).toBeInTheDocument();
  });

  it("asks the server for the acting tenant's users only", async () => {
    const user = userEvent.setup();
    let query = "";
    server.use(
      http.get(`${BASE}/api/v1/users`, ({ request }) => {
        query = new URL(request.url).search;
        return envelope([]);
      })
    );
    render(<UserPicker value={[]} onChange={vi.fn()} />, { preloadedState: ADMIN });

    await user.click(screen.getByRole("button", { name: "Select members…" }));

    await waitFor(() => expect(query).toContain("tenantId%3Aeq%3A"));
  });

  it("shows an empty message when the tenant has no users", async () => {
    const user = userEvent.setup();
    server.use(http.get(`${BASE}/api/v1/users`, () => envelope([])));
    render(<UserPicker value={[]} onChange={vi.fn()} />, { preloadedState: ADMIN });

    await user.click(screen.getByRole("button", { name: "Select members…" }));

    expect(await screen.findByText("This tenant has no users to add.")).toBeInTheDocument();
  });
});
```

Check `frontend/src/test/auth-state.ts` for what `ADMIN` sets. If its user carries no `tenantId`, add one (`tenantId: "tenant-1"`) or use a locally built preloaded state in this file — the tenant filter is derived from `auth.user.tenantId ?? auth.selectedTenantId`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && pnpm test --run src/components/admin/group-picker.test.tsx src/components/admin/user-picker.test.tsx`
Expected: FAIL — there is no "Select groups…" button yet.

- [ ] **Step 3: Rewrite `GroupPicker`**

Replace `frontend/src/components/admin/group-picker.tsx`:

```tsx
/**
 * @module GroupPicker — Assigns the tenant's user groups to one user.
 *
 * The counterpart of {@link UserPicker}: membership is editable from either
 * side, so an admin can manage it from whichever page they are already on.
 */
"use client";

import { UsersRound } from "lucide-react";
import { useCallback } from "react";
import type { PickerOption } from "@/components/admin/record-picker-dialog";
import { RecordPickerField } from "@/components/admin/record-picker-field";
import type { ColumnDef } from "@/components/ui/data-table";
import { listUserGroups, type UserGroup } from "@/lib/api";
import { EMPTY_VALUE } from "@/lib/read-only-display";
import { ROLE_LABELS } from "@/lib/roles";

/** Columns of the picker dialog, mirroring the user-groups list page. */
const COLUMNS: ColumnDef<UserGroup>[] = [
  {
    header: "Name",
    sortField: "name",
    filterField: "name",
    visibility: "always",
    cell: (g) => g.name,
  },
  {
    header: "Description",
    filterField: "description",
    cell: (g) => g.description || EMPTY_VALUE,
  },
  {
    // Roles are a JSON column, so this column is display-only: the list API can
    // neither sort nor filter on it.
    header: "Roles",
    noTruncate: true,
    cell: (g) =>
      g.roles && g.roles.length > 0
        ? g.roles.map((role) => ROLE_LABELS[role]).join(", ")
        : EMPTY_VALUE,
  },
  {
    // Membership lives in a join table rather than on the group row, so this is
    // display-only too.
    header: "Members",
    className: "text-center",
    cell: (g) => g.memberIds?.length ?? 0,
  },
];

/** Props for {@link GroupPicker}. */
export interface GroupPickerProps {
  /** Ids of the groups the user currently belongs to. */
  value: string[];
  /** Called with the next selection whenever the assignment changes. */
  onChange: (next: string[]) => void;
  /** Render the selection as a read-only value instead of an editable field. */
  readOnly?: boolean;
  /** Group labels the page already loaded, saving a label round trip. */
  initialOptions?: PickerOption[];
}

/** Controlled multi-select over the tenant's user groups. */
export function GroupPicker({
  value,
  onChange,
  readOnly = false,
  initialOptions,
}: GroupPickerProps) {
  const resolveLabels = useCallback(async (ids: string[]): Promise<PickerOption[]> => {
    const groups = await listUserGroups({
      limit: ids.length,
      filters: [{ field: "id", op: "in", value: ids.join(",") }],
    });
    return groups.map((group) => ({ value: group.id, label: group.name }));
  }, []);

  return (
    <RecordPickerField<UserGroup>
      label="Groups"
      value={value}
      onChange={onChange}
      readOnly={readOnly}
      initialOptions={initialOptions}
      resolveLabels={resolveLabels}
      listRecords={listUserGroups}
      columns={COLUMNS}
      getId={(group) => group.id}
      getLabel={(group) => group.name}
      panelId="group-picker-dialog"
      dialogTitle="Select groups"
      selectLabel="Select groups…"
      emptyMessage="This tenant has no user groups yet."
      emptyIcon={UsersRound}
    />
  );
}
```

- [ ] **Step 4: Rewrite `UserPicker`**

Replace `frontend/src/components/admin/user-picker.tsx`:

```tsx
/**
 * @module UserPicker — Assigns the tenant's users to one group.
 *
 * The listing is filtered server-side to the acting tenant. That is both what
 * keeps paging honest — a client-side filter would punch holes in pages — and
 * what keeps the picker from offering members the backend will reject: a group
 * belongs to exactly one tenant, so platform-scoped accounts (every super admin
 * and the seeded system user, all with `tenantId === null`) and users of other
 * tenants can never be members. Soft-deleted users never reach the list
 * endpoint at all.
 */
"use client";

import { Users } from "lucide-react";
import { useCallback } from "react";
import type { PickerOption } from "@/components/admin/record-picker-dialog";
import { RecordPickerField } from "@/components/admin/record-picker-field";
import type { ColumnDef } from "@/components/ui/data-table";
import { formatUserName, type ListQuery, listUsers, type User } from "@/lib/api";
import { useAppSelector } from "@/store/hooks";

/** Columns of the picker dialog, mirroring the users list page. */
const COLUMNS: ColumnDef<User>[] = [
  {
    header: "Username",
    sortField: "username",
    filterField: "username",
    visibility: "always",
    cell: (u) => u.username,
  },
  {
    header: "Name",
    sortField: "firstName",
    filterField: "firstName",
    cell: (u) => formatUserName(u),
  },
  {
    header: "Email",
    sortField: "email",
    filterField: "email",
    cell: (u) => u.email,
  },
];

/** Label shown on a member's chip and on its checkbox in the dialog. */
function memberLabel(user: User): string {
  return `${formatUserName(user)} (${user.username})`;
}

/** Props for {@link UserPicker}. */
export interface UserPickerProps {
  /** Ids of the currently selected users. */
  value: string[];
  /** Called with the next selection whenever the assignment changes. */
  onChange: (next: string[]) => void;
  /** Render the selection as a read-only value instead of an editable field. */
  readOnly?: boolean;
}

/** Controlled multi-select over the acting tenant's users. */
export function UserPicker({ value, onChange, readOnly = false }: UserPickerProps) {
  // The acting tenant, resolved the same way the X-Tenant-Id interceptor does:
  // a tenant-scoped viewer's own tenant, or the tenant a super admin selected
  // in the app bar.
  const viewerTenantId = useAppSelector((s) => s.auth.user?.tenantId ?? null);
  const selectedTenantId = useAppSelector((s) => s.auth.selectedTenantId);
  const tenantId = viewerTenantId ?? selectedTenantId;

  const listRecords = useCallback(
    (query: ListQuery) =>
      listUsers({
        ...query,
        filters: [
          ...(query.filters ?? []),
          ...(tenantId ? [{ field: "tenantId", op: "eq", value: tenantId }] : []),
        ],
      }),
    [tenantId]
  );

  const resolveLabels = useCallback(async (ids: string[]): Promise<PickerOption[]> => {
    const users = await listUsers({
      limit: ids.length,
      filters: [{ field: "id", op: "in", value: ids.join(",") }],
    });
    return users.map((user) => ({ value: user.id, label: memberLabel(user) }));
  }, []);

  return (
    <RecordPickerField<User>
      label="Members"
      value={value}
      onChange={onChange}
      readOnly={readOnly}
      resolveLabels={resolveLabels}
      listRecords={listRecords}
      columns={COLUMNS}
      getId={(user) => user.id}
      getLabel={memberLabel}
      panelId="user-picker-dialog"
      dialogTitle="Select members"
      selectLabel="Select members…"
      emptyMessage="This tenant has no users to add."
      emptyIcon={Users}
    />
  );
}
```

- [ ] **Step 5: Delete the dead picker**

```bash
git rm frontend/src/components/admin/async-checkbox-picker.tsx frontend/src/components/admin/async-checkbox-picker.test.tsx
```

Then confirm nothing still imports it:

Run: `cd frontend && grep -rn "async-checkbox-picker\|AsyncCheckboxPicker" src`
Expected: no matches. (`McpToolPicker` defines its own `FILTER_THRESHOLD` and does not import this module.)

- [ ] **Step 6: Run the picker tests to verify they pass**

Run: `cd frontend && pnpm test --run src/components/admin/group-picker.test.tsx src/components/admin/user-picker.test.tsx`
Expected: PASS.

- [ ] **Step 7: Lint**

Run (PowerShell tool, from `frontend/`): `npx biome ci src`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/admin/group-picker.tsx frontend/src/components/admin/group-picker.test.tsx frontend/src/components/admin/user-picker.tsx frontend/src/components/admin/user-picker.test.tsx
git commit -m "Move the membership pickers onto the modal table field"
```

The `git rm` from Step 5 is already staged, so it goes in with this commit.

---

### Task 8: Wire the four pages and finish

**Files:**
- Modify: `frontend/src/app/admin/users/[userId]/page.tsx`
- Modify: `frontend/src/app/admin/users/[userId]/page.test.tsx`
- Modify: `frontend/src/app/admin/user-groups/[groupId]/page.test.tsx` (only if its assertions touch the picker)
- Modify: `README.md` (only if it describes the picker's checkbox list)

**Interfaces:**
- Consumes: `getUserGroupsForUser` (Task 3), `GroupPicker`'s `initialOptions` (Task 7).

`users/new`, `user-groups/[groupId]`, and `user-groups/new` need **no source change** — they already render `<GroupPicker value onChange>` / `<UserPicker value onChange readOnly>`, and those prop contracts are unchanged.

- [ ] **Step 1: Update the user detail page's membership fetch**

In `frontend/src/app/admin/users/[userId]/page.tsx`, add a `groupOptions` state next to `groupIds`:

```tsx
  // Group membership, edited from this side as well as from the group detail
  // page. `savedGroupIds` remembers what the server has, so an unchanged
  // selection skips the extra request; `groupOptions` hands the picker the
  // names it already fetched, so the chips render without a second round trip.
  const [groupIds, setGroupIds] = useState<string[]>([]);
  const [savedGroupIds, setSavedGroupIds] = useState<string[]>([]);
  const [groupOptions, setGroupOptions] = useState<PickerOption[]>([]);
```

Replace the membership effect (currently `listUserGroups({ limit: 1000 })` plus a `memberIds` scan) with:

```tsx
  // Membership is not carried on the user record, so it is read through the
  // dedicated sub-resource. A failure here is not fatal: the picker renders an
  // empty selection and the rest of the form still works.
  useEffect(() => {
    getUserGroupsForUser(userId)
      .then((groups) => {
        setGroupIds(groups.map((group) => group.id));
        setSavedGroupIds(groups.map((group) => group.id));
        setGroupOptions(groups.map((group) => ({ value: group.id, label: group.name })));
      })
      .catch(() => {
        // Failure toast is shown globally by api.ts; nothing else to do here.
      });
  }, [userId]);
```

Pass the options to the picker:

```tsx
          {canJoinGroups && (
            <GroupPicker
              value={groupIds}
              onChange={setGroupIds}
              readOnly={!canEdit}
              initialOptions={groupOptions}
            />
          )}
```

Swap `listUserGroups` for `getUserGroupsForUser` in the `@/lib/api` import and add `import type { PickerOption } from "@/components/admin/record-picker-dialog";` — all in the same edit, or Biome will strip the new imports.

- [ ] **Step 2: Update the user detail page's membership tests**

In `frontend/src/app/admin/users/[userId]/page.test.tsx`, rewrite the three membership tests in the `UserDetailPage group membership` block. Replace `it("checks the groups the user already belongs to", …)` with:

```tsx
  it("shows a chip for each group the user already belongs to", async () => {
    renderPage();
    expect(await screen.findByText("Developers")).toBeInTheDocument();
  });
```

Replace `it("writes the new membership when a group is toggled", …)` with:

```tsx
  it("writes the new membership when a group is removed", async () => {
    let body: unknown;
    server.use(
      http.put("http://localhost:8000/api/v1/users/:userId/groups", async ({ request }) => {
        body = await request.json();
        return envelope({ id: "user-1" });
      })
    );
    renderPage();
    await screen.findByText("Developers");
    await userEvent.click(screen.getByRole("button", { name: "Remove Developers" }));
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(body).toEqual({ groupIds: [] }));
  });
```

Leave `it("writes membership only when the selection changed", …)` as it is, but change its wait from the checkbox to `await screen.findByText("Developers")`.

The `hides the group picker for a platform-scoped user` test still asserts on the `"Groups"` label and needs no change.

- [ ] **Step 3: Run the page tests**

Run: `cd frontend && pnpm test --run src/app/admin/users src/app/admin/user-groups`
Expected: PASS. If `user-groups/[groupId]/page.test.tsx` asserted on member checkboxes, update it the same way — chip text instead of checkbox role.

- [ ] **Step 4: Run the whole frontend suite**

Run: `cd frontend && pnpm test --run`
Expected: PASS.

- [ ] **Step 5: Build**

Run: `cd frontend && pnpm build`
Expected: success. This is what pre-push runs, and it catches `zod.gen` name mismatches.

- [ ] **Step 6: Check the README**

Run: `grep -n "group" README.md`
Review the hits. If any sentence describes assigning groups or members through a checkbox list, update it to describe the modal table picker. If the README only names the user-groups feature without describing its UI, leave it alone and say so.

- [ ] **Step 7: Lint**

Run (PowerShell tool, from `frontend/`): `npx biome ci src`
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/admin/users/[userId]/page.tsx frontend/src/app/admin/users/[userId]/page.test.tsx
git commit -m "Read a user's groups from the dedicated endpoint and chip them"
```

Include `README.md` and `frontend/src/app/admin/user-groups/[groupId]/page.test.tsx` in the `git add` if Steps 3 and 6 changed them.

---

## Verification

After Task 8, the whole change is in. Confirm end to end:

- [ ] `cd backend && uv run pytest` — full backend suite passes.
- [ ] `cd frontend && pnpm test --run` — full frontend suite passes.
- [ ] `cd frontend && pnpm build` — production build succeeds.
- [ ] Optionally drive the real app with the `verify` skill: open `/admin/users/<id>`, press **Select groups…**, filter the table by name, page forward, check a group on each page, press **Assign**, confirm both chips appear, remove one, press **Save**, and reload to confirm the membership stuck. Repeat on `/admin/user-groups/<id>` for **Members**.
