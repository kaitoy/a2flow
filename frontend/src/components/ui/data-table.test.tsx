import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { type ColumnDef, DataTable } from "./data-table";

interface Row {
  id: string;
  name: string;
  value: number;
}

const COLUMNS: ColumnDef<Row>[] = [
  { header: "Name", cell: (r) => r.name },
  { header: "Value", cell: (r) => String(r.value) },
];

const ROWS: Row[] = [
  { id: "1", name: "Alpha", value: 10 },
  { id: "2", name: "Beta", value: 20 },
];

describe("DataTable", () => {
  it("renders column headers", () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} getRowKey={(r) => r.id} />);
    expect(screen.getByRole("columnheader", { name: "Name" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Value" })).toBeInTheDocument();
  });

  it("renders a row for each data item", () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} getRowKey={(r) => r.id} />);
    expect(screen.getByText("Alpha")).toBeInTheDocument();
    expect(screen.getByText("Beta")).toBeInTheDocument();
  });

  it("renders cell content returned by cell() function", () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} getRowKey={(r) => r.id} />);
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("20")).toBeInTheDocument();
  });

  it("renders ReactNode cell content", () => {
    const cols: ColumnDef<Row>[] = [
      { header: "Name", cell: (r) => <strong data-testid="bold">{r.name}</strong> },
    ];
    render(<DataTable columns={cols} rows={[ROWS[0]]} getRowKey={(r) => r.id} />);
    expect(screen.getByTestId("bold")).toBeInTheDocument();
    expect(screen.getByTestId("bold").textContent).toBe("Alpha");
  });

  it("exposes role=status on the wrapper when loading", () => {
    render(<DataTable columns={COLUMNS} rows={[]} loading getRowKey={(r) => r.id} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders skeletonRows placeholder rows while loading", () => {
    const { container } = render(
      <DataTable columns={COLUMNS} rows={[]} loading skeletonRows={3} getRowKey={(r) => r.id} />
    );
    expect(container.querySelectorAll("tbody tr")).toHaveLength(3);
    // Each placeholder row has a skeleton cell per column.
    expect(container.querySelectorAll("tbody .skeleton")).toHaveLength(3 * COLUMNS.length);
  });

  it("does not render data rows when loading", () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} loading getRowKey={(r) => r.id} />);
    expect(screen.queryByText("Alpha")).not.toBeInTheDocument();
  });

  it("shows default empty message when rows is empty and not loading", () => {
    render(<DataTable columns={COLUMNS} rows={[]} getRowKey={(r) => r.id} />);
    expect(screen.getByText("No data.")).toBeInTheDocument();
  });

  it("shows custom emptyMessage when provided", () => {
    render(
      <DataTable
        columns={COLUMNS}
        rows={[]}
        emptyMessage="Nothing here yet."
        getRowKey={(r) => r.id}
      />
    );
    expect(screen.getByText("Nothing here yet.")).toBeInTheDocument();
  });

  it("empty cell spans all columns", () => {
    render(<DataTable columns={COLUMNS} rows={[]} getRowKey={(r) => r.id} />);
    const cell = screen.getByText("No data.").closest("td");
    expect(cell).toHaveAttribute("colspan", "2");
  });

  it("does not show empty message when loading even with empty rows", () => {
    render(<DataTable columns={COLUMNS} rows={[]} loading getRowKey={(r) => r.id} />);
    expect(screen.queryByText("No data.")).not.toBeInTheDocument();
  });

  it("applies column className to td elements", () => {
    const cols: ColumnDef<Row>[] = [
      { header: "Name", cell: (r) => r.name, className: "max-w-[200px] truncate" },
    ];
    render(<DataTable columns={cols} rows={[ROWS[0]]} getRowKey={(r) => r.id} />);
    const cell = screen.getByText("Alpha").closest("td");
    expect(cell?.className).toContain("truncate");
  });

  it("td always has base px-5 py-3 padding class", () => {
    render(<DataTable columns={COLUMNS} rows={[ROWS[0]]} getRowKey={(r) => r.id} />);
    const cell = screen.getByText("Alpha").closest("td");
    expect(cell?.className).toContain("px-5");
    expect(cell?.className).toContain("py-3");
  });

  it("wrapper div has glass-panel class", () => {
    const { container } = render(
      <DataTable columns={COLUMNS} rows={ROWS} getRowKey={(r) => r.id} />
    );
    expect(container.firstChild).toHaveClass("glass-panel");
  });

  it("wraps truncate columns in a single-line clipping span", () => {
    const cols: ColumnDef<Row>[] = [{ header: "Name", truncate: true, cell: (r) => r.name }];
    render(<DataTable columns={cols} rows={[ROWS[0]]} getRowKey={(r) => r.id} />);
    expect(screen.getByText("Alpha").className).toContain("truncate");
  });

  it("renders a resize handle for every column", () => {
    const { container } = render(
      <DataTable columns={COLUMNS} rows={ROWS} getRowKey={(r) => r.id} />
    );
    expect(container.querySelectorAll("[data-resize-handle]")).toHaveLength(COLUMNS.length);
  });

  it("cycles a column's sort asc → desc → none on header click", async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();
    const cols: ColumnDef<Row>[] = [{ header: "Name", sortField: "name", cell: (r) => r.name }];
    const { rerender } = render(
      <DataTable
        columns={cols}
        rows={ROWS}
        getRowKey={(r) => r.id}
        sort={null}
        onSortChange={onSortChange}
      />
    );
    await user.click(screen.getByRole("button", { name: /Name/ }));
    expect(onSortChange).toHaveBeenLastCalledWith({ field: "name", descending: false });

    rerender(
      <DataTable
        columns={cols}
        rows={ROWS}
        getRowKey={(r) => r.id}
        sort={{ field: "name", descending: false }}
        onSortChange={onSortChange}
      />
    );
    await user.click(screen.getByRole("button", { name: /Name/ }));
    expect(onSortChange).toHaveBeenLastCalledWith({ field: "name", descending: true });

    rerender(
      <DataTable
        columns={cols}
        rows={ROWS}
        getRowKey={(r) => r.id}
        sort={{ field: "name", descending: true }}
        onSortChange={onSortChange}
      />
    );
    await user.click(screen.getByRole("button", { name: /Name/ }));
    expect(onSortChange).toHaveBeenLastCalledWith(null);
  });

  it("does not render a sort button without onSortChange", () => {
    const cols: ColumnDef<Row>[] = [{ header: "Name", sortField: "name", cell: (r) => r.name }];
    render(<DataTable columns={cols} rows={ROWS} getRowKey={(r) => r.id} />);
    expect(screen.queryByRole("button", { name: /Name/ })).not.toBeInTheDocument();
  });

  it("emits a filter spec when a select filter changes", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();
    const cols: ColumnDef<Row>[] = [
      {
        header: "Name",
        filterField: "name",
        filterOp: "eq",
        filterOptions: [{ label: "Alpha", value: "alpha" }],
        cell: (r) => r.name,
      },
    ];
    render(
      <DataTable
        columns={cols}
        rows={ROWS}
        getRowKey={(r) => r.id}
        filters={[]}
        onFilterChange={onFilterChange}
      />
    );
    await user.click(screen.getByRole("button", { name: "Filter Name" }));
    const select = await screen.findByRole("combobox");
    await user.selectOptions(select, "alpha");
    expect(onFilterChange).toHaveBeenCalledWith([{ field: "name", op: "eq", value: "alpha" }]);
  });
});
