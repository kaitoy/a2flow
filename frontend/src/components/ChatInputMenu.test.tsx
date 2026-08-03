import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatInputMenu } from "./ChatInputMenu";

describe("ChatInputMenu", () => {
  it("renders a closed trigger", () => {
    render(<ChatInputMenu onGenerateDescription={vi.fn()} />);
    const trigger = screen.getByRole("button", { name: "Chat actions" });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("opens the menu on trigger click and moves focus to the item", async () => {
    const user = userEvent.setup();
    render(<ChatInputMenu onGenerateDescription={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Chat actions" }));

    expect(screen.getByRole("button", { name: "Chat actions" })).toHaveAttribute(
      "aria-expanded",
      "true"
    );
    await waitFor(() =>
      expect(screen.getByRole("menuitem", { name: /Generate description/ })).toHaveFocus()
    );
  });

  it("calls onGenerateDescription and closes when the item is clicked", async () => {
    const onGenerateDescription = vi.fn();
    const user = userEvent.setup();
    render(<ChatInputMenu onGenerateDescription={onGenerateDescription} />);

    await user.click(screen.getByRole("button", { name: "Chat actions" }));
    await user.click(screen.getByRole("menuitem", { name: /Generate description/ }));

    expect(onGenerateDescription).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Chat actions" })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
  });

  it("disables the item and ignores clicks when disabled", async () => {
    const onGenerateDescription = vi.fn();
    const user = userEvent.setup();
    render(<ChatInputMenu onGenerateDescription={onGenerateDescription} disabled />);

    await user.click(screen.getByRole("button", { name: "Chat actions" }));
    const item = screen.getByRole("menuitem", { name: /Generate description/ });

    expect(item).toBeDisabled();
    await user.click(item);
    expect(onGenerateDescription).not.toHaveBeenCalled();
  });

  it("spins the icon while pending", async () => {
    const user = userEvent.setup();
    render(<ChatInputMenu onGenerateDescription={vi.fn()} pending />);

    await user.click(screen.getByRole("button", { name: "Chat actions" }));
    await waitFor(() =>
      expect(screen.getByRole("menuitem", { name: /Generate description/ })).toHaveFocus()
    );

    // The menu panel is portaled to `document.body`, outside RTL's `container`.
    const icon = document.body.querySelector(".lucide-sparkles");
    expect(icon).toHaveClass("motion-safe:animate-spin-y");
  });

  it("closes and returns focus to the trigger on Escape", async () => {
    const user = userEvent.setup();
    render(<ChatInputMenu onGenerateDescription={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Chat actions" }));
    await waitFor(() =>
      expect(screen.getByRole("menuitem", { name: /Generate description/ })).toHaveFocus()
    );

    await user.keyboard("{Escape}");

    expect(screen.getByRole("button", { name: "Chat actions" })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
    await waitFor(() => expect(screen.getByRole("button", { name: "Chat actions" })).toHaveFocus());
  });

  it("closes on an outside pointerdown", async () => {
    const user = userEvent.setup();
    render(<ChatInputMenu onGenerateDescription={vi.fn()} />);

    await user.click(screen.getByRole("button", { name: "Chat actions" }));
    await waitFor(() =>
      expect(screen.getByRole("menuitem", { name: /Generate description/ })).toHaveFocus()
    );

    fireEvent.pointerDown(document.body);

    expect(screen.getByRole("button", { name: "Chat actions" })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
  });
});
