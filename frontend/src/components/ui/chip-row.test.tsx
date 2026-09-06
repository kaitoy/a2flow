import userEvent from "@testing-library/user-event";
import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, within } from "@/test/test-utils";
import { ChipRow, type ChipRowItem } from "./chip-row";

/**
 * jsdom performs no layout, so every width is 0 and the fold could never
 * trigger. Stub the two measurements `ChipRow` takes — each chip's own width
 * and the row's available width — the same way `data-table.test.tsx` stubs the
 * table's, so the measure → fit → refit path runs end to end.
 */
describe("ChipRow", () => {
  const ITEMS: ChipRowItem[] = [
    { key: "a", label: "alpha", color: "rose" },
    { key: "b", label: "bravo", color: "amber" },
    { key: "c", label: "charlie", color: "cyan", description: "the third one" },
    { key: "d", label: "delta", color: "violet" },
  ];

  /** Width every tag chip reports. Uniform, so the arithmetic stays readable. */
  const CHIP_WIDTH = 100;

  let rowWidth = 600;
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
    Object.defineProperty(HTMLSpanElement.prototype, "offsetWidth", {
      configurable: true,
      get: () => CHIP_WIDTH,
    });
    Object.defineProperty(HTMLDivElement.prototype, "clientWidth", {
      configurable: true,
      get: () => rowWidth,
    });
    vi.stubGlobal("ResizeObserver", RecordingResizeObserver);
  });

  afterEach(() => {
    Reflect.deleteProperty(HTMLSpanElement.prototype, "offsetWidth");
    Reflect.deleteProperty(HTMLDivElement.prototype, "clientWidth");
    vi.unstubAllGlobals();
    observerCallbacks = [];
    rowWidth = 600;
  });

  /** Replay a container resize, which the observer would deliver in a browser. */
  const resizeRow = (width: number) => {
    rowWidth = width;
    act(() => {
      for (const callback of observerCallbacks) callback([], {} as ResizeObserver);
    });
  };

  it("shows every chip when they all fit", () => {
    render(<ChipRow items={ITEMS} />);
    // 4 × 100 plus three 4px gaps = 412, inside the 600px row.
    for (const item of ITEMS) expect(screen.getByText(item.label)).toBeInTheDocument();
    expect(screen.queryByText(/^\+/)).not.toBeInTheDocument();
  });

  it("folds the chips that do not fit into a single counted chip", () => {
    rowWidth = 300;
    render(<ChipRow items={ITEMS} />);
    // Two chips (204px) fit alongside the reserved `+N` width; the rest fold.
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("bravo")).toBeInTheDocument();
    expect(screen.getByText("+2")).toBeInTheDocument();
    expect(screen.queryByText("charlie")).not.toBeInTheDocument();
  });

  it("opens a dialog listing every chip when the +N chip is clicked", async () => {
    const user = userEvent.setup();
    rowWidth = 300;
    render(<ChipRow items={ITEMS} title="Tags" />);

    await user.click(screen.getByRole("button", { name: "Show all 4 tags" }));
    const dialog = await screen.findByRole("dialog", { name: "Tags" });
    // The whole set, not the leftovers: the two chips still shown inline are in
    // the dialog too.
    for (const item of ITEMS) {
      expect(within(dialog).getByText(item.label)).toBeInTheDocument();
    }
  });

  it("shows a chip's description on hover inside the dialog", async () => {
    const user = userEvent.setup();
    rowWidth = 300;
    render(<ChipRow items={ITEMS} title="Tags" />);

    await user.click(screen.getByRole("button", { name: "Show all 4 tags" }));
    const dialog = await screen.findByRole("dialog", { name: "Tags" });
    await user.hover(within(dialog).getByText("charlie"));
    // The whole point of the dialog over the old tooltip: descriptions are
    // reachable on hover here.
    expect(await screen.findByRole("tooltip", {}, { timeout: 2000 })).toHaveTextContent(
      "the third one"
    );
  });

  it("hands the folded labels to assistive technology", () => {
    rowWidth = 300;
    const { container } = render(<ChipRow items={ITEMS} />);
    // Folded chips are unmounted, so a screen reader would otherwise be told
    // only that there are two more of something.
    expect(container.querySelector(".sr-only")).toHaveTextContent("charlie, delta");
  });

  it("folds every chip once not even the first one fits whole", () => {
    rowWidth = 120;
    render(<ChipRow items={ITEMS} />);
    // 120 leaves 84px beside the reserved count, under a chip's own 100px. A
    // pill clipped mid-label names its tag no better than "+4" does, and would
    // be the one thing to spill past the row's overflow — pushing the count,
    // the only mark saying there is more to see, out of the cell.
    expect(screen.getByText("+4")).toBeInTheDocument();
    expect(screen.queryByText("alpha")).not.toBeInTheDocument();
  });

  it("shows everything while the row has no measured width", () => {
    rowWidth = 0;
    render(<ChipRow items={ITEMS} />);
    // Not laid out yet — folding here would hide chips nobody has had a chance
    // to see, so the unmeasured state errs towards showing all of them.
    for (const item of ITEMS) expect(screen.getByText(item.label)).toBeInTheDocument();
    expect(screen.queryByText(/^\+/)).not.toBeInTheDocument();
  });

  it("refits when the row resizes", () => {
    render(<ChipRow items={ITEMS} />);
    expect(screen.queryByText(/^\+/)).not.toBeInTheDocument();

    resizeRow(300);
    expect(screen.getByText("+2")).toBeInTheDocument();

    // Widening refits from the cached natural widths rather than ratcheting.
    resizeRow(600);
    expect(screen.queryByText(/^\+/)).not.toBeInTheDocument();
    expect(screen.getByText("delta")).toBeInTheDocument();
  });

  it("re-measures when the chips themselves change", () => {
    rowWidth = 300;
    const { rerender } = render(<ChipRow items={ITEMS} />);
    expect(screen.getByText("+2")).toBeInTheDocument();

    rerender(<ChipRow items={ITEMS.slice(0, 2)} />);
    // The previous fit's survivors must not be mistaken for the whole set.
    expect(screen.getByText("alpha")).toBeInTheDocument();
    expect(screen.getByText("bravo")).toBeInTheDocument();
    expect(screen.queryByText(/^\+/)).not.toBeInTheDocument();
  });
});
