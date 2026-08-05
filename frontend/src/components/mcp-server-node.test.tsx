import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { McpServerNodeData } from "@/lib/workflow-graph";

// React Flow's Handle needs a provider context that unit tests don't set up.
vi.mock("@xyflow/react", () => ({
  Handle: () => null,
  Position: { Top: "top", Bottom: "bottom", Left: "left", Right: "right" },
}));

import { McpServerNode } from "./mcp-server-node";

/** Render the node with only the props it actually reads. */
function renderNode(data: McpServerNodeData) {
  // React Flow passes many more props; the component only destructures `data`.
  return render(
    <McpServerNode {...({ data } as unknown as React.ComponentProps<typeof McpServerNode>)} />
  );
}

describe("McpServerNode", () => {
  it("renders the server name with the full value as a tooltip", () => {
    renderNode({ serverId: "s1", serverName: "GitHub", toolCount: 2 });
    const label = screen.getByText("GitHub");
    expect(label).toBeInTheDocument();
    expect(label).toHaveAttribute("title", "GitHub");
  });

  it("truncates a long name rather than wrapping it", () => {
    renderNode({ serverId: "s1", serverName: "A very long MCP server name", toolCount: 1 });
    expect(screen.getByText("A very long MCP server name")).toHaveClass("truncate");
  });
});
