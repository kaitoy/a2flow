import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { WorkflowTaskNodeData } from "@/lib/workflow-graph";

// React Flow's Handle needs a provider context that unit tests don't set up.
vi.mock("@xyflow/react", () => ({
  Handle: () => null,
  Position: { Top: "top", Bottom: "bottom", Left: "left", Right: "right" },
}));

import { WorkflowTaskNode } from "./workflow-task-node";

/** Render the node with only the props it actually reads. */
function renderNode(data: WorkflowTaskNodeData) {
  // React Flow passes many more props; the component only destructures `data`.
  return render(
    <WorkflowTaskNode {...({ data } as unknown as React.ComponentProps<typeof WorkflowTaskNode>)} />
  );
}

describe("WorkflowTaskNode", () => {
  it("renders the task's ordinal (1-based from columnIndex) and title", () => {
    renderNode({ task: { id: "a", title: "Collect requirements" }, columnIndex: 2 });
    expect(screen.getByText("#3")).toBeInTheDocument();
    expect(screen.getByText("Collect requirements")).toBeInTheDocument();
  });

  it("shows the status label for a session task", () => {
    renderNode({
      task: { id: "a", title: "Run tests", status: "in_progress" },
      columnIndex: 0,
    });
    expect(screen.getByText("in progress")).toBeInTheDocument();
  });

  it("omits the status row for a status-less task template", () => {
    renderNode({ task: { id: "a", title: "Template step" }, columnIndex: 0 });
    expect(screen.queryByText(/pending/i)).not.toBeInTheDocument();
  });
});
