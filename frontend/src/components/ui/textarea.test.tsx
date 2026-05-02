import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { Textarea } from "./textarea";

describe("Textarea", () => {
  it("renders a textarea", () => {
    render(<Textarea />);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
  });

  it("forwards ref to the textarea element", () => {
    const ref = createRef<HTMLTextAreaElement>();
    render(<Textarea ref={ref} />);
    expect(ref.current).toBeInstanceOf(HTMLTextAreaElement);
  });

  it("disabled textarea is disabled", () => {
    render(<Textarea disabled />);
    expect(screen.getByRole("textbox")).toBeDisabled();
  });

  it("className prop is applied alongside base classes", () => {
    render(<Textarea className="my-class" />);
    const cls = screen.getByRole("textbox").className;
    expect(cls).toContain("border-outline");
    expect(cls).toContain("my-class");
  });

  it("forwards rows prop", () => {
    render(<Textarea rows={4} />);
    expect(screen.getByRole("textbox")).toHaveAttribute("rows", "4");
  });

  it("forwards value and onChange", async () => {
    const onChange = vi.fn();
    render(<Textarea value="" onChange={onChange} />);
    await userEvent.type(screen.getByRole("textbox"), "a");
    expect(onChange).toHaveBeenCalled();
  });
});
