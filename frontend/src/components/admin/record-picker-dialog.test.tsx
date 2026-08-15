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

const COLUMNS: ColumnDef<Row>[] = [{ header: "Name", visibility: "always", cell: (r) => r.name }];

/** A `filterKind: "tags"` column, for the tag-filter-wiring test below. */
const TAG_COLUMN: ColumnDef<Row> = {
  header: "Tags",
  filterKind: "tags",
  tagOptions: [{ value: "t1", label: "prod" }],
  cell: () => null,
};

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
  // `props` (the caller's fixed overrides) is captured once and merged under
  // every `overrides` passed to `rerender`, so a rerender only needs to state
  // what changed — e.g. `{ open: false }` — without repeating the rest.
  const build = (overrides: Partial<RecordPickerDialogProps<Row>>) => (
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
      {...overrides}
    />
  );
  const result = render(build({}));
  return {
    onAssign,
    rerender: (overrides: Partial<RecordPickerDialogProps<Row>>) =>
      result.rerender(build(overrides)),
  };
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
    await user.click(screen.getByRole("button", { name: "Select" }));

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
    await user.click(screen.getByRole("button", { name: "Select" }));

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

  it("re-seeds the draft from value on the closed-to-open transition", async () => {
    const user = userEvent.setup();
    const { rerender } = renderDialog({ value: ["r01"] });

    await waitFor(() => expect(screen.getByRole("checkbox", { name: "Row 01" })).toBeChecked());
    await user.click(screen.getByRole("checkbox", { name: "Row 02" }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();

    rerender({ open: false });
    rerender({ open: true });

    await waitFor(() => expect(screen.getByRole("checkbox", { name: "Row 01" })).toBeChecked());
    expect(screen.getByRole("checkbox", { name: "Row 02" })).not.toBeChecked();
    expect(screen.getByText("1 selected")).toBeInTheDocument();
  });

  it("keeps the draft when the parent re-renders with a new but equal value array", async () => {
    const user = userEvent.setup();
    const { rerender } = renderDialog({ value: ["r01"] });

    await waitFor(() => expect(screen.getByRole("checkbox", { name: "Row 01" })).toBeChecked());
    await user.click(screen.getByRole("checkbox", { name: "Row 02" }));
    expect(screen.getByText("2 selected")).toBeInTheDocument();

    // A fresh array instance carrying the same ids, not the same reference —
    // the shape a parent's re-render would pass without memoizing `value`.
    rerender({ value: ["r01"] });

    expect(screen.getByRole("checkbox", { name: "Row 02" })).toBeChecked();
    expect(screen.getByText("2 selected")).toBeInTheDocument();
  });

  it("passes a filterKind: tags column's picks through to the record fetch", async () => {
    const user = userEvent.setup();
    const listRecords = vi.fn(listRows);
    renderDialog({ columns: [...COLUMNS, TAG_COLUMN], listRecords });

    await user.click(await screen.findByRole("button", { name: /Tags/ }));
    await user.click(await screen.findByRole("checkbox", { name: "prod" }));

    await waitFor(() =>
      expect(listRecords).toHaveBeenLastCalledWith(expect.objectContaining({ tagIds: ["t1"] }))
    );
  });

  describe("single-select", () => {
    it("lists the records with a radio each instead of a checkbox", async () => {
      renderDialog({ multiple: false });
      expect(await screen.findByRole("radio", { name: "Row 01" })).toBeInTheDocument();
      expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    });

    it("pre-selects the record already assigned", async () => {
      renderDialog({ multiple: false, value: ["r01"] });
      await waitFor(() => expect(screen.getByRole("radio", { name: "Row 01" })).toBeChecked());
      expect(screen.getByRole("radio", { name: "Row 02" })).not.toBeChecked();
    });

    it("replaces the draft rather than adding to it", async () => {
      const user = userEvent.setup();
      const { onAssign } = renderDialog({ multiple: false });

      await user.click(await screen.findByRole("radio", { name: "Row 02" }));
      await user.click(screen.getByRole("radio", { name: "Row 03" }));
      await user.click(screen.getByRole("button", { name: "Select" }));

      expect(screen.getByRole("radio", { name: "Row 02" })).not.toBeChecked();
      expect(onAssign).toHaveBeenCalledWith(["r03"], [{ value: "r03", label: "Row 03" }]);
    });

    it("names the pick in the footer instead of counting it", async () => {
      const user = userEvent.setup();
      renderDialog({ multiple: false });

      expect(await screen.findByText("None selected")).toBeInTheDocument();

      await user.click(screen.getByRole("radio", { name: "Row 02" }));

      // The name itself is asserted by the paging test below, where the chosen
      // row is off-screen and so the footer is its only occurrence; here the
      // point is that a count never appears.
      expect(screen.queryByText("None selected")).not.toBeInTheDocument();
      expect(screen.queryByText(/\d+ selected/)).not.toBeInTheDocument();
    });

    it("keeps a pick made on a page the operator has paged away from", async () => {
      const user = userEvent.setup();
      const { onAssign } = renderDialog({ multiple: false });

      await user.click(await screen.findByRole("radio", { name: "Row 01" }));
      await user.click(screen.getByRole("button", { name: /next/i }));
      await screen.findByRole("radio", { name: "Row 11" });

      // The chosen row is off-screen, so the footer is the only thing that can
      // still name it — which is what `labels` exists for.
      expect(screen.getByText("Row 01")).toBeInTheDocument();

      await user.click(screen.getByRole("button", { name: "Select" }));
      expect(onAssign).toHaveBeenCalledWith(["r01"], [{ value: "r01", label: "Row 01" }]);
    });
  });
});
