import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ToolActivityBubble } from "./ToolActivityBubble";

describe("ToolActivityBubble", () => {
  it("shows a spinner and 'running…' while the tool is running", () => {
    render(<ToolActivityBubble content={{ name: "create_workflow_task", status: "running" }} />);
    expect(screen.getByText("create_workflow_task")).toBeInTheDocument();
    expect(screen.getByText("running…")).toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("carries the live edge on the pill while running", () => {
    render(<ToolActivityBubble content={{ name: "create_workflow_task", status: "running" }} />);
    expect(screen.getByText("running…").parentElement?.className).toContain("live-edge");
  });

  it("shows 'done' and no MCP tag for a completed internal tool", () => {
    render(<ToolActivityBubble content={{ name: "list_workflow_tasks", status: "done" }} />);
    expect(screen.getByText("done")).toBeInTheDocument();
    expect(screen.queryByText("MCP")).not.toBeInTheDocument();
    expect(screen.getByText("done").parentElement?.className).not.toContain("live-edge");
  });

  it("renders an MCP tag when the call is a user MCP tool", () => {
    render(<ToolActivityBubble content={{ name: "search_web", status: "done", isMcp: true }} />);
    expect(screen.getByText("MCP")).toBeInTheDocument();
  });

  it("stays a plain pill when the call carries no arguments or result", () => {
    render(<ToolActivityBubble content={{ name: "list_workflow_tasks", status: "done" }} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("expands to show the arguments and the result", async () => {
    const user = userEvent.setup();
    render(
      <ToolActivityBubble
        content={{
          name: "search_web",
          status: "done",
          isMcp: true,
          args: { query: "rust" },
          result: { result: { content: ["ok"], structured: null } },
        }}
      />
    );
    const trigger = screen.getByRole("button");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Arguments")).not.toBeInTheDocument();

    await user.click(trigger);

    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Arguments")).toBeInTheDocument();
    expect(screen.getByText("Result")).toBeInTheDocument();
    expect(screen.getByText(/"query": "rust"/)).toBeInTheDocument();
  });

  it("collapses again on a second click", async () => {
    const user = userEvent.setup();
    render(<ToolActivityBubble content={{ name: "search_web", status: "done", args: { q: 1 } }} />);
    const trigger = screen.getByRole("button");
    await user.click(trigger);
    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Arguments")).not.toBeInTheDocument();
  });

  it("renders a Mocked badge when the result came from a stub", () => {
    render(
      <ToolActivityBubble
        content={{
          name: "delete_record",
          status: "done",
          isMcp: true,
          mocked: true,
          result: { mocked: true },
        }}
      />
    );
    expect(screen.getByText("Mocked")).toBeInTheDocument();
  });

  it("shows a string result without re-quoting it", async () => {
    const user = userEvent.setup();
    render(
      <ToolActivityBubble content={{ name: "echo", status: "done", result: "plain answer" }} />
    );
    await user.click(screen.getByRole("button"));
    expect(screen.getByText("plain answer")).toBeInTheDocument();
  });
});
