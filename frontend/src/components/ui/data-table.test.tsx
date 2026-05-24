import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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

  it("shows loading spinner when loading is true", () => {
    render(<DataTable columns={COLUMNS} rows={[]} loading getRowKey={(r) => r.id} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("does not render data rows when loading", () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} loading getRowKey={(r) => r.id} />);
    expect(screen.queryByText("Alpha")).not.toBeInTheDocument();
  });

  it("loading cell spans all columns", () => {
    render(<DataTable columns={COLUMNS} rows={[]} loading getRowKey={(r) => r.id} />);
    const cell = screen.getByRole("status").closest("td");
    expect(cell).toHaveAttribute("colspan", "2");
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
});
