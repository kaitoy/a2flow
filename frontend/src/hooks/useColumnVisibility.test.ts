import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { ColumnDef } from "@/components/ui/data-table";
import { useColumnVisibility } from "./useColumnVisibility";

interface Row {
  id: string;
}

const cell = (r: Row) => r.id;

/** A table with one column of each visibility, plus an unlabeled always-on column. */
const COLUMNS: ColumnDef<Row>[] = [
  { header: "", visibility: "always", cell },
  { header: "Name", visibility: "always", cell },
  { header: "Type", cell },
  { header: "Reference", visibility: "optional", cell },
  { header: "Actions", visibility: "always", cell },
];

/** Headers of the columns the hook says to render. */
function headers(columns: ColumnDef<Row>[]): string[] {
  return columns.map((col) => col.header);
}

/** The raw stored value for a table, or null when nothing is stored. */
function stored(key: string): string | null {
  return window.localStorage.getItem(`a2flow.columns.${key}`);
}

afterEach(() => window.localStorage.clear());

describe("useColumnVisibility", () => {
  it("shows default columns and hides optional ones when nothing is stored", () => {
    const { result } = renderHook(() => useColumnVisibility("secrets", COLUMNS));
    expect(headers(result.current.visibleColumns)).toEqual(["", "Name", "Type", "Actions"]);
    expect(result.current.selected).toEqual(["Type"]);
    expect(result.current.customized).toBe(false);
  });

  it("offers every column except the always-visible ones", () => {
    const { result } = renderHook(() => useColumnVisibility("secrets", COLUMNS));
    expect(result.current.options).toEqual([
      { value: "Type", label: "Type" },
      { value: "Reference", label: "Reference" },
    ]);
  });

  it("shows an optional column once it is selected", () => {
    const { result } = renderHook(() => useColumnVisibility("secrets", COLUMNS));
    act(() => result.current.setSelected(["Type", "Reference"]));
    expect(headers(result.current.visibleColumns)).toEqual([
      "",
      "Name",
      "Type",
      "Reference",
      "Actions",
    ]);
    expect(result.current.customized).toBe(true);
  });

  it("hides a default column once it is deselected", () => {
    const { result } = renderHook(() => useColumnVisibility("secrets", COLUMNS));
    act(() => result.current.setSelected([]));
    expect(headers(result.current.visibleColumns)).toEqual(["", "Name", "Actions"]);
  });

  it("stores only the departures from the declared defaults", () => {
    const { result } = renderHook(() => useColumnVisibility("secrets", COLUMNS));
    act(() => result.current.setSelected(["Reference"]));
    expect(JSON.parse(stored("secrets") as string)).toEqual({ Type: false, Reference: true });
  });

  it("stores nothing while the selection matches the defaults", () => {
    const { result } = renderHook(() => useColumnVisibility("secrets", COLUMNS));
    act(() => result.current.setSelected(["Type"]));
    expect(stored("secrets")).toBeNull();
  });

  it("restores the stored selection on mount", () => {
    window.localStorage.setItem("a2flow.columns.secrets", JSON.stringify({ Reference: true }));
    const { result } = renderHook(() => useColumnVisibility("secrets", COLUMNS));
    expect(result.current.selected).toEqual(["Type", "Reference"]);
    expect(result.current.customized).toBe(true);
  });

  it("scopes the stored selection to its own key", () => {
    window.localStorage.setItem("a2flow.columns.users", JSON.stringify({ Reference: true }));
    const { result } = renderHook(() => useColumnVisibility("secrets", COLUMNS));
    expect(result.current.selected).toEqual(["Type"]);
  });

  it("leaves a column added after the preference was stored at its declared default", () => {
    window.localStorage.setItem("a2flow.columns.secrets", JSON.stringify({ Type: false }));
    const { result } = renderHook(() => useColumnVisibility("secrets", COLUMNS));
    // "Reference" predates nothing in the stored map, so it keeps its own default.
    expect(headers(result.current.visibleColumns)).toEqual(["", "Name", "Actions"]);
  });

  it("ignores a stored entry for a column the table no longer has", () => {
    window.localStorage.setItem("a2flow.columns.secrets", JSON.stringify({ Retired: true }));
    const { result } = renderHook(() => useColumnVisibility("secrets", COLUMNS));
    expect(headers(result.current.visibleColumns)).toEqual(["", "Name", "Type", "Actions"]);
    expect(result.current.customized).toBe(false);
  });

  it("falls back to the defaults on a malformed stored value", () => {
    window.localStorage.setItem("a2flow.columns.secrets", "not json");
    const { result } = renderHook(() => useColumnVisibility("secrets", COLUMNS));
    expect(result.current.selected).toEqual(["Type"]);
  });

  it("clears the stored preference on reset", () => {
    const { result } = renderHook(() => useColumnVisibility("secrets", COLUMNS));
    act(() => result.current.setSelected(["Reference"]));
    expect(stored("secrets")).not.toBeNull();

    act(() => result.current.reset());
    expect(stored("secrets")).toBeNull();
    expect(result.current.selected).toEqual(["Type"]);
    expect(result.current.customized).toBe(false);
  });

  it("keeps working when localStorage throws", () => {
    const getItem = Storage.prototype.getItem;
    Storage.prototype.getItem = () => {
      throw new Error("denied");
    };
    try {
      const { result } = renderHook(() => useColumnVisibility("secrets", COLUMNS));
      expect(result.current.selected).toEqual(["Type"]);
    } finally {
      Storage.prototype.getItem = getItem;
    }
  });
});
