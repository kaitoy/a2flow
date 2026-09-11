import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Tooltip } from "./tooltip";

describe("Tooltip", () => {
  it("shows the label on hover", async () => {
    const user = userEvent.setup();
    render(
      <Tooltip label="Full text" delay={0}>
        <button type="button">trigger</button>
      </Tooltip>
    );
    await user.hover(screen.getByRole("button", { name: "trigger" }));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Full text");
  });

  it("shows the label when the trigger takes keyboard focus", async () => {
    const user = userEvent.setup();
    render(
      <Tooltip label="Full text" delay={0}>
        <button type="button">trigger</button>
      </Tooltip>
    );

    await user.tab();

    expect(screen.getByRole("button", { name: "trigger" })).toHaveFocus();
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Full text");
  });

  it("stays hidden when focus is restored to a trigger the user clicked", async () => {
    const user = userEvent.setup();
    render(
      <Tooltip label="Full text" delay={0}>
        <button type="button">trigger</button>
      </Tooltip>
    );
    const trigger = screen.getByRole("button", { name: "trigger" });

    // The shape of the bug: click a trigger that opens a modal, the modal's
    // backdrop takes the pointer off the button, and closing the modal hands
    // focus back — with no pointer left to fire `mouseleave`, a tooltip shown
    // on that focus would hang around forever. A real browser reports that
    // pointer-then-programmatic focus as not `:focus-visible`; happy-dom does
    // not implement the heuristic, so stand in for it.
    await user.click(trigger);
    await user.unhover(trigger);
    await waitFor(() => expect(screen.queryByRole("tooltip")).not.toBeInTheDocument(), {
      timeout: 3000,
    });

    vi.spyOn(trigger, "matches").mockImplementation((sel) => sel !== ":focus-visible");
    trigger.blur();
    trigger.focus();

    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("hides the label again when focus leaves the trigger", async () => {
    const user = userEvent.setup();
    render(
      <>
        <Tooltip label="Full text" delay={0}>
          <button type="button">trigger</button>
        </Tooltip>
        <button type="button">next</button>
      </>
    );

    await user.tab();
    await screen.findByRole("tooltip");
    await user.tab();

    // The chip unmounts only once its leave spring settles, which outlasts
    // waitFor's 1s default.
    await waitFor(() => expect(screen.queryByRole("tooltip")).not.toBeInTheDocument(), {
      timeout: 3000,
    });
  });

  it("attaches no tooltip behavior when disabled", async () => {
    const user = userEvent.setup();
    render(
      <Tooltip label="Full text" delay={0} disabled>
        <button type="button">trigger</button>
      </Tooltip>
    );
    await user.hover(screen.getByRole("button", { name: "trigger" }));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});
