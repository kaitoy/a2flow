import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type ColumnDef, DataTable, fitColumnWidths } from "./data-table";

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

  it("wrapper scrolls horizontally instead of clipping overflowing columns", () => {
    const { container } = render(
      <DataTable columns={COLUMNS} rows={ROWS} getRowKey={(r) => r.id} />
    );
    expect(container.firstChild).toHaveClass("overflow-x-auto");
    expect(container.firstChild).not.toHaveClass("overflow-hidden");
  });

  it("wraps cells in a single-line clipping span by default", () => {
    render(<DataTable columns={COLUMNS} rows={[ROWS[0]]} getRowKey={(r) => r.id} />);
    expect(screen.getByText("Alpha").className).toContain("truncate");
  });

  it("renders noTruncate columns without a clipping span", () => {
    const cols: ColumnDef<Row>[] = [{ header: "Name", noTruncate: true, cell: (r) => r.name }];
    render(<DataTable columns={cols} rows={[ROWS[0]]} getRowKey={(r) => r.id} />);
    expect(screen.getByText("Alpha").className).not.toContain("truncate");
  });

  it("separates columns with a vertical divider on all but the last cell", () => {
    const { container } = render(
      <DataTable columns={COLUMNS} rows={[ROWS[0]]} getRowKey={(r) => r.id} />
    );
    // Header cells: divider on every column except the last.
    const headers = container.querySelectorAll("thead th");
    expect(headers[0].className).toContain("border-r");
    // Body cells carry the same not-last-child divider utility.
    const cells = container.querySelectorAll("tbody td");
    expect(cells[0].className).toContain("border-r");
  });

  it("zebra-stripes body rows via the even variant", () => {
    const { container } = render(
      <DataTable columns={COLUMNS} rows={ROWS} getRowKey={(r) => r.id} />
    );
    const rows = container.querySelectorAll("tbody tr");
    expect(rows[0].className).toContain("even:bg-glass-strong/15");
  });

  it("renders a resize handle for every column", () => {
    const { container } = render(
      <DataTable columns={COLUMNS} rows={ROWS} getRowKey={(r) => r.id} />
    );
    expect(container.querySelectorAll("[data-resize-handle]")).toHaveLength(COLUMNS.length);
  });

  it("sorts ascending, descending, and clears through the header menu", async () => {
    const user = userEvent.setup();
    const onSortChange = vi.fn();
    const cols: ColumnDef<Row>[] = [{ header: "Name", sortField: "name", cell: (r) => r.name }];
    /** Wait out the closing menu's exit animation so reopening never sees two panels. */
    const menuClosed = () =>
      waitFor(() =>
        expect(screen.queryByRole("button", { name: "Sort ascending" })).not.toBeInTheDocument()
      );
    const { rerender } = render(
      <DataTable
        columns={cols}
        rows={ROWS}
        getRowKey={(r) => r.id}
        sort={null}
        onSortChange={onSortChange}
      />
    );
    await user.click(screen.getByRole("button", { name: "Name" }));
    await user.click(await screen.findByRole("button", { name: "Sort ascending" }));
    expect(onSortChange).toHaveBeenLastCalledWith({ field: "name", descending: false });
    await menuClosed();

    rerender(
      <DataTable
        columns={cols}
        rows={ROWS}
        getRowKey={(r) => r.id}
        sort={{ field: "name", descending: false }}
        onSortChange={onSortChange}
      />
    );
    await user.click(screen.getByRole("button", { name: "Name" }));
    await user.click(await screen.findByRole("button", { name: "Sort descending" }));
    expect(onSortChange).toHaveBeenLastCalledWith({ field: "name", descending: true });
    await menuClosed();

    rerender(
      <DataTable
        columns={cols}
        rows={ROWS}
        getRowKey={(r) => r.id}
        sort={{ field: "name", descending: true }}
        onSortChange={onSortChange}
      />
    );
    // Clicking the already-active direction clears the sort.
    await user.click(screen.getByRole("button", { name: "Name" }));
    await user.click(await screen.findByRole("button", { name: "Sort descending" }));
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
    await user.click(screen.getByRole("button", { name: "Name" }));
    const select = await screen.findByRole("combobox");
    await user.selectOptions(select, "alpha");
    expect(onFilterChange).toHaveBeenCalledWith([{ field: "name", op: "eq", value: "alpha" }]);
  });

  it("renders one full-width menu trigger per interactive header", () => {
    const cols: ColumnDef<Row>[] = [{ header: "Name", filterField: "name", cell: (r) => r.name }];
    render(
      <DataTable
        columns={cols}
        rows={ROWS}
        getRowKey={(r) => r.id}
        filters={[]}
        onFilterChange={vi.fn()}
      />
    );
    const triggers = screen.getAllByRole("button");
    expect(triggers).toHaveLength(1);
    expect(triggers[0]).toHaveAccessibleName("Name");
    expect(triggers[0]).toHaveAttribute("aria-haspopup", "dialog");
    expect(triggers[0].className).toContain("w-full");
  });

  it("offers no sort actions on a filter-only column", async () => {
    const user = userEvent.setup();
    const cols: ColumnDef<Row>[] = [{ header: "Name", filterField: "name", cell: (r) => r.name }];
    render(
      <DataTable
        columns={cols}
        rows={ROWS}
        getRowKey={(r) => r.id}
        filters={[]}
        onFilterChange={vi.fn()}
      />
    );
    await user.click(screen.getByRole("button", { name: "Name" }));
    expect(await screen.findByRole("textbox")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sort ascending" })).not.toBeInTheDocument();
  });

  it("shows the active sort direction on the header trigger", () => {
    const cols: ColumnDef<Row>[] = [{ header: "Name", sortField: "name", cell: (r) => r.name }];
    const { container, rerender } = render(
      <DataTable
        columns={cols}
        rows={ROWS}
        getRowKey={(r) => r.id}
        sort={{ field: "name", descending: false }}
        onSortChange={vi.fn()}
      />
    );
    expect(container.querySelector("th .lucide-arrow-up")).toBeInTheDocument();

    rerender(
      <DataTable
        columns={cols}
        rows={ROWS}
        getRowKey={(r) => r.id}
        sort={{ field: "name", descending: true }}
        onSortChange={vi.fn()}
      />
    );
    expect(container.querySelector("th .lucide-arrow-down")).toBeInTheDocument();

    rerender(
      <DataTable
        columns={cols}
        rows={ROWS}
        getRowKey={(r) => r.id}
        sort={null}
        onSortChange={vi.fn()}
      />
    );
    // Unsorted headers show the subtle menu chevron instead.
    expect(container.querySelector("th .lucide-chevron-down")).toBeInTheDocument();
  });

  it("shows the filter indicator on the header trigger only while a filter is applied", () => {
    const cols: ColumnDef<Row>[] = [{ header: "Name", filterField: "name", cell: (r) => r.name }];
    const { container, rerender } = render(
      <DataTable
        columns={cols}
        rows={ROWS}
        getRowKey={(r) => r.id}
        filters={[]}
        onFilterChange={vi.fn()}
      />
    );
    expect(container.querySelector('[data-filter-indicator="idle"]')).toBeInTheDocument();

    rerender(
      <DataTable
        columns={cols}
        rows={ROWS}
        getRowKey={(r) => r.id}
        filters={[{ field: "name", op: "like", value: "a" }]}
        onFilterChange={vi.fn()}
      />
    );
    expect(container.querySelector('[data-filter-indicator="active"]')).toBeInTheDocument();
  });
});

