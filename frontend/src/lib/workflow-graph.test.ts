import { describe, expect, it } from "vitest";
import type { WorkflowTask } from "@/lib/api";
import {
  buildLayoutedWorkflowGraph,
  buildWorkflowGraph,
  layoutWorkflowGraph,
} from "@/lib/workflow-graph";

/** Build a minimal WorkflowTask for graph tests. */
function task(id: string, dependsOnIds: string[] = [], position = 0): WorkflowTask {
  return {
    id,
    workflowSessionId: "ws-1",
    title: `Task ${id}`,
    status: "pending",
    position,
    dependsOnIds,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
  };
}

describe("buildWorkflowGraph", () => {
  it("creates one node per task", () => {
    const { nodes } = buildWorkflowGraph([task("a"), task("b")]);
    expect(nodes.map((n) => n.id)).toEqual(["a", "b"]);
    expect(nodes.every((n) => n.type === "workflowTask")).toBe(true);
  });

  it("creates an edge from dependency to dependent task", () => {
    const { edges } = buildWorkflowGraph([task("a"), task("b", ["a"])]);
    expect(edges).toHaveLength(1);
    expect(edges[0]).toMatchObject({ source: "a", target: "b" });
  });

  it("skips dependency ids that are not present in the task list", () => {
    const { edges } = buildWorkflowGraph([task("b", ["missing"])]);
    expect(edges).toHaveLength(0);
  });

  it("handles tasks with no dependsOnIds field", () => {
    const bare = { id: "x", workflowSessionId: "ws-1", title: "x" } as WorkflowTask;
    const { nodes, edges } = buildWorkflowGraph([bare]);
    expect(nodes).toHaveLength(1);
    expect(edges).toHaveLength(0);
  });
});

describe("layoutWorkflowGraph", () => {
  it("assigns a position to every node without mutating inputs", () => {
    const { nodes, edges } = buildWorkflowGraph([task("a"), task("b", ["a"])]);
    const laidOut = layoutWorkflowGraph(nodes, edges);
    expect(laidOut).toHaveLength(2);
    for (const node of laidOut) {
      expect(Number.isFinite(node.position.x)).toBe(true);
      expect(Number.isFinite(node.position.y)).toBe(true);
    }
    // Inputs untouched (still at origin).
    expect(nodes[0].position).toEqual({ x: 0, y: 0 });
  });

  it("places a dependent task to the right of its dependency (larger x)", () => {
    const { nodes } = buildLayoutedWorkflowGraph([task("a"), task("b", ["a"])]);
    const a = nodes.find((n) => n.id === "a");
    const b = nodes.find((n) => n.id === "b");
    expect(b?.position.x).toBeGreaterThan(a?.position.x ?? 0);
  });
});
