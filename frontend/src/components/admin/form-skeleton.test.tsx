import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FormSkeleton } from "./form-skeleton";

describe("FormSkeleton", () => {
  it("exposes role=status for assistive technologies", () => {
    render(<FormSkeleton fields={3} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders an input placeholder per requested field", () => {
    const { container } = render(<FormSkeleton fields={4} />);
    // Each field row contains a label skeleton and an input skeleton; the
    // button row adds two more. 4 fields → 4*2 + 2 = 10 skeleton blocks.
    expect(container.querySelectorAll(".skeleton")).toHaveLength(4 * 2 + 2);
  });
});
