import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PasswordInput } from "./password-input";

describe("PasswordInput", () => {
  it("masks the value by default", () => {
    render(<PasswordInput aria-label="Password" value="secret" onChange={() => {}} />);
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  });

  it("reveals the value as plain text when the toggle is clicked", async () => {
    const user = userEvent.setup();
    render(<PasswordInput aria-label="Password" value="secret" onChange={() => {}} />);
    await user.click(screen.getByRole("button", { name: /show value/i }));
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "text");
  });

  it("masks the value again on a second click", async () => {
    const user = userEvent.setup();
    render(<PasswordInput aria-label="Password" value="secret" onChange={() => {}} />);
    const toggle = screen.getByRole("button", { name: /show value/i });
    await user.click(toggle);
    await user.click(screen.getByRole("button", { name: /hide value/i }));
    expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  });

  it("forwards id and other input props", () => {
    const onChange = vi.fn();
    render(<PasswordInput id="my-id" value="" onChange={onChange} />);
    expect(document.getElementById("my-id")).toBeInTheDocument();
  });
});
