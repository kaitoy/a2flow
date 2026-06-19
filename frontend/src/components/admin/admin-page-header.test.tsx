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
});
