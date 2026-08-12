# Modal table record picker — design

Replace the checkbox-list membership pickers (`GroupPicker`, `UserPicker`) with a
field that shows the current selection as removable chips and opens a modal
dialog containing a real, server-paginated table to change it.

## Motivation

Both pickers are thin wrappers over `AsyncCheckboxPicker`, which loads the whole
option list with `limit: 1000` on mount and renders one checkbox per option, with
a client-side filter box appearing past 12 options. That stops being usable — and
eventually stops being correct — as a tenant accumulates groups, and sooner as it
accumulates users: past 1000 records the option simply is not offered.

The admin list pages already solve this with `DataTable` + `useTableQuery` +
`PaginationControls`: server-side pagination, per-column sort, and per-column
filters. The picker should reuse that machinery rather than invent a smaller,
weaker version of it.

## Scope

Four screens, through two shared components:

| Screen | Field |
|---|---|
| `/admin/users/[userId]` | Groups |
| `/admin/users/new` | Groups |
| `/admin/user-groups/[groupId]` | Members |
| `/admin/user-groups/new` | Members |

## Components

### `ui/dialog.tsx` — shared modal shell

`ConfirmDialog`, `RegistrySearchDialog`, `GenerateWorkflowDialog`, and
`DescriptionDiffDialog` each hand-write the same shell: a `createPortal` to
`document.body`, a `useTransition` fade/scale pair from `@react-spring/web`, a
backdrop button that closes on click and declines focus on mousedown, a
`useDialogA11y` call with `closeOnOutsideClick: false`, and a
`role="dialog" aria-modal="true"` panel with a `<h2>` title. They differ only in
panel id, maximum width, and whether the body scrolls.

Adding a fifth copy would violate the UI-consistency rule in `CLAUDE.md`, so the
shell is extracted first and all four existing dialogs are migrated onto it.

```tsx
interface DialogProps {
  open: boolean;
  onClose: () => void;
  /** DOM id of the panel; the title element derives its id as `${panelId}-title`. */
  panelId: string;
  title: string;
  /** Sentence under the title. */
  description?: string;
  /** Maximum panel width. Defaults to "md". */
  size?: "sm" | "md" | "lg" | "xl";
  /** Cap the panel at 80vh and let the body scroll. Defaults to false. */
  scrollable?: boolean;
  /** Right-aligned action row pinned below the body. */
  footer?: React.ReactNode;
  /** Extra classes merged onto the panel, for the few callers that need them. */
  panelClassName?: string;
  children: React.ReactNode;
}
```

Each migrated dialog keeps its current `panelId`, `aria-labelledby` target, and
panel classes, so the rendered DOM is unchanged and the existing dialog tests
keep passing. Any that do not are updated in the same task.

`DescriptionDiffDialog` and `GenerateWorkflowDialog` pass extra classes to the
panel today; `Dialog` accepts an optional `panelClassName` for that.

### `admin/record-picker-dialog.tsx` — the picker modal

A generic modal that lists records in a `DataTable` and returns a selection.

```tsx
interface RecordPickerDialogProps<T> {
  open: boolean;
  onClose: () => void;
  /** Called with the confirmed selection when the operator presses Assign. */
  onAssign: (ids: string[], options: PickerOption[]) => void;
  title: string;
  /** Currently assigned ids, used to seed the draft each time the dialog opens. */
  value: string[];
  /** Fetches one page for the table. Must be stable (wrap in `useCallback`). */
  listRecords: (query: ListQuery) => Promise<T[]>;
  columns: ColumnDef<T>[];
  getId: (row: T) => string;
  getLabel: (row: T) => string;
  /** Shown by the table when the query returns nothing. */
  emptyMessage: string;
  /** Accent icon for that empty state. */
  emptyIcon: LucideIcon;
}
```

- Data comes from `useTableQuery(listRecords, { limit: 10 })`, so pagination,
  sort, and filters are all server-side and behave exactly as on the matching
  admin list page.
- A checkbox column is prepended to `columns`. It carries an empty `header`, so
  it must be `visibility: "always"` (the `ColumnDef` contract requires that for
  an unlabeled column) and `noTruncate: true` because its cell is interactive.
  There is no select-all header control: `DataTable` renders headers as plain
  strings, and a select-all that only covers the visible page would be
  misleading.
