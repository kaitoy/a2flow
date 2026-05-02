import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Input } from "./input";

describe("Input", () => {
  it("renders an input element", () => {
    render(<Input />);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("forwards value and onChange", async () => {
    const onChange = vi.fn();
    render(<Input value="" onChange={onChange} />);
    await userEvent.type(screen.getByRole("textbox"), "a");
    expect(onChange).toHaveBeenCalled();
  });

  it("disabled input is disabled", () => {
    render(<Input disabled />);
    expect(screen.getByRole("textbox")).toBeDisabled();
  });

  it("className prop is applied alongside base classes", () => {
    render(<Input className="my-class" />);
    const cls = screen.getByRole("textbox").className;
    expect(cls).toContain("border-outline");
    expect(cls).toContain("my-class");
  });

  it("forwards type prop", () => {
    const { container } = render(<Input type="password" />);
    expect(container.querySelector("input")).toHaveAttribute("type", "password");
  });

  it("forwards id prop", () => {
    render(<Input id="my-id" />);
    expect(document.getElementById("my-id")).toBeInTheDocument();
  });
});
