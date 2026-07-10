import { render, screen } from "@testing-library/react";
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
});
