import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AdminListSkeleton } from "./admin-list-skeleton";

describe("AdminListSkeleton", () => {
  it("renders a header cell per column", () => {
    render(<AdminListSkeleton columns={["Name", "Email"]} />);
    expect(screen.getByRole("columnheader", { name: "Name" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Email" })).toBeInTheDocument();
  });

  it("renders 5 placeholder rows by default", () => {
    const { container } = render(<AdminListSkeleton columns={["A", "B"]} />);
    expect(container.querySelectorAll("tbody tr")).toHaveLength(5);
  });

  it("renders the requested number of rows", () => {
    const { container } = render(<AdminListSkeleton columns={["A", "B"]} rows={3} />);
    expect(container.querySelectorAll("tbody tr")).toHaveLength(3);
  });

  it("exposes role=status for assistive technologies", () => {
    render(<AdminListSkeleton columns={["A"]} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });
});
