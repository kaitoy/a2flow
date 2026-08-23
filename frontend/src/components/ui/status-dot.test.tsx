import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusDot } from "./status-dot";

/** The dot itself carries no text, so tests reach for it by its shape classes. */
function dot(container: HTMLElement) {
  return container.querySelector(".size-2.rounded-full");
}

describe("StatusDot", () => {
  it("paints the dot with the caller's status colour", () => {
    const { container } = render(<StatusDot dotClass="bg-success/80" label="ready" />);
    expect(dot(container)?.className).toContain("bg-success/80");
  });

  it("hides the dot from assistive tech, since the label already names the status", () => {
    const { container } = render(<StatusDot dotClass="bg-error" label="failed" />);
    expect(dot(container)).toHaveAttribute("aria-hidden");
  });

  it("renders the label capitalized and without a colour of its own", () => {
    render(<StatusDot dotClass="bg-error" label="failed" />);
    const label = screen.getByText("failed");
    expect(label.className).toBe("capitalize");
  });

  it("lets a call site restyle the label", () => {
    render(
      <StatusDot
        dotClass="bg-accent"
        label="in progress"
        labelClassName="text-on-surface-variant text-xs"
      />
    );
    expect(screen.getByText("in progress").className).toBe("text-on-surface-variant text-xs");
  });

  it("appends call-site spacing to the row", () => {
    const { container } = render(
      <StatusDot dotClass="bg-accent" label="pending" className="mt-1.5 pl-7" />
    );
    const row = container.firstElementChild;
    expect(row?.className).toContain("flex items-center gap-2");
    expect(row?.className).toContain("mt-1.5 pl-7");
  });
});
