import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DataTable } from "@/components/ui/data-table";
import { render, screen } from "@/test/test-utils";
import { auditColumns } from "./audit-columns";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

interface Row {
  id: string;
  updatedAt: string;
  createdBy: string;
  updatedBy: string;
}

const ROW: Row = {
  id: "row-1",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "user-1",
  updatedBy: "user-2",
};

function renderTable(rows: Row[], userNameById?: Map<string, string>) {
  render(
    <DataTable<Row>
      columns={auditColumns<Row>(userNameById)}
      rows={rows}
      getRowKey={(row) => row.id}
    />
  );
}

describe("auditColumns", () => {
  it("links created-by/updated-by to the user's detail page, labeled with the raw id when no name map is given", () => {
    renderTable([ROW]);
    expect(screen.getByText("row-1")).toBeInTheDocument();
    const createdByLink = screen.getByRole("link", { name: "user-1" });
    expect(createdByLink).toHaveAttribute("href", "/admin/users/user-1");
    const updatedByLink = screen.getByRole("link", { name: "user-2" });
    expect(updatedByLink).toHaveAttribute("href", "/admin/users/user-2");
  });

  it("resolves created-by/updated-by to display names when a name map is given", () => {
    const names = new Map([
      ["user-1", "Alice"],
      ["user-2", "Bob"],
    ]);
    renderTable([ROW], names);
    const createdByLink = screen.getByRole("link", { name: "Alice" });
    expect(createdByLink).toHaveAttribute("href", "/admin/users/user-1");
    const updatedByLink = screen.getByRole("link", { name: "Bob" });
    expect(updatedByLink).toHaveAttribute("href", "/admin/users/user-2");
  });

  it("falls back to the raw id label for an id missing from the name map, still linked", () => {
    renderTable([ROW], new Map([["user-1", "Alice"]]));
    expect(screen.getByRole("link", { name: "Alice" })).toHaveAttribute(
      "href",
      "/admin/users/user-1"
    );
    expect(screen.getByRole("link", { name: "user-2" })).toHaveAttribute(
      "href",
      "/admin/users/user-2"
    );
  });

  it("exposes exactly the four expected headers", () => {
    renderTable([ROW]);
    expect(screen.getByRole("columnheader", { name: "ID" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Updated At" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Created By" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Updated By" })).toBeInTheDocument();
  });

  it("makes Updated At sortable but leaves ID/Created By/Updated By display-only", async () => {
    const user = userEvent.setup();
    render(
      <DataTable<Row>
        columns={auditColumns<Row>()}
        rows={[ROW]}
        getRowKey={(row) => row.id}
        sort={null}
        onSortChange={vi.fn()}
      />
    );

    await user.click(screen.getByRole("button", { name: /Updated At/ }));
    expect(await screen.findByRole("button", { name: "Sort ascending" })).toBeInTheDocument();

    expect(screen.queryByRole("button", { name: /^ID$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Created By$/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Updated By$/ })).not.toBeInTheDocument();
  });
});