- The draft selection is a `Set<string>` in component state, seeded from `value`
  on open and **kept across page, sort, and filter changes** — a record checked
  on page 1 stays checked after paging to page 2 and back.
- Labels of every row the operator has checked are recorded alongside the draft,
  so `onAssign` can hand the field enough to render chips without another fetch.
- The footer shows `{n} selected` on the left and `Cancel` (ghost) / `Assign`
  (primary) on the right. `Cancel` discards the draft; the dialog is rendered by
  `Dialog` with `scrollable` and `size="xl"`.

`DataTable`'s per-column filter menus portal themselves out of the panel, but
`useDialogA11y` already marks every open panel with `data-glass-popover` and
treats a pointerdown inside any of them as "inside", so a filter menu opened
within the dialog does not close it.

### `admin/record-picker-field.tsx` — the form field

```tsx
interface RecordPickerFieldProps<T> {
  label: string;
  value: string[];
  onChange: (next: string[]) => void;
  /** Render chips without remove buttons and hide the Select button. */
  readOnly?: boolean;
  /** Labels the caller already holds; ids not covered are resolved by `resolveLabels`. */
  initialOptions?: PickerOption[];
  /** Resolves display labels for ids the form starts with. Must be stable. */
  resolveLabels: (ids: string[]) => Promise<PickerOption[]>;
  listRecords: (query: ListQuery) => Promise<T[]>;
  columns: ColumnDef<T>[];
  getId: (row: T) => string;
  getLabel: (row: T) => string;
  dialogTitle: string;
  emptyMessage: string;
  emptyIcon: LucideIcon;
  /** Label of the button that opens the dialog, e.g. "Select groups…". */
  selectLabel: string;
}
```

- Renders the field label, then the selection as `Chip`s, then the Select button.
- A label map (`id -> label`) is held in state. It is seeded from
  `initialOptions`, extended with whatever `resolveLabels` returns for the
  remaining ids on mount, and extended again by every `onAssign`. An id whose
  label never resolves falls back to its raw id, the same convention
  `getUserNames` callers already follow.
- Each chip's `×` removes that id via `onChange`; removal never needs the dialog.
- With no selection, the field renders `ReadOnlyField` with `EMPTY_VALUE` so it
  matches the other empty admin fields.
- `readOnly` drops the `×` buttons and the Select button, leaving the chips as a
  plain value display.

### `ui/chip.tsx` — removable variant

`Chip` gains an optional `onRemove?: () => void`. When supplied, it renders a
small `×` button inside the pill with an accessible name of
`Remove ${label}`. The prop is optional, so the existing dependency-chip and
tool-chip usages are untouched. The `<span>` stays the direct child of `Tooltip`,
which clones it for its ref and hover handlers.

### `GroupPicker` / `UserPicker`

Both become thin wrappers over `RecordPickerField`, the same relationship they
have to `AsyncCheckboxPicker` today.

`GroupPicker` — columns Name, Description, Roles, Members; `listRecords` is
`listUserGroups`; `resolveLabels` is `listUserGroups` with an `id:in:<ids>`
filter.

`UserPicker` — columns Name, Username, Email; `listRecords` is `listUsers` with a
`tenantId:eq:<acting tenant>` filter; `resolveLabels` is `listUsers` with an
`id:in:<ids>` filter. The acting tenant is `viewer.tenantId ?? selectedTenantId`,
the same value the `X-Tenant-Id` interceptor sends.

That server-side tenant filter replaces today's client-side
`user.tenantId !== null` filter, which cannot survive server-side pagination (it
would punch holes in pages). It is also strictly more correct: a `super_admin`
reads users across every tenant, so today's filter still offers members from
another tenant, which the backend then rejects with 422 on save.

`AsyncCheckboxPicker` has no other callers once both wrappers are converted, so
it and its test are deleted. `McpToolPicker` defines its own `FILTER_THRESHOLD`
and is unaffected.

## Backend

### `GET /api/v1/users/{userId}/groups`

The user detail page currently discovers a user's groups by fetching
`listUserGroups({ limit: 1000 })` and scanning every group's `memberIds` — the
exact full-list fetch this change exists to remove. A dedicated endpoint replaces
it, mirroring the existing `PUT /api/v1/users/{userId}/groups`.

- Returns `ApiResponse[list[UserGroupRead]]` — the group objects, not just their
  ids, so the page can seed the field's `initialOptions` and skip a second
  round trip for labels.
