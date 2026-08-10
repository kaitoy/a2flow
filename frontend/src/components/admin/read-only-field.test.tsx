import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReadOnlyField } from "./read-only-field";

describe("ReadOnlyField", () => {
  it("renders its value on a recessed surface rather than as an input", () => {
    render(<ReadOnlyField>my-agent-skill</ReadOnlyField>);

    const field = screen.getByText("my-agent-skill");
    expect(field).toHaveClass("bg-surface-dim/40", "border-outline-variant");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("merges extra classes onto the surface", () => {
    render(<ReadOnlyField className="whitespace-pre-wrap">line one{"\n"}line two</ReadOnlyField>);

    expect(screen.getByText(/line one/)).toHaveClass("whitespace-pre-wrap", "bg-surface-dim/40");
  });

  it("renders a node value", () => {
    render(
      <ReadOnlyField>
        <span data-testid="badge">Super Admin</span>
      </ReadOnlyField>
    );

    expect(screen.getByTestId("badge")).toBeInTheDocument();
  });
});
