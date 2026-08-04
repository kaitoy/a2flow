import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { ToolBinding, WorkflowTask } from "@/lib/api";
import type { WorkflowGraphNode } from "@/lib/workflow-graph";
import { ThemeProvider } from "./ThemeProvider";

// React Flow needs real layout/ResizeObserver that jsdom lacks, so we stub it
// with a lightweight renderer that just prints each node's label. This still
// exercises buildLayoutedWorkflowGraph (the real logic under test).
vi.mock("@xyflow/react", () => ({
  ReactFlow: ({ nodes }: { nodes: WorkflowGraphNode[] }) => (
    <div data-testid="react-flow">
      {nodes.map((n) => (
        <span key={n.id} data-node-type={n.type}>
          {n.type === "workflowTask"
            ? n.data.task.title
            : n.type === "mcpServer"
              ? n.data.serverName
              : n.data.toolName}
        </span>
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
function task(
  id: string,
  dependsOnIds: string[] = [],
  toolBindings: ToolBinding[] = []
): WorkflowTask {
  return {
    id,
    workflowSessionId: "ws-1",
    title: `Task ${id}`,
    status: "pending",
    position: 0,
    dependsOnIds,
    toolBindings,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
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

  it("renders a server node named from serverNameById and a node per bound tool", () => {
    renderWithTheme(
      <WorkflowTaskGraph
        tasks={[
          task(
            "a",
            [],
            [
              { mcpServerId: "s1", toolName: "read_file" },
              { mcpServerId: "s1", toolName: "write_file" },
            ]
          ),
        ]}
        serverNameById={new Map([["s1", "GitHub"]])}
      />
    );

    expect(screen.getByText("GitHub")).toBeInTheDocument();
    expect(screen.getByText("read_file")).toBeInTheDocument();
    expect(screen.getByText("write_file")).toBeInTheDocument();
  });

  it("falls back to a truncated server id when the name is unknown", () => {
    renderWithTheme(
      <WorkflowTaskGraph
        tasks={[task("a", [], [{ mcpServerId: "0123456789ab", toolName: "run" }])]}
      />
    );

    expect(screen.getByText("01234567…")).toBeInTheDocument();
  });
});
