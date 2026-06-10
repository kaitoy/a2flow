import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Skeleton } from "./skeleton";

describe("Skeleton", () => {
  it("renders a shimmer block with the skeleton class", () => {
    const { container } = render(<Skeleton />);
    expect(container.firstChild).toHaveClass("skeleton");
  });

  it("is aria-hidden so it is not announced", () => {
    const { container } = render(<Skeleton />);
    expect(container.firstChild).toHaveAttribute("aria-hidden", "true");
  });

  it("merges a passed className", () => {
    const { container } = render(<Skeleton className="h-4 w-32" />);
    expect(container.firstChild).toHaveClass("skeleton", "h-4", "w-32");
  });
});