- No `admin` role gate. Reads are open to authenticated users by convention; the
  route calls `UserService.get(user_id, acting_user=...)` first, so a
  cross-tenant `userId` surfaces as 404 through the existing tenant-visibility
  rule.
- `SqlUserGroupRepository` gains `list_for_user(user_id) -> list[UserGroupRead]`:
  a tenant-scoped join through `UserGroupMember`, projected with
  `_members_for_many` the same way `list()` does. The existing
  `group_ids_for_user` stays as-is — `set_groups_for_user` and the effective-role
  resolution still use it.
- `UserGroupService` gains a matching `groups_for_user` passthrough.

`backend/openapi.yaml` and `frontend/src/generated/` are regenerated afterwards.
Both are gitignored, so they produce no commit diff, but the regeneration must
still run before the frontend build can resolve the new binding.

### `lib/api.ts`

Add `getUserGroupsForUser(userId: string): Promise<UserGroup[]>` against the new
route, validated with the generated Zod response schema.

## Data flow

Opening `/admin/users/[userId]`:

1. `getUser(userId)` fills the form as today.
2. `getUserGroupsForUser(userId)` replaces the `listUserGroups({ limit: 1000 })`
   scan. Its result sets `groupIds`/`savedGroupIds` and is passed to
   `GroupPicker` as `initialOptions`, so the chips render without a further
   fetch.
3. Pressing Select opens the dialog, which fetches page 1 of `listUserGroups`.
4. Assign writes the new id list into `groupIds`.
5. Submit is unchanged: `updateUser`, then `setUserGroups` only when
   `sameIds(groupIds, savedGroupIds)` is false.

The group detail page is the mirror image, except `memberIds` already arrives on
the group record, so only `resolveLabels` runs for the chips.

The two create pages start with an empty selection, so neither
`initialOptions` nor `resolveLabels` has anything to do.

## Error handling

- The dialog's fetches go through `useTableQuery`, which shows the global red
  toast from `api.ts` on failure and leaves the rows on screen unchanged. No
  local error state is added.
- `resolveLabels` failing is not fatal: unresolved ids render as raw ids and the
  rest of the form still works, matching how the user detail page already treats
  a failed membership fetch.
- Assigning a record the backend then rejects (a stale cross-tenant id, say)
  still surfaces as the existing 422 on save. Nothing new is needed.

## Testing

Backend (`backend/tests/test_user_groups.py`):

- `GET /users/{userId}/groups` returns the user's groups.
- A user in another tenant returns 404, not 403 or an empty list.
- A user with no groups returns an empty list.
- The route is reachable without the `admin` role.

Frontend, new tests:

- `ui/dialog.test.tsx` — renders when open, closes on Escape and backdrop click,
  labels the panel by its title, renders the footer.
- `admin/record-picker-dialog.test.tsx` — checks a row, pages forward and back
  with the check retained, Assign reports the ids, Cancel discards the draft.
- `admin/record-picker-field.test.tsx` — renders chips for the initial value,
  removes one via its `×`, opens the dialog, applies an assignment, hides the
  controls under `readOnly`.
- `ui/chip.test.tsx` — the `×` appears only with `onRemove` and calls it.

Frontend, updated tests:

- `admin/group-picker.test.tsx`, `admin/user-picker.test.tsx` rewritten for the
  new markup (including the `tenantId:eq:` query the user picker sends).
- `app/admin/users/[userId]/page.test.tsx` for the new membership fetch.
- `src/test/msw/handlers.ts` gains a handler for `GET /users/:userId/groups`.
- The four migrated dialogs' tests are run and fixed if the shell extraction
  moved anything they assert on.

Deleted: `admin/async-checkbox-picker.test.tsx`.

## Documentation

- Doc comments on every new module, component, prop interface, and backend
  method, per `CLAUDE.md`.
- `README.md` mentions user-group membership editing; update the wording if it
  describes the checkbox list specifically.
- `.claude/rules/api-conventions.md` needs no change — the new route uses no new
  query syntax.

## Out of scope

- A select-all control in the dialog table.
- Making a `super_admin`'s user list tenant-scoped server-side. The client-side
  `tenantId:eq:` filter above fixes the picker; the underlying listing behaviour
  is left alone.
- Migrating the other multi-selects (`McpToolPicker`, `RolesField`) to this
  pattern. Their option sets are bounded and small.
