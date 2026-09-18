import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DataTable } from "@/components/ui/data-table";
import type { UserGroup } from "@/lib/api";
import { render, screen, within } from "@/test/test-utils";
import { groupFilterOptions, groupsColumn } from "./group-columns";

interface Row {
  id: string;
  groupIds?: string[];
}

const GROUPS: UserGroup[] = [
  {
    id: "group-1",
    tenantId: "tenant-1",
    name: "Developers",
    description: "People who build workflows.",
    roles: ["developer"],
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
  },
  {
    id: "group-2",
    tenantId: "tenant-1",
    name: "Approvers",
    roles: [],
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
  },
  {
    id: "group-3",
    tenantId: "tenant-1",
    name: "Auditors",
    description: "Read-only access for compliance review.",
    roles: [],
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
  },
];

const BY_ID = new Map(GROUPS.map((group) => [group.id, group]));

function renderTable(rows: Row[], onGroupIdsChange = vi.fn(), groupIds: string[] = []) {
  render(
    <DataTable<Row>
      columns={[
        { header: "Id", cell: (row) => row.id },
        groupsColumn<Row>((row) => row.groupIds, BY_ID),
      ]}
      rows={rows}
      getRowKey={(row) => row.id}
      groupIds={groupIds}
      onGroupIdsChange={onGroupIdsChange}
    />
  );
  return onGroupIdsChange;
}

describe("groupsColumn", () => {
  afterEach(() => {
    // Only the fold test stubs these; drop them so the inherited (always-zero)
    // getters come back for the rest of the file.
    Reflect.deleteProperty(HTMLSpanElement.prototype, "offsetWidth");
    Reflect.deleteProperty(HTMLDivElement.prototype, "clientWidth");
  });

  it("renders one chip per attached group, named by the group", () => {
    renderTable([{ id: "r1", groupIds: ["group-1", "group-2"] }]);
    expect(screen.getByText("Developers")).toBeInTheDocument();
    expect(screen.getByText("Approvers")).toBeInTheDocument();
  });

  it("renders a dash for a record carrying no groups", () => {
    renderTable([{ id: "r1", groupIds: [] }]);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("falls back to the raw id when the group is not in the lookup", () => {
    renderTable([{ id: "r1", groupIds: ["group-gone"] }]);
    expect(screen.getByText("group-gone")).toBeInTheDocument();
  });

  it("shows the group's description in the chip's tooltip", async () => {
    const user = userEvent.setup();
    renderTable([{ id: "r1", groupIds: ["group-1"] }]);

    await user.hover(screen.getByText("Developers"));
    expect(await screen.findByRole("tooltip", {}, { timeout: 2000 })).toHaveTextContent(
      "People who build workflows."
    );
  });

  it("folds the groups that overflow two lines into a counted chip", () => {
    // jsdom lays nothing out, so the column normally takes ChipRow's
    // show-everything path. Stub the two widths it measures to prove a heavily
    // grouped row collapses to two lines instead of widening the column: at
    // 200px only one 100px chip fits per line, so two lines take two groups and
    // the third folds.
    Object.defineProperty(HTMLSpanElement.prototype, "offsetWidth", {
      configurable: true,
      get: () => 100,
    });
    Object.defineProperty(HTMLDivElement.prototype, "clientWidth", {
      configurable: true,
      get: () => 200,
    });
    renderTable([{ id: "r1", groupIds: ["group-1", "group-2", "group-3"] }]);

    expect(screen.getByText("Developers")).toBeInTheDocument();
    expect(screen.getByText("Approvers")).toBeInTheDocument();
    expect(screen.getByText("+1")).toBeInTheDocument();
    // The folded group leaves no chip behind — only the name a screen reader
    // still needs, which is what the count alone would have taken away.
    expect(screen.getByText("Auditors")).toHaveClass("sr-only");
  });

  it("opens a dialog listing every group, each with its description, from the +N chip", async () => {
    const user = userEvent.setup();
    Object.defineProperty(HTMLSpanElement.prototype, "offsetWidth", {
      configurable: true,
      get: () => 100,
    });
    Object.defineProperty(HTMLDivElement.prototype, "clientWidth", {
      configurable: true,
      get: () => 200,
    });
    renderTable([{ id: "r1", groupIds: ["group-1", "group-2", "group-3"] }]);

    await user.click(screen.getByRole("button", { name: "Show all 3 groups" }));
    const dialog = await screen.findByRole("dialog", { name: "Groups" });
    expect(within(dialog).getByText("Developers")).toBeInTheDocument();
    expect(within(dialog).getByText("Approvers")).toBeInTheDocument();
    expect(within(dialog).getByText("Auditors")).toBeInTheDocument();

    await user.hover(within(dialog).getByText("Auditors"));
    expect(await screen.findByRole("tooltip", {}, { timeout: 2000 })).toHaveTextContent(
      "Read-only access for compliance review."
    );
  });

  it("offers a conjunctive multi-select in its header menu", async () => {
    const user = userEvent.setup();
    renderTable([{ id: "r1", groupIds: ["group-1"] }]);

    await user.click(screen.getByRole("button", { name: /Groups/ }));
    // The AND semantics are stated, since a narrowing filter otherwise reads
    // as a broken one.
    expect(await screen.findByText("Filter (all of)")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Developers" })).toBeInTheDocument();
  });

  it("reports the picked groups through onGroupIdsChange", async () => {
    const user = userEvent.setup();
    const onGroupIdsChange = renderTable([{ id: "r1", groupIds: ["group-1"] }]);

    await user.click(screen.getByRole("button", { name: /Groups/ }));
    await user.click(await screen.findByRole("checkbox", { name: "Approvers" }));

    expect(onGroupIdsChange).toHaveBeenCalledWith(["group-2"]);
  });

  it("is not sortable — a set has no order", async () => {
    const user = userEvent.setup();
    renderTable([{ id: "r1", groupIds: ["group-1"] }]);

    await user.click(screen.getByRole("button", { name: /Groups/ }));
    await screen.findByText("Filter (all of)");
    expect(screen.queryByRole("button", { name: "Sort ascending" })).not.toBeInTheDocument();
  });
});

describe("groupFilterOptions", () => {
  it("turns the lookup into one option per group", () => {
    expect(groupFilterOptions(BY_ID)).toEqual([
      { value: "group-1", label: "Developers" },
      { value: "group-2", label: "Approvers" },
      { value: "group-3", label: "Auditors" },
    ]);
  });
});
