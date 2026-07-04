import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { describe, expect, it } from "vitest";
import { useDialogA11y } from "./useDialogA11y";

/** Minimal host wiring an anchor, an unrelated "outside" control, and a panel
 * with `itemCount` focusable buttons to {@link useDialogA11y}. The panel opens
 * by clicking the anchor, mirroring real usage so the anchor genuinely holds
 * focus at the moment the panel opens (needed to test focus restoration). */
function Harness({
  itemCount = 2,
  ready = true,
  closeOnOutsideClick = true,
}: {
  itemCount?: number;
  ready?: boolean;
  closeOnOutsideClick?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLButtonElement | null>(null);
  useDialogA11y({
    open,
    onClose: () => setOpen(false),
    anchorRef,
    panelId: "test-panel",
    ready,
    closeOnOutsideClick,
  });

  return (
    <>
      <button type="button" ref={anchorRef} onClick={() => setOpen(true)}>
        anchor
      </button>
      <button type="button">outside</button>
      {open && ready && (
        <div id="test-panel" role="dialog" aria-label="Test panel" tabIndex={-1}>
          {Array.from({ length: itemCount }, (_, i) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length static list, order never changes
            <button key={`item-${i}`} type="button">
              item {i + 1}
            </button>
          ))}
        </div>
      )}
    </>
  );
}

describe("useDialogA11y", () => {
  it("moves focus to the first focusable element inside the panel on open", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByText("anchor"));

    await waitFor(() => expect(document.activeElement).toBe(screen.getByText("item 1")));
  });

  it("does not move focus until the panel is marked ready", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Harness ready={false} />);
    await user.click(screen.getByText("anchor"));
    expect(screen.queryByText("item 1")).not.toBeInTheDocument();

    rerender(<Harness ready />);

    await waitFor(() => expect(document.activeElement).toBe(screen.getByText("item 1")));
  });

  it("keeps focus on the panel itself when it has no focusable descendants", async () => {
    const user = userEvent.setup();
    render(<Harness itemCount={0} />);
    await user.click(screen.getByText("anchor"));

    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("dialog")));
  });

  it("closes and restores focus to the anchor on Escape", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByText("anchor"));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByText("item 1")));

    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.getByText("anchor")).toHaveFocus());
  });

  it("closes on an outside pointerdown and restores focus to the anchor", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByText("anchor"));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByText("item 1")));

    // A raw pointerdown (not userEvent) exercises only our own listener,
    // without also simulating the browser's default mousedown focus/blur
    // step, isolating the restoration logic from that separate race.
    fireEvent.pointerDown(document.body);

    await waitFor(() => expect(screen.getByText("anchor")).toHaveFocus());
  });

  it("does not fight focus when the outside click lands on another focusable control", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByText("anchor"));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByText("item 1")));

    await user.click(screen.getByText("outside"));

    await waitFor(() => expect(screen.getByText("outside")).toHaveFocus());
  });

  it("wraps Tab from the last focusable element back to the first", async () => {
    const user = userEvent.setup();
    render(<Harness itemCount={2} />);
    await user.click(screen.getByText("anchor"));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByText("item 1")));

    await user.tab();
    expect(document.activeElement).toBe(screen.getByText("item 2"));
    await user.tab();

    expect(document.activeElement).toBe(screen.getByText("item 1"));
  });

  it("wraps Shift+Tab from the first focusable element back to the last", async () => {
    const user = userEvent.setup();
    render(<Harness itemCount={2} />);
    await user.click(screen.getByText("anchor"));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByText("item 1")));

    await user.tab({ shift: true });

    expect(document.activeElement).toBe(screen.getByText("item 2"));
  });

  it("does not close on an outside pointerdown when closeOnOutsideClick is false", async () => {
    const user = userEvent.setup();
    render(<Harness closeOnOutsideClick={false} />);
    await user.click(screen.getByText("anchor"));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByText("item 1")));

    fireEvent.pointerDown(document.body);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
});
