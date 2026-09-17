import { Tags } from "lucide-react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@/test/test-utils";
import { AdminLoading } from "./admin-loading";

describe("AdminLoading", () => {
  it("renders the trail after Admin, the header, and a table skeleton with the given columns", () => {
    render(
      <AdminLoading
        crumbs={[{ label: "Tags" }]}
        icon={Tags}
        title="Tags"
        addHref="/tags/new"
        addLabel="+ Add tag"
        columns={["Name", "Created At"]}
      />
    );
    expect(screen.getByRole("link", { name: "Admin" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("heading", { name: "Tags" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "+ Add tag" })).toHaveAttribute("href", "/tags/new");
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Created At")).toBeInTheDocument();
  });

  it("renders a form skeleton when given a field count", () => {
    const { container } = render(
      <AdminLoading
        crumbs={[{ label: "Tags", href: "/tags" }, { label: "…" }]}
        icon={Tags}
        fields={3}
      />
    );
    expect(screen.getByRole("link", { name: "Tags" })).toHaveAttribute("href", "/tags");
    expect(container.querySelector("table")).toBeNull();
  });
});
