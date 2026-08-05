import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { McpToolNodeData } from "@/lib/workflow-graph";

// React Flow's Handle needs a provider context that unit tests don't set up.
vi.mock("@xyflow/react", () => ({
  Handle: () => null,
  Position: { Top: "top", Bottom: "bottom", Left: "left", Right: "right" },
}));

import { McpToolNode } from "./mcp-tool-node";

/** Render the node with only the props it actually reads. */
function renderNode(data: McpToolNodeData) {
  // React Flow passes many more props; the component only destructures `data`.
  return render(
    <McpToolNode {...({ data } as unknown as React.ComponentProps<typeof McpToolNode>)} />
  );
}

describe("McpToolNode", () => {
  it("renders the tool name with the full value as a tooltip", () => {
    renderNode({ serverId: "s1", toolName: "create_pull_request" });
    const label = screen.getByText("create_pull_request");
    expect(label).toBeInTheDocument();
    expect(label).toHaveAttribute("title", "create_pull_request");
  });

  it("renders the tool name in the mono data face, truncated", () => {
    renderNode({ serverId: "s1", toolName: "mcp__github__create_pull_request" });
    const label = screen.getByText("mcp__github__create_pull_request");
    expect(label).toHaveClass("font-mono");
    expect(label).toHaveClass("truncate");
  });
});
