import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AdminPageHeader } from "./admin-page-header";

describe("AdminPageHeader", () => {
  it("renders the title", () => {
    render(<AdminPageHeader title="Agent Skills" />);
    expect(screen.getByRole("heading", { name: "Agent Skills" })).toBeInTheDocument();
  });

  it("renders the Add link when addHref and addLabel are provided", () => {
    render(<AdminPageHeader title="Users" addHref="/admin/users/new" addLabel="+ Add user" />);
    const link = screen.getByRole("link", { name: "+ Add user" });
    expect(link).toHaveAttribute("href", "/admin/users/new");
  });

  it("does not render a refresh button without onRefresh", () => {
    render(<AdminPageHeader title="Approvals" />);
    expect(screen.queryByRole("button", { name: "Refresh" })).not.toBeInTheDocument();
  });

  it("calls onRefresh when the refresh button is clicked", async () => {
    const user = userEvent.setup();
    const onRefresh = vi.fn();
    render(<AdminPageHeader title="Approvals" onRefresh={onRefresh} />);

    await user.click(screen.getByRole("button", { name: "Refresh" }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it("disables the refresh button while refreshing", () => {
    render(<AdminPageHeader title="Approvals" onRefresh={vi.fn()} refreshing />);
    expect(screen.getByRole("button", { name: "Refresh" })).toBeDisabled();
  });

  it("renders the column picker between the refresh and secondary actions", () => {
    render(
      <AdminPageHeader
        title="MCP Servers"
        onRefresh={vi.fn()}
        columnPicker={<button type="button">Columns</button>}
        secondaryAction={<button type="button">Browse registry</button>}
        addHref="/admin/mcp-servers/new"
        addLabel="+ Add server"
      />
    );
    const labels = screen
      .getAllByRole("button")
      .map((el) => el.getAttribute("aria-label") ?? el.textContent);
    expect(labels).toEqual(["Refresh", "Columns", "Browse registry"]);
  });
});
