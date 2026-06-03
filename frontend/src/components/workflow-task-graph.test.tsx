import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { WorkflowTask } from "@/lib/api";
import type { WorkflowTaskFlowNode } from "@/lib/workflow-graph";
import { ThemeProvider } from "./ThemeProvider";

// React Flow needs real layout/ResizeObserver that jsdom lacks, so we stub it
// with a lightweight renderer that just prints each node's task title. This
// still exercises buildLayoutedWorkflowGraph (the real logic under test).
vi.mock("@xyflow/react", () => ({
  ReactFlow: ({ nodes }: { nodes: WorkflowTaskFlowNode[] }) => (
    <div data-testid="react-flow">
      {nodes.map((n) => (
        <span key={n.id}>{n.data.task.title}</span>
      ))}
    </div>
  ),
  Background: () => null,
  Controls: () => null,
  Handle: () => null,
  BackgroundVariant: { Dots: "dots" },
  Position: { Top: "top", Bottom: "bottom", Left: "left", Right: "right" },
}));

import { WorkflowTaskGraph } from "./workflow-task-graph";

/** Build a minimal WorkflowTask for rendering tests. */
function task(id: string, dependsOnIds: string[] = []): WorkflowTask {
  return {
    id,
    workflowSessionId: "ws-1",
    title: `Task ${id}`,
    status: "pending",
    position: 0,
    dependsOnIds,
  };
}

function renderWithTheme(ui: ReactNode) {
  return render(<ThemeProvider>{ui}</ThemeProvider>);
}

describe("WorkflowTaskGraph", () => {
  it("renders a node for each task", () => {
    renderWithTheme(<WorkflowTaskGraph tasks={[task("a"), task("b", ["a"])]} />);
    expect(screen.getByText("Task a")).toBeInTheDocument();
    expect(screen.getByText("Task b")).toBeInTheDocument();
  });

  it("shows an empty message when there are no tasks", () => {
    renderWithTheme(<WorkflowTaskGraph tasks={[]} />);
    expect(screen.getByText(/no tasks to visualize/i)).toBeInTheDocument();
    expect(screen.queryByTestId("react-flow")).not.toBeInTheDocument();
  });
});
