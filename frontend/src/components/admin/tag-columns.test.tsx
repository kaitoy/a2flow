import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DataTable } from "@/components/ui/data-table";
import type { Tag } from "@/lib/api";
import { render, screen, within } from "@/test/test-utils";
import { tagFilterOptions, tagsColumn } from "./tag-columns";

interface Row {
  id: string;
  tagIds?: string[];
}

const TAGS: Tag[] = [
  {
    id: "tag-1",
    tenantId: "tenant-1",
    name: "production",
    color: "rose",
    description: "Live customer-facing environment.",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
  },
  {
    id: "tag-2",
    tenantId: "tenant-1",
    name: "aws",
    color: "amber",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
  },
];

const BY_ID = new Map(TAGS.map((tag) => [tag.id, tag]));

function renderTable(rows: Row[], onTagIdsChange = vi.fn(), tagIds: string[] = []) {
  render(
    <DataTable<Row>
      columns={[
        { header: "Id", cell: (row) => row.id },
        tagsColumn<Row>((row) => row.tagIds, BY_ID),
      ]}
      rows={rows}
      getRowKey={(row) => row.id}
      tagIds={tagIds}
      onTagIdsChange={onTagIdsChange}
    />
  );
  return onTagIdsChange;
}

describe("tagsColumn", () => {
  afterEach(() => {
    // Only the fold test stubs these; drop them so the inherited (always-zero)
    // getters come back for the rest of the file.
    Reflect.deleteProperty(HTMLSpanElement.prototype, "offsetWidth");
    Reflect.deleteProperty(HTMLDivElement.prototype, "clientWidth");
  });

  it("renders one chip per attached tag, named by the tag", () => {
    renderTable([{ id: "r1", tagIds: ["tag-1", "tag-2"] }]);
    expect(screen.getByText("production")).toBeInTheDocument();
    expect(screen.getByText("aws")).toBeInTheDocument();
  });

  it("renders a dash for a record carrying no tags", () => {
    renderTable([{ id: "r1", tagIds: [] }]);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("falls back to the raw id when the tag is not in the lookup", () => {
    renderTable([{ id: "r1", tagIds: ["tag-gone"] }]);
    expect(screen.getByText("tag-gone")).toBeInTheDocument();
  });

  it("shows the tag's description in the chip's tooltip", async () => {
    const user = userEvent.setup();
    renderTable([{ id: "r1", tagIds: ["tag-1"] }]);

    await user.hover(screen.getByText("production"));
    expect(await screen.findByRole("tooltip", {}, { timeout: 2000 })).toHaveTextContent(
      "Live customer-facing environment."
    );
  });

  it("offers a conjunctive multi-select in its header menu", async () => {
    const user = userEvent.setup();
    renderTable([{ id: "r1", tagIds: ["tag-1"] }]);

    await user.click(screen.getByRole("button", { name: /Tags/ }));
    // The AND semantics are stated, since a narrowing filter otherwise reads
    // as a broken one.
    expect(await screen.findByText("Filter (all of)")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "production" })).toBeInTheDocument();
  });

  it("reports the picked tags through onTagIdsChange", async () => {
    const user = userEvent.setup();
    const onTagIdsChange = renderTable([{ id: "r1", tagIds: ["tag-1"] }]);

    await user.click(screen.getByRole("button", { name: /Tags/ }));
    await user.click(await screen.findByRole("checkbox", { name: "aws" }));

    expect(onTagIdsChange).toHaveBeenCalledWith(["tag-2"]);
  });

  it("folds the tags that do not fit into a counted chip", () => {
    // jsdom lays nothing out, so the column normally takes ChipRow's
    // show-everything path. Stub the two widths it measures to prove a heavily
    // tagged row collapses to one line instead of widening the column.
    Object.defineProperty(HTMLSpanElement.prototype, "offsetWidth", {
      configurable: true,
      get: () => 100,
    });
    Object.defineProperty(HTMLDivElement.prototype, "clientWidth", {
      configurable: true,
      get: () => 200,
    });
    renderTable([{ id: "r1", tagIds: ["tag-1", "tag-2"] }]);

    expect(screen.getByText("production")).toBeInTheDocument();
    expect(screen.getByText("+1")).toBeInTheDocument();
    // The folded tag leaves no chip behind — only the name a screen reader
    // still needs, which is what the count alone would have taken away.
    expect(screen.getByText("aws")).toHaveClass("sr-only");
  });

  it("opens a dialog listing every tag, each with its description, from the +N chip", async () => {
    const user = userEvent.setup();
    Object.defineProperty(HTMLSpanElement.prototype, "offsetWidth", {
      configurable: true,
      get: () => 100,
    });
    Object.defineProperty(HTMLDivElement.prototype, "clientWidth", {
      configurable: true,
      get: () => 200,
    });
    renderTable([{ id: "r1", tagIds: ["tag-1", "tag-2"] }]);

    await user.click(screen.getByRole("button", { name: "Show all 2 tags" }));
    const dialog = await screen.findByRole("dialog", { name: "Tags" });
    expect(within(dialog).getByText("production")).toBeInTheDocument();
    expect(within(dialog).getByText("aws")).toBeInTheDocument();

    await user.hover(within(dialog).getByText("production"));
    expect(await screen.findByRole("tooltip", {}, { timeout: 2000 })).toHaveTextContent(
      "Live customer-facing environment."
    );
  });

  it("is not sortable — a set has no order", async () => {
    const user = userEvent.setup();
    renderTable([{ id: "r1", tagIds: ["tag-1"] }]);

    await user.click(screen.getByRole("button", { name: /Tags/ }));
    await screen.findByText("Filter (all of)");
    expect(screen.queryByRole("button", { name: "Sort ascending" })).not.toBeInTheDocument();
  });
});

describe("tagFilterOptions", () => {
  it("turns the lookup into one swatched option per tag", () => {
    expect(tagFilterOptions(BY_ID)).toEqual([
      { value: "tag-1", label: "production", swatch: "rose" },
      { value: "tag-2", label: "aws", swatch: "amber" },
    ]);
  });
});
