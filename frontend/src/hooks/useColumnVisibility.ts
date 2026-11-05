/** @module useColumnVisibility — per-table column visibility, persisted to localStorage. */
"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import type { CheckboxOption } from "@/components/ui/checkbox-group";
import type { ColumnDef } from "@/components/ui/data-table";
import { useT } from "@/i18n/provider";

/** Prefix of the localStorage key holding one table's column choices. */
const STORAGE_PREFIX = "a2flow.columns.";

/**
 * The viewer's departures from a table's declared defaults, keyed by column
 * header. Only headers the viewer actually toggled appear here.
 */
type Overrides = Record<string, boolean>;

/** Whether the column is offered in the picker at all. */
function isToggleable<T>(column: ColumnDef<T>): boolean {
  return column.visibility !== "always";
}

/** Whether the column is shown when the viewer has expressed no preference. */
function isDefaultVisible<T>(column: ColumnDef<T>): boolean {
  return column.visibility !== "optional";
}

/** Read a table's stored overrides, treating unreadable or malformed data as none. */
function readOverrides(storageKey: string): Overrides {
  try {
    const raw = window.localStorage.getItem(STORAGE_PREFIX + storageKey);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) return {};
    // Keep only the boolean entries; anything else is from a shape we no longer
    // write and is safer discarded than coerced.
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>).filter(
        ([, value]) => typeof value === "boolean"
      )
    ) as Overrides;
  } catch {
    // Ignore -- privacy-mode browsers may throw, and a corrupt value should
    // fall back to the table's defaults rather than break the page.
    return {};
  }
}

/** Persist a table's overrides, removing the key entirely once there are none. */
function writeOverrides(storageKey: string, overrides: Overrides): void {
  try {
    if (Object.keys(overrides).length === 0) {
      window.localStorage.removeItem(STORAGE_PREFIX + storageKey);
    } else {
      window.localStorage.setItem(STORAGE_PREFIX + storageKey, JSON.stringify(overrides));
    }
  } catch {
    // Ignore -- privacy-mode browsers may throw on localStorage writes.
  }
}

/** Everything a list page needs to render a column picker and a filtered table. */
export interface UseColumnVisibilityResult<T> {
  /** The columns to hand to `DataTable`, in declaration order. */
  visibleColumns: ColumnDef<T>[];
  /** One picker option per toggleable column, in declaration order. */
  options: CheckboxOption[];
  /** Headers of the toggleable columns currently shown. */
  selected: string[];
  /** Replace the shown set (values must come from {@link options}) and persist it. */
  setSelected: (next: string[]) => void;
  /** Discard the stored preference and fall back to the declared defaults. */
  reset: () => void;
  /** Whether the current set differs from the declared defaults. */
  customized: boolean;
}

/**
 * Let the viewer choose which of a table's columns are shown, remembering the
 * choice in localStorage under `a2flow.columns.<storageKey>`.
 *
 * Each column declares how it participates through `ColumnDef.visibility`:
 * `"always"` columns are never offered and never hidden, `"default"` columns
 * start shown, and `"optional"` columns start hidden. What is stored is only the
 * viewer's *departures* from those declarations, not the resolved set — so a
 * column added to the table later still arrives at its declared default, and the
 * stored entry for a column that has since been removed (or role-gated away, as
 * the agent-skills actions column is) is simply ignored.
 *
 * The stored value is read after mount rather than during the first render:
 * these pages are server-rendered, and seeding state from localStorage would
 * make the markup disagree with the server's. Nothing flashes in practice —
 * rows arrive from the API later still, and `DataTable` defers its width
 * measurement until they do.
 *
 * `columns` may be rebuilt inline on every render; only the headers and their
 * declared visibility are read, never the array's identity.
 *
 * @param storageKey - Stable, per-table slug (e.g. `"users"`) scoping the stored preference.
 * @param columns - The table's full column set, in display order.
 * @returns The filtered columns plus the picker's controlled state.
 */
export function useColumnVisibility<T>(
  storageKey: string,
  columns: ColumnDef<T>[]
): UseColumnVisibilityResult<T> {
  const t = useT();
  const [overrides, setOverrides] = useState<Overrides>({});

  useEffect(() => {
    setOverrides(readOverrides(storageKey));
  }, [storageKey]);

  // Pages rebuild their column array inline every render, so derive from the
  // headers and their declared visibility instead of the array identity.
  const columnsKey = columns.map((col) => `${col.header}:${col.visibility ?? "default"}`).join("");

  // biome-ignore lint/correctness/useExhaustiveDependencies: columnsKey captures the relevant change
  const toggleable = useMemo(() => columns.filter(isToggleable), [columnsKey]);

  const isVisible = useCallback(
    (column: ColumnDef<T>) =>
      !isToggleable(column) || (overrides[column.header] ?? isDefaultVisible(column)),
    [overrides]
  );

  const visibleColumns = columns.filter(isVisible);
  const selected = toggleable.filter(isVisible).map((col) => col.header);

  const options = useMemo<CheckboxOption[]>(
    () => toggleable.map((col) => ({ value: col.header, label: t.maybe(col.header) })),
    [toggleable, t]
  );

  const setSelected = useCallback(
    (next: string[]) => {
      const shown = new Set(next);
      const updated: Overrides = {};
      for (const col of toggleable) {
        const visible = shown.has(col.header);
        // Store the departures only, so the defaults stay authoritative for
        // everything the viewer has not deliberately changed.
        if (visible !== isDefaultVisible(col)) updated[col.header] = visible;
      }
      setOverrides(updated);
      writeOverrides(storageKey, updated);
    },
    [toggleable, storageKey]
  );

  const reset = useCallback(() => {
    setOverrides({});
    writeOverrides(storageKey, {});
  }, [storageKey]);

  // Judged against the columns actually on the table: a leftover override for a
  // column this table no longer has must not light up "Reset to default" while
  // everything on screen still matches the defaults.
  const customized = toggleable.some((col) => overrides[col.header] !== undefined);

  return { visibleColumns, options, selected, setSelected, reset, customized };
}
