import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatInput } from "./ChatInput";

/** Make `(pointer: coarse)` match, emulating a touch device; other queries stay false. */
function stubCoarsePointer() {
  return vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({
        matches: query === "(pointer: coarse)",
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }) as unknown as MediaQueryList
  );
}

describe("ChatInput", () => {
  it("renders textarea with placeholder", () => {
    render(<ChatInput onSend={vi.fn()} disabled={false} />);
    expect(screen.getByRole("textbox")).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Message/)).toBeInTheDocument();
  });

  it("Send button is disabled when textarea is empty", () => {
    render(<ChatInput onSend={vi.fn()} disabled={false} />);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("Send button is disabled when disabled prop is true", async () => {
    render(<ChatInput onSend={vi.fn()} disabled={true} />);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("typing in textarea enables Send button", async () => {
    render(<ChatInput onSend={vi.fn()} disabled={false} />);
    await userEvent.type(screen.getByRole("textbox"), "hello");
    expect(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  });

  it("clicking Send calls onSend with trimmed text and clears textarea", async () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} disabled={false} />);
    await userEvent.type(screen.getByRole("textbox"), "  hello  ");
    await userEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(onSend).toHaveBeenCalledWith("hello");
    expect(screen.getByRole("textbox")).toHaveValue("");
  });

  it("pressing Enter calls onSend", async () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} disabled={false} />);
    await userEvent.type(screen.getByRole("textbox"), "hello{Enter}");
    expect(onSend).toHaveBeenCalledWith("hello");
  });

  it("pressing Shift+Enter does NOT call onSend", async () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} disabled={false} />);
    await userEvent.type(screen.getByRole("textbox"), "hello{Shift>}{Enter}{/Shift}");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("pressing Enter with only whitespace does NOT call onSend", async () => {
    const onSend = vi.fn();
    render(<ChatInput onSend={onSend} disabled={false} />);
    await userEvent.type(screen.getByRole("textbox"), "   {Enter}");
    expect(onSend).not.toHaveBeenCalled();
  });

  it("on a touch device, Enter inserts a newline instead of sending", async () => {
    const spy = stubCoarsePointer();
    try {
      const onSend = vi.fn();
      render(<ChatInput onSend={onSend} disabled={false} />);
      await userEvent.type(screen.getByRole("textbox"), "hello{Enter}world");
      expect(onSend).not.toHaveBeenCalled();
      expect(screen.getByRole("textbox")).toHaveValue("hello\nworld");
    } finally {
      spy.mockRestore();
    }
  });

  it("on a touch device, the placeholder omits the Enter-to-send hint", () => {
    const spy = stubCoarsePointer();
    try {
      render(<ChatInput onSend={vi.fn()} disabled={false} />);
      expect(screen.getByPlaceholderText("Message…")).toBeInTheDocument();
    } finally {
      spy.mockRestore();
    }
  });
});
