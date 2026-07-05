import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import NotFound from "./not-found";

describe("NotFound", () => {
  it("renders a heading and description", () => {
    render(<NotFound />);
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByText("The page you're looking for doesn't exist.")).toBeInTheDocument();
  });

  it("links to the dashboard", () => {
    render(<NotFound />);
    expect(screen.getByRole("link", { name: "Go to dashboard" })).toHaveAttribute("href", "/admin");
  });
});
