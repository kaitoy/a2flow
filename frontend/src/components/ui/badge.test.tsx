import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Badge } from "./badge";

describe("Badge", () => {
  it("renders its children", () => {
    render(<Badge>Super Admin</Badge>);
    expect(screen.getByText("Super Admin")).toBeInTheDocument();
  });

  it("applies the accent pill styling", () => {
    render(<Badge>MCP</Badge>);
    expect(screen.getByText("MCP").className).toContain("bg-accent-soft");
  });
});
