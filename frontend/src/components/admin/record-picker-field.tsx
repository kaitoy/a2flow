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
