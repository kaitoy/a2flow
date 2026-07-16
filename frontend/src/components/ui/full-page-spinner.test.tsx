import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FullPageSpinner } from "./full-page-spinner";

describe("FullPageSpinner", () => {
  it("renders a spinner", () => {
    render(<FullPageSpinner />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("defaults to filling the viewport height", () => {
    const { container } = render(<FullPageSpinner />);
    expect(container.firstChild).toHaveClass("h-dvh");
  });

  it("accepts a custom sizing class", () => {
    const { container } = render(<FullPageSpinner className="h-full" />);
    expect(container.firstChild).toHaveClass("h-full");
    expect(container.firstChild).not.toHaveClass("h-dvh");
  });
});
