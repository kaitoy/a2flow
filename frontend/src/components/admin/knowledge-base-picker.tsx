/**
 * @module KnowledgeBasePicker — Chooses the knowledge bases a workflow's agents may read.
 */
"use client";

import { BookOpen } from "lucide-react";
import { useCallback } from "react";
import type { PickerOption } from "@/components/admin/record-picker-dialog";
import { RecordPickerField } from "@/components/admin/record-picker-field";
import type { ColumnDef } from "@/components/ui/data-table";
import { type KnowledgeBase, listKnowledgeBases } from "@/lib/api";

/** Columns describing a knowledge base in the picker dialog. */
const COLUMNS: ColumnDef<KnowledgeBase>[] = [
  {
    header: "Name",
    sortField: "name",
    filterField: "name",
    visibility: "always",
    cell: (kb) => kb.name,
  },
  {
    header: "Description",
    cell: (kb) => kb.description || "—",
  },
];

/** Props for {@link KnowledgeBasePicker}. */
export interface KnowledgeBasePickerProps {
  /** Ids of the knowledge bases currently linked. */
  value: string[];
  /** Called with the next selection whenever it changes. */
  onChange: (next: string[]) => void;
  /** Render the selection as a read-only value instead of an editable field. */
  readOnly?: boolean;
  /** Labels the page already loaded, saving a label round trip. */
  initialOptions?: PickerOption[];
}

/** Controlled multi-select over the tenant's knowledge bases. */
export function KnowledgeBasePicker({
  value,
  onChange,
  readOnly = false,
  initialOptions,
}: KnowledgeBasePickerProps) {
  const resolveLabels = useCallback(async (ids: string[]): Promise<PickerOption[]> => {
    const kbs = await listKnowledgeBases({
      limit: ids.length,
      filters: [{ field: "id", op: "in", value: ids.join(",") }],
    });
    return kbs.map((kb) => ({ value: kb.id, label: kb.name }));
  }, []);

  return (
    <RecordPickerField<KnowledgeBase>
      label="Knowledge Bases"
      value={value}
      onChange={onChange}
      readOnly={readOnly}
      initialOptions={initialOptions}
      resolveLabels={resolveLabels}
      listRecords={listKnowledgeBases}
      columns={COLUMNS}
      getId={(kb) => kb.id}
      getLabel={(kb) => kb.name}
      panelId="knowledge-base-picker-dialog"
      dialogTitle="Select knowledge bases"
      selectLabel="Select knowledge bases…"
      emptyMessage="This tenant has no knowledge bases yet."
      emptyIcon={BookOpen}
    />
  );
}
