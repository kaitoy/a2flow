import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { ToolBinding } from "@/lib/api";
import { TaskToolsDialog } from "./TaskToolsDialog";

const TOOL_BINDINGS: ToolBinding[] = [
  { mcpServerId: "mcp-1", toolName: "extract_text" },
  { mcpServerId: "mcp-2", toolName: "ocr_scan" },
];

const SERVER_NAMES = new Map([
  ["mcp-1", "my-mcp-server"],
  ["mcp-2", "local-files"],
]);

/** Wraps {@link TaskToolsDialog} with a real trigger button, matching how it's
 * opened in practice, so focus restoration on close is testable. */
function TriggerHarness({
  serverNames = SERVER_NAMES,
  serverNamesLoading = false,
}: {
  serverNames?: Map<string, string>;
  serverNamesLoading?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        open dialog
      </button>
      <TaskToolsDialog
        task={open ? { title: "Gather sources", toolBindings: TOOL_BINDINGS } : null}
        serverNames={serverNames}
        serverNamesLoading={serverNamesLoading}
        onClose={() => setOpen(false)}
      />
    </>
  );
}

describe("TaskToolsDialog", () => {
  it("lists each bound tool with its resolved server name", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness />);

    await user.click(screen.getByText("open dialog"));
    const dialog = await screen.findByRole("dialog");

    expect(within(dialog).getByText("Gather sources")).toBeInTheDocument();
    expect(within(dialog).getByText("extract_text")).toBeInTheDocument();
    expect(within(dialog).getByText("my-mcp-server")).toBeInTheDocument();
    expect(within(dialog).getByText("ocr_scan")).toBeInTheDocument();
    expect(within(dialog).getByText("local-files")).toBeInTheDocument();
  });

  it("shows a loading placeholder instead of server names while they load", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness serverNames={new Map()} serverNamesLoading={true} />);

    await user.click(screen.getByText("open dialog"));
    const dialog = await screen.findByRole("dialog");

    expect(within(dialog).getAllByText("Loading server…")).toHaveLength(2);
  });

  it("falls back to 'Unknown server' for a binding with no resolved name", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness serverNames={new Map()} />);

    await user.click(screen.getByText("open dialog"));
    const dialog = await screen.findByRole("dialog");

    expect(within(dialog).getAllByText("Unknown server")).toHaveLength(2);
  });

  it("moves focus into the dialog when it opens", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness />);

    await user.click(screen.getByText("open dialog"));
    const dialog = await screen.findByRole("dialog");
    await waitFor(() =>
      expect(within(dialog).getByRole("button", { name: "Close" })).toHaveFocus()
    );
  });

  it("closes and returns focus to the trigger on Escape", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness />);

    await user.click(screen.getByText("open dialog"));
    await screen.findByRole("dialog");

    await user.keyboard("{Escape}");

    await waitFor(() => expect(screen.getByText("open dialog")).toHaveFocus());
  });

  it("closes via the Close button", async () => {
    const user = userEvent.setup();
    render(<TriggerHarness />);

    await user.click(screen.getByText("open dialog"));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Close" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("renders nothing when task is null", () => {
    render(
      <TaskToolsDialog
        task={null}
        serverNames={new Map()}
        serverNamesLoading={false}
        onClose={vi.fn()}
      />
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
