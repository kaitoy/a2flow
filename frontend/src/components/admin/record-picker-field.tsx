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
import { useEffect, useRef, useState } from "react";
import { ReadOnlyField } from "@/components/admin/read-only-field";
import { type PickerOption, RecordPickerDialog } from "@/components/admin/record-picker-dialog";
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

  // Rebuilt every render (pickers pass at most a page's worth of options, so
  // this is cheap) rather than folded into `labels` and read back: `value` and
  // `initialOptions` typically change together, in the very same render — the
  // user detail page sets `groupIds` and `groupOptions` from the same
  // membership-fetch callback, and React batches both into one update — and a
  // render cannot see a state write an effect of that same render has not
  // committed yet. Consulting `initialOptions` directly here, rather than
  // waiting for the merge effect below, is what lets both `missingKey` and the
  // chip label below see a newly-arrived id on the render it arrives on,
  // instead of one render later.
  const initialOptionsById = new Map((initialOptions ?? []).map((o) => [o.value, o.label]));

  // Latest `initialOptions` for the merge effect below to read, kept out of
  // its dependency array on purpose (see `initialOptionsKey`).
  const initialOptionsRef = useRef(initialOptions);
  initialOptionsRef.current = initialOptions;

  // Content fingerprint of `initialOptions`, used only to decide when the
  // merge effect below needs to run again. `initialOptions` itself cannot be
  // the dependency: a caller that inlines the array literal (as GroupPicker
  // does when it forwards its own `initialOptions` prop through) hands this
  // component a new array identity on every render, which would fire the
  // effect every render too. Two renders whose `initialOptions` carry the
  // same ids produce the same key string, and `useEffect` compares dependency
  // values with `Object.is` — string primitives compare by value — so the
  // effect only re-fires when the id set genuinely changes.
  const initialOptionsKey = (initialOptions ?? []).map((o) => o.value).join(",");

  // Copies `initialOptions` into the persistent `labels` map even when it
  // arrives after the first render, not only from the `useState` initializer
  // above (which React only ever runs once). Without this, an id `labels`
  // has never otherwise learned (through `resolveLabels` or the dialog's
  // `onAssign`) would fall back to `initialOptionsById` on every render
  // instead of settling into state — harmless for what's on screen right now
  // (see `initialOptionsById` above for why the *chip label* and
  // `missingKey` do not wait on this effect to be correct), but it would
  // leave `labels` never actually knowing the name for that id, so a later
  // render whose `initialOptions` prop no longer happens to include it would
  // regress the chip back to showing the raw id.
  //
  // Only ever adds entries `labels` doesn't already have, so it cannot loop:
  // `setLabels` bails out to the same `prev` reference once every id in
  // `initialOptions` is already present, and this effect's own dependency,
  // `initialOptionsKey`, does not change when `labels` changes.
  // biome-ignore lint/correctness/useExhaustiveDependencies: initialOptionsKey captures the relevant change; initialOptionsRef.current is read purely to dodge depending on the array's unstable identity
  useEffect(() => {
    const options = initialOptionsRef.current;
    if (!options || options.length === 0) return;
    setLabels((prev) => {
      let changed = false;
      const next = new Map(prev);
      for (const option of options) {
        if (!next.has(option.value)) {
          next.set(option.value, option.label);
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [initialOptionsKey]);

  // Resolve whatever `labels` and `initialOptions` together do not cover.
  // Keyed on the joined id list, so a round that resolves only some of its
  // ids shrinks `missingKey` and fires again for the rest — `labels` only
  // ever grows and `initialOptions` is assumed stable in content once it
  // covers an id (see `initialOptionsById` above), so `missingKey` can only
  // shrink or hold steady across firings, and it stops once a round resolves
  // nothing at all.
  //
  // The `initialOptionsById` check is what actually keeps this from
  // resolving over the network an id the caller already named: if this only
  // consulted `labels`, the very render that first hands in a new `value` id
  // alongside its `initialOptions` label — the common case, per
  // `initialOptionsById` above — would still compute a `missingKey` that
  // includes it, since `labels` has not caught up yet, and this effect would
  // fire regardless of what the merge effect above goes on to do with that
  // same render's state update.
  const missingKey = value.filter((id) => !labels.has(id) && !initialOptionsById.has(id)).join(",");
  useEffect(() => {
    if (missingKey === "") return;
    let cancelled = false;
    resolveLabels(missingKey.split(","))
      .then((options) => {
        if (cancelled) return;
        if (options.length === 0) return;
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
              label={labels.get(id) ?? initialOptionsById.get(id) ?? id}
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
