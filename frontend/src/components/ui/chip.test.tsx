import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Chip } from "./chip";

/**
 * Force `scrollWidth`/`clientWidth` for the duration of a test so the overflow
 * measurement can be exercised — happy-dom has no layout engine and reports 0
 * for both, which reads as "not clipped".
 */
function stubOverflow(scrollWidth: number, clientWidth: number) {
  const original = {
    scrollWidth: Object.getOwnPropertyDescriptor(HTMLElement.prototype, "scrollWidth"),
    clientWidth: Object.getOwnPropertyDescriptor(HTMLElement.prototype, "clientWidth"),
  };
  Object.defineProperty(HTMLElement.prototype, "scrollWidth", {
    configurable: true,
    value: scrollWidth,
  });
  Object.defineProperty(HTMLElement.prototype, "clientWidth", {
    configurable: true,
    value: clientWidth,
  });
  return () => {
    if (original.scrollWidth) {
      Object.defineProperty(HTMLElement.prototype, "scrollWidth", original.scrollWidth);
    }
    if (original.clientWidth) {
      Object.defineProperty(HTMLElement.prototype, "clientWidth", original.clientWidth);
    }
  };
}

describe("Chip", () => {
  it("renders its label", () => {
    render(<Chip label="Gather sources" />);
    expect(screen.getByText("Gather sources")).toBeInTheDocument();
  });

  it("clips to a single capped-width line with a modest radius", () => {
    render(<Chip label="Validate the uploaded CSV schema against the contract" />);
    // The label lives in an inner span that truncates; the width cap and
    // radius live on its parent, the outer pill (see the remove-button test
    // below for why they are split).
    const labelSpan = screen.getByText("Validate the uploaded CSV schema against the contract");
    expect(labelSpan.className).toContain("truncate");
    const pill = labelSpan.parentElement;
    expect(pill?.className).toContain("max-w-64");
    expect(pill?.className).toContain("rounded-md");
    // A pill radius breaks open once the text wraps, so it must not be used here.
    expect(pill?.className).not.toContain("rounded-full");
  });

  it("reports hover to the caller", async () => {
    const user = userEvent.setup();
    const onMouseEnter = vi.fn();
    const onMouseLeave = vi.fn();
    render(<Chip label="Gather sources" onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave} />);

    await user.hover(screen.getByText("Gather sources"));
    expect(onMouseEnter).toHaveBeenCalledTimes(1);

    await user.unhover(screen.getByText("Gather sources"));
    expect(onMouseLeave).toHaveBeenCalledTimes(1);
  });

  it("reveals the full label in a tooltip once the text is clipped", async () => {
    const restore = stubOverflow(400, 224);
    try {
      const user = userEvent.setup();
      render(<Chip label="Validate the uploaded CSV schema against the contract" />);

      await user.hover(screen.getByText("Validate the uploaded CSV schema against the contract"));
      expect(await screen.findByRole("tooltip", {}, { timeout: 2000 })).toHaveTextContent(
        "Validate the uploaded CSV schema against the contract"
      );
    } finally {
      restore();
    }
  });

  it("stays hover-inert when the label fits", async () => {
    const user = userEvent.setup();
    const onMouseEnter = vi.fn();
    render(<Chip label="Gather sources" onMouseEnter={onMouseEnter} />);

    await user.hover(screen.getByText("Gather sources"));
    // The caller's handler still fires; only the tooltip is suppressed.
    expect(onMouseEnter).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("renders no remove button without onRemove", () => {
    render(<Chip label="Developers" />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("calls onRemove when its remove button is pressed", async () => {
    const onRemove = vi.fn();
    const user = userEvent.setup();
    render(<Chip label="Developers" onRemove={onRemove} />);

    await user.click(screen.getByRole("button", { name: "Remove Developers" }));

    expect(onRemove).toHaveBeenCalledTimes(1);
  });

  it("keeps the remove button reachable even when the label is long enough to clip", async () => {
    // A label past ~36 characters is ordinary data here — e.g. UserPicker's
    // "First Last (username)" chips in font-mono text-xs. If the truncating
    // box ever again wrapped the button as well as the label, the button
    // would clip out of the layout along with the overflowing text and this
    // click would silently miss.
    const onRemove = vi.fn();
    const user = userEvent.setup();
    const label = "Alexandra Montgomery-Whitfield (a.montgomery-whitfield)";
    render(<Chip label={label} onRemove={onRemove} />);

    const button = screen.getByRole("button", { name: `Remove ${label}` });
    // The button must be a sibling of the truncating label span, not a
    // descendant of it — the fix that keeps it out of the clipping region.
    const labelSpan = screen.getByText(label);
    expect(labelSpan.className).toContain("truncate");
    expect(button.parentElement).toBe(labelSpan.parentElement);
    expect(button.className).toContain("shrink-0");

    await user.click(button);

    expect(onRemove).toHaveBeenCalledTimes(1);
  });
});