/**
 * jsdom has no layout engine (`offsetWidth`/`clientWidth` are always 0), so the
 * fitting cannot be driven through a render — it is exercised as a pure function.
 */
describe("fitColumnWidths", () => {
  /** Mirrors MIN_WIDTH in data-table.tsx. */
  const MIN_WIDTH = 60;

  const cell = (r: Row) => r.name;
  const FIT_COLUMNS: ColumnDef<Row>[] = [
    { header: "Name", cell },
    { header: "Prompt", cell },
    { header: "Actions", noTruncate: true, cell },
  ];

  const sum = (widths: Record<string, number>) =>
    Object.values(widths).reduce((total, w) => total + w, 0);

  it("leaves widths untouched when they already fit", () => {
    const natural = { Name: 200, Prompt: 300, Actions: 100 };
    expect(fitColumnWidths(FIT_COLUMNS, natural, 800)).toEqual(natural);
  });

  it("leaves widths untouched before the container has been laid out", () => {
    const natural = { Name: 200, Prompt: 800, Actions: 100 };
    expect(fitColumnWidths(FIT_COLUMNS, natural, 0)).toEqual(natural);
  });

  it("takes the shortfall out of the oversized column, sparing the narrow one", () => {
    const fitted = fitColumnWidths(FIT_COLUMNS, { Name: 200, Prompt: 800, Actions: 100 }, 600);
    // Shrinking proportionally would drag Name down to 100px — narrow enough to
    // clip its own header — purely to spare Prompt, which has width to burn.
    expect(fitted).toEqual({ Name: 200, Prompt: 300, Actions: 100 });
    expect(sum(fitted)).toBe(600);
  });

  it("shares one ceiling between the oversized columns", () => {
    const columns: ColumnDef<Row>[] = [
      { header: "Name", cell },
      { header: "Prompt", cell },
      { header: "Description", cell },
      { header: "Actions", noTruncate: true, cell },
    ];
    const fitted = fitColumnWidths(
      columns,
      { Name: 100, Prompt: 600, Description: 500, Actions: 100 },
      700
    );
    expect(fitted).toEqual({ Name: 100, Prompt: 250, Description: 250, Actions: 100 });
    expect(sum(fitted)).toBe(700);
  });

  it("keeps noTruncate columns at their natural width", () => {
    const fitted = fitColumnWidths(FIT_COLUMNS, { Name: 200, Prompt: 800, Actions: 100 }, 600);
    expect(fitted.Actions).toBe(100);
  });

  it("keeps explicitly sized columns at their natural width", () => {
    const columns: ColumnDef<Row>[] = [
      { header: "Icon", width: 40, cell },
      { header: "Name", cell },
      { header: "Actions", noTruncate: true, cell },
    ];
    const fitted = fitColumnWidths(columns, { Icon: 40, Name: 800, Actions: 100 }, 500);
    expect(fitted).toEqual({ Icon: 40, Name: 360, Actions: 100 });
    expect(sum(fitted)).toBe(500);
  });

  it("floors every column and tolerates overflow when nothing can fit", () => {
    const fitted = fitColumnWidths(FIT_COLUMNS, { Name: 100, Prompt: 900, Actions: 300 }, 200);
    // The action buttons alone already overrun the panel, so the panel scrolls —
    // but no column is ever squeezed to nothing, and the buttons stay clickable.
    expect(fitted).toEqual({ Name: MIN_WIDTH, Prompt: MIN_WIDTH, Actions: 300 });
  });

  it("raises a narrow column to its header width even when everything fits", () => {
    // A full-width header trigger contributes nothing to the browser's natural
    // table layout, so a noTruncate column with short body content (a status
    // chip) can measure narrower than its own header. The fit raises it.
    const fitted = fitColumnWidths(FIT_COLUMNS, { Name: 200, Prompt: 300, Actions: 100 }, 800, {
      Actions: 140,
    });
    expect(fitted).toEqual({ Name: 200, Prompt: 300, Actions: 140 });
  });

  it("floors a column at its header width instead of the absolute minimum", () => {
    const fitted = fitColumnWidths(FIT_COLUMNS, { Name: 100, Prompt: 900, Actions: 300 }, 200, {
      Name: 120,
    });
    // Name stops at its own header width — never ellipsizing the label — while
    // Prompt, whose header is narrow, still falls back to the absolute floor.
    expect(fitted).toEqual({ Name: 120, Prompt: MIN_WIDTH, Actions: 300 });
  });

  it("ignores header minima below the absolute floor", () => {
    const fitted = fitColumnWidths(FIT_COLUMNS, { Name: 100, Prompt: 900, Actions: 300 }, 200, {
      Name: 30,
      Prompt: 30,
    });
    expect(fitted).toEqual({ Name: MIN_WIDTH, Prompt: MIN_WIDTH, Actions: 300 });
  });

  it("overflows rather than shrinking below the header floors", () => {
    const fitted = fitColumnWidths(FIT_COLUMNS, { Name: 300, Prompt: 300, Actions: 100 }, 250, {
      Name: 150,
      Prompt: 150,
    });
    // The floors alone (150 + 150 + 100) exceed the panel, so the panel scrolls.
    expect(fitted).toEqual({ Name: 150, Prompt: 150, Actions: 100 });
  });
});

