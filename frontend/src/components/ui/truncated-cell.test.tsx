import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TruncatedCell } from "./truncated-cell";

describe("TruncatedCell", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders its content in a single-line clipping span", () => {
    render(<TruncatedCell>Hello</TruncatedCell>);
    expect(screen.getByText("Hello").className).toContain("truncate");
  });

  it("does not show a tooltip when the content fits", () => {
    render(<TruncatedCell>Short</TruncatedCell>);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("reveals the full text in a tooltip when the content overflows", async () => {
    const user = userEvent.setup();
    // jsdom reports 0 for layout sizes; force an overflow by stubbing them.
    vi.spyOn(HTMLElement.prototype, "scrollWidth", "get").mockReturnValue(200);
    vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(100);

    render(<TruncatedCell>Very long cell text</TruncatedCell>);
    await user.hover(screen.getByText("Very long cell text"));

    expect(await screen.findByRole("tooltip")).toHaveTextContent("Very long cell text");
  });
});
