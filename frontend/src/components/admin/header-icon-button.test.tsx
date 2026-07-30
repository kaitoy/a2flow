import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { HeaderIconButton } from "./header-icon-button";

describe("HeaderIconButton", () => {
  it("uses the label as its accessible name", () => {
    render(
      <HeaderIconButton label="Columns">
        <svg aria-hidden="true" />
      </HeaderIconButton>
    );
    expect(screen.getByRole("button", { name: "Columns" })).toBeInTheDocument();
  });

  it("calls onClick", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<HeaderIconButton label="Refresh" onClick={onClick} />);
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("passes button attributes through", () => {
    render(<HeaderIconButton label="Columns" aria-haspopup="dialog" aria-expanded disabled />);
    const button = screen.getByRole("button", { name: "Columns" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-haspopup", "dialog");
    expect(button).toHaveAttribute("aria-expanded", "true");
  });

  it("forwards its ref to the button, alongside the tooltip's own", () => {
    const ref = createRef<HTMLButtonElement>();
    render(<HeaderIconButton ref={ref} label="Columns" />);
    expect(ref.current).toBe(screen.getByRole("button", { name: "Columns" }));
  });

  it("keeps the shared glass chrome", () => {
    render(<HeaderIconButton label="Refresh" />);
    expect(screen.getByRole("button", { name: "Refresh" }).className).toContain("glass-panel");
  });
});