/**
 * The fitting is driven by real measurements, which jsdom never produces
 * (`offsetWidth`/`clientWidth` are always 0). Stub the layout so the measure →
 * fit → refit path can be exercised end to end through the component.
 */
describe("DataTable column fitting", () => {
  const cell = (r: Row) => r.name;
  const COLS: ColumnDef<Row>[] = [
    { header: "Name", cell },
    { header: "Prompt", cell },
    { header: "Actions", noTruncate: true, cell },
  ];

  /** Natural width each column reports, keyed by its header text. */
  const NATURAL: Record<string, number> = { Name: 200, Prompt: 800, Actions: 100 };

  /** Label width each hidden header sizer reports, keyed by its text. */
  const SIZER: Record<string, number> = { Name: 80 };

  /**
   * Chrome the component adds around a measured sizer on a non-interactive
   * header. Mirrors TH_PADDING_X + RESIZE_HANDLE_ALLOWANCE in data-table.tsx.
   */
  const HEADER_CHROME = 42;

  let panelWidth = 600;
  /** Every ResizeObserver the render creates, so a resize can be replayed. */
  let observerCallbacks: ResizeObserverCallback[] = [];

  class RecordingResizeObserver {
    constructor(callback: ResizeObserverCallback) {
      observerCallbacks.push(callback);
    }
    observe() {}
    unobserve() {}
    disconnect() {}
  }

  beforeEach(() => {
    Object.defineProperty(HTMLTableCellElement.prototype, "offsetWidth", {
      configurable: true,
      get(this: HTMLTableCellElement) {
        // Header cells carry their label on the hidden sizer; body cells fall
        // back to their text content.
        const label =
          this.querySelector("[data-header-sizer]")?.getAttribute("data-label") ??
          this.textContent ??
          "";
        return NATURAL[label.trim()] ?? 0;
      },
    });
    Object.defineProperty(HTMLSpanElement.prototype, "offsetWidth", {
      configurable: true,
      get(this: HTMLSpanElement) {
        if (!this.hasAttribute("data-header-sizer")) return 0;
        return SIZER[this.getAttribute("data-label") ?? ""] ?? 0;
      },
    });
    Object.defineProperty(HTMLDivElement.prototype, "clientWidth", {
      configurable: true,
      get: () => panelWidth,
    });
    vi.stubGlobal("ResizeObserver", RecordingResizeObserver);
  });

  afterEach(() => {
    // Drop the overrides so the inherited (always-zero) jsdom getters come back
    // and the other suites in this file keep their unstubbed layout.
    Reflect.deleteProperty(HTMLTableCellElement.prototype, "offsetWidth");
    Reflect.deleteProperty(HTMLSpanElement.prototype, "offsetWidth");
    Reflect.deleteProperty(HTMLDivElement.prototype, "clientWidth");
    vi.unstubAllGlobals();
    observerCallbacks = [];
    panelWidth = 600;
  });

  /** Column widths currently written into the table's `<colgroup>`. */
  const colWidths = (container: HTMLElement) =>
    [...container.querySelectorAll("colgroup col")].map((col) =>
      Number.parseInt((col as HTMLElement).style.width, 10)
    );

  /** Replay a container resize, which the observer would deliver in a browser. */
  const resizePanel = (width: number) => {
    panelWidth = width;
    act(() => {
      for (const callback of observerCallbacks) {
        callback([], {} as ResizeObserver);
      }
    });
  };

  it("fits the measured columns into the panel", () => {
    const { container } = render(<DataTable columns={COLS} rows={ROWS} getRowKey={(r) => r.id} />);
    // Natural widths total 1100 in a 600px panel: Prompt gives up the 200px
    // shortfall, Name keeps its natural width, Actions is never touched.
    expect(colWidths(container)).toEqual([200, 300, 100]);
  });

  it("refits the columns when the panel shrinks", () => {
    const { container } = render(<DataTable columns={COLS} rows={ROWS} getRowKey={(r) => r.id} />);
    resizePanel(400);
    // Prompt alone can no longer absorb the shortfall, so Name joins it at the
    // shared ceiling rather than the table overflowing.
    expect(colWidths(container)).toEqual([150, 150, 100]);
  });

  it("refits from the natural widths rather than ratcheting down", () => {
    const { container } = render(<DataTable columns={COLS} rows={ROWS} getRowKey={(r) => r.id} />);
    resizePanel(400);
    resizePanel(600);
    // Widening again restores the original fit; the shrink is not cumulative.
    expect(colWidths(container)).toEqual([200, 300, 100]);
  });

  it("does not measure until rows have arrived", () => {
    const { container } = render(
      <DataTable columns={COLS} rows={[]} loading getRowKey={(r) => r.id} />
    );
    // Skeleton rows are not representative, so no width is frozen from them.
    expect(colWidths(container)).toEqual([Number.NaN, Number.NaN, Number.NaN]);
  });

  it("never fits a column below its header content width", () => {
    const { container } = render(<DataTable columns={COLS} rows={ROWS} getRowKey={(r) => r.id} />);
    resizePanel(300);
    // The shared ceiling lands at 100, but Name's floor is its measured header
    // label (80) plus the header chrome = 122, so it stops there and the panel
    // overflows slightly; Prompt's header is narrow, so the ceiling takes it.
    expect(colWidths(container)).toEqual([SIZER.Name + HEADER_CHROME, 100, 100]);
  });
});
