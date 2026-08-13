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

  it("merges initialOptions that arrive together with value on a later render, not just at mount", async () => {
    // Mirrors the user detail page: GroupPicker mounts with `value=[]` and
    // `initialOptions=[]` as soon as `loading` flips false (driven by the
    // separate `getUser` fetch), and only later — when the membership fetch
    // resolves — do `value` and `initialOptions` change together, in the same
    // render, batched from the same `.then()` callback. The `useState`
    // initializer that seeds `labels` from `initialOptions` only ever runs
    // once, at mount, so it cannot see this update; something else has to.
    const resolveLabels = vi.fn(async (ids: string[]) =>
      ALL.filter((r) => ids.includes(r.id)).map((r) => ({ value: r.id, label: r.name }))
    );
    const onChange = vi.fn();
    const props: RecordPickerFieldProps<Row> = {
      label: "Groups",
      value: [],
      onChange,
      resolveLabels,
      listRecords: async () => ALL,
      columns: COLUMNS,
      getId: (r) => r.id,
      getLabel: (r) => r.name,
      panelId: "test-field-dialog",
      dialogTitle: "Select rows",
      selectLabel: "Select rows…",
      emptyMessage: "Nothing here.",
      emptyIcon: UsersRound,
    };
    const { rerender } = render(<RecordPickerField<Row> {...props} />);

    rerender(
      <RecordPickerField<Row>
        {...props}
        value={["a"]}
        initialOptions={[{ value: "a", label: "Alpha" }]}
      />
    );

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

  it("fetches no records before the operator opens the dialog", async () => {
    const user = userEvent.setup();
    const listRecords = vi.fn(async () => ALL);
    renderField({ listRecords });

    expect(listRecords).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: "Select rows…" }));

    await waitFor(() => expect(listRecords).toHaveBeenCalled());
  });

  it("keeps the dialog mounted across a close and reopen, so it does not refetch", async () => {
    // A collapse to `{open && <RecordPickerDialog ... />}` would still pass the
    // "fetches no records before first open" test above, since `open` is false
    // on the very first render either way. What actually distinguishes the two
    // implementations is what happens after the dialog has been opened once:
    // this field keeps it mounted, so a close-then-reopen must not issue a
    // second fetch. An eager-unmount regression would call `listRecords` again
    // on reopen and fail the final assertion.
    const user = userEvent.setup();
    const listRecords = vi.fn(async () => ALL);
    renderField({ listRecords });

    await user.click(screen.getByRole("button", { name: "Select rows…" }));
    await waitFor(() => expect(listRecords).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    // Cancel runs the dialog's leave animation on real timers before it
    // actually unmounts, so wait for it to finish closing.
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Select rows…" }));
    await waitFor(() => expect(screen.getByRole("dialog")).toBeInTheDocument());

    expect(listRecords).toHaveBeenCalledTimes(1);
  });

  it("applies the dialog's assignment", async () => {
    const user = userEvent.setup();
    const { onChange } = renderField();

    await user.click(screen.getByRole("button", { name: "Select rows…" }));
    await user.click(await screen.findByRole("checkbox", { name: "Bravo" }));
    await user.click(screen.getByRole("button", { name: "Select" }));

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
