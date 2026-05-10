import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./button";

describe("Button", () => {
  it("renders children", () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole("button", { name: "Click me" })).toBeInTheDocument();
  });

  it("default type is button", () => {
    render(<Button>x</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });

  it("primary variant applies gradient background", () => {
    render(<Button variant="primary">x</Button>);
    expect(screen.getByRole("button").className).toContain("from-accent");
  });

  it("secondary variant applies glass-panel", () => {
    render(<Button variant="secondary">x</Button>);
    const cls = screen.getByRole("button").className;
    expect(cls).toContain("glass-panel");
  });

  it("ghost variant (default) has transparent background", () => {
    render(<Button>x</Button>);
    expect(screen.getByRole("button").className).toContain("bg-transparent");
  });

  it("disabled prop disables the button", () => {
    render(<Button disabled>x</Button>);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("onClick fires when clicked", async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>x</Button>);
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it("className prop is applied", () => {
    render(<Button className="w-full">x</Button>);
    expect(screen.getByRole("button").className).toContain("w-full");
  });

  it("className does not remove variant classes", () => {
    render(
      <Button variant="primary" className="w-full">
        x
      </Button>
    );
    const cls = screen.getByRole("button").className;
    expect(cls).toContain("from-accent");
    expect(cls).toContain("w-full");
  });
});
