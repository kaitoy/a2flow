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
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  const wasOpenRef = useRef(open);

  // Re-seed the draft on the closed→open transition, so a cancelled edit never
  // leaks into the next one and an assignment made elsewhere is picked up.
  // `value` is deliberately not a dependency: re-seeding on every `value`
  // identity change while already open would silently discard an in-progress
  // draft whenever the parent re-renders with a fresh (but equal) array.
  // biome-ignore lint/correctness/useExhaustiveDependencies: intentionally re-runs only on the open transition, not on every value identity change
  useEffect(() => {
    if (open && !wasOpenRef.current) setDraft(value);
    wasOpenRef.current = open;
  }, [open]);

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
          <span className="mr-auto text-sm text-on-surface-variant">{draft.length} selected</span>
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
