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

const COLUMNS: ColumnDef<Row>[] = [{ header: "Name", visibility: "always", cell: (r) => r.name }];

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
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
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
