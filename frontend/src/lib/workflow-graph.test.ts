import { describe, expect, it } from "vitest";
import type { ToolBinding, WorkflowTask } from "@/lib/api";
import {
  BRANCH_SOURCE_HANDLE,
  BRANCH_TARGET_HANDLE,
  buildLayoutedWorkflowGraph,
  buildWorkflowGraph,
  layoutWorkflowGraph,
  SERVER_NODE_HEIGHT,
  SERVER_NODE_WIDTH,
  serverNodeId,
  TASK_DEP_SOURCE_HANDLE,
  TASK_DEP_TARGET_HANDLE,
  TASK_NODE_HEIGHT,
  TASK_NODE_WIDTH,
  TASK_SKIP_SOURCE_HANDLE,
  TASK_SKIP_TARGET_HANDLE,
  TASK_TOOLS_SOURCE_HANDLE,
  TOOL_NODE_HEIGHT,
  TOOL_NODE_WIDTH,
  toolNodeId,
  type WorkflowGraphNode,
} from "@/lib/workflow-graph";

/** Build a minimal WorkflowTask for graph tests. */
function task(
  id: string,
  dependsOnIds: string[] = [],
  position = 0,
  toolBindings: ToolBinding[] = []
): WorkflowTask {
  return {
    id,
    workflowExecutionId: "execution-1",
    title: `Task ${id}`,
    status: "pending",
    position,
    dependsOnIds,
    toolBindings,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
  };
}

/** Shorthand for a `(server, tool)` binding. */
function binding(mcpServerId: string, toolName: string): ToolBinding {
  return { mcpServerId, toolName };
}

/** Rendered size of a laid-out node, keyed off its discriminant. */
function nodeSize(node: WorkflowGraphNode): { width: number; height: number } {
  switch (node.type) {
    case "workflowTask":
      return { width: TASK_NODE_WIDTH, height: TASK_NODE_HEIGHT };
    case "mcpServer":
      return { width: SERVER_NODE_WIDTH, height: SERVER_NODE_HEIGHT };
    default:
      return { width: TOOL_NODE_WIDTH, height: TOOL_NODE_HEIGHT };
  }
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
    expect(edges[0]).toMatchObject({
      source: "a",
      target: "b",
      sourceHandle: TASK_DEP_SOURCE_HANDLE,
      targetHandle: TASK_DEP_TARGET_HANDLE,
    });
  });

  it("routes a dependency that skips rows through the side handles", () => {
    // c depends on a, but b sits between them in the column.
    const { edges } = buildWorkflowGraph([
      task("a", [], 0),
      task("b", ["a"], 1),
      task("c", ["a", "b"], 2),
    ]);

    expect(edges).toContainEqual(
      expect.objectContaining({
        source: "a",
        target: "c",
        sourceHandle: TASK_SKIP_SOURCE_HANDLE,
        targetHandle: TASK_SKIP_TARGET_HANDLE,
      })
    );
    expect(edges).toContainEqual(
      expect.objectContaining({
        source: "b",
        target: "c",
        sourceHandle: TASK_DEP_SOURCE_HANDLE,
        targetHandle: TASK_DEP_TARGET_HANDLE,
      })
    );
  });

  it("orders tasks so dependencies come first, tie-broken by position", () => {
    // Input order is deliberately not the column order.
    const { nodes } = buildWorkflowGraph([
      task("late", ["early"], 9),
      task("sibling", [], 1),
      task("early", [], 0),
    ]);
    expect(nodes.filter((n) => n.type === "workflowTask").map((n) => n.id)).toEqual([
      "early",
      "sibling",
      "late",
    ]);
  });

  it("still emits every task when the dependencies form a cycle", () => {
    const { nodes } = buildWorkflowGraph([task("a", ["b"]), task("b", ["a"])]);
    expect(nodes.filter((n) => n.type === "workflowTask").map((n) => n.id)).toEqual(["a", "b"]);
  });

  it("skips dependency ids that are not present in the task list", () => {
    const { edges } = buildWorkflowGraph([task("b", ["missing"])]);
    expect(edges).toHaveLength(0);
  });

  it("handles tasks with no dependsOnIds field", () => {
    const bare = { id: "x", workflowExecutionId: "execution-1", title: "x" } as WorkflowTask;
    const { nodes, edges } = buildWorkflowGraph([bare]);
    expect(nodes).toHaveLength(1);
    expect(edges).toHaveLength(0);
  });

  it("creates one server node per distinct server and one tool node per binding", () => {
    const { nodes } = buildWorkflowGraph(
      [task("a", [], 0, [binding("s1", "read"), binding("s1", "write"), binding("s2", "post")])],
      new Map([
        ["s1", "GitHub"],
        ["s2", "Slack"],
      ])
    );

    expect(nodes.filter((n) => n.type === "mcpServer").map((n) => n.id)).toEqual([
      serverNodeId("a", "s1"),
      serverNodeId("a", "s2"),
    ]);
    expect(nodes.filter((n) => n.type === "mcpTool").map((n) => n.id)).toEqual([
      toolNodeId("a", "s1", "read"),
      toolNodeId("a", "s1", "write"),
      toolNodeId("a", "s2", "post"),
    ]);
  });

  it("wires task -> server -> tool with the branch handles", () => {
    const { edges } = buildWorkflowGraph([task("a", [], 0, [binding("s1", "read")])]);

    expect(edges).toContainEqual(
      expect.objectContaining({
        source: "a",
        target: serverNodeId("a", "s1"),
        sourceHandle: TASK_TOOLS_SOURCE_HANDLE,
        targetHandle: BRANCH_TARGET_HANDLE,
      })
    );
    expect(edges).toContainEqual(
      expect.objectContaining({
        source: serverNodeId("a", "s1"),
        target: toolNodeId("a", "s1", "read"),
        sourceHandle: BRANCH_SOURCE_HANDLE,
        targetHandle: BRANCH_TARGET_HANDLE,
      })
    );
  });

  it("duplicates a shared server per task instead of merging it", () => {
    const { nodes } = buildWorkflowGraph([
      task("a", [], 0, [binding("s1", "read")]),
      task("b", [], 1, [binding("s1", "write")]),
    ]);

    const servers = nodes.filter((n) => n.type === "mcpServer");
    expect(servers.map((n) => n.id)).toEqual([serverNodeId("a", "s1"), serverNodeId("b", "s1")]);
    expect(servers.every((n) => n.data.serverId === "s1")).toBe(true);
  });

  it("labels a server by name and falls back to a truncated id", () => {
    const { nodes } = buildWorkflowGraph(
      [task("a", [], 0, [binding("known-server-id", "read"), binding("0123456789ab", "write")])],
      new Map([["known-server-id", "GitHub"]])
    );

    const names = nodes.filter((n) => n.type === "mcpServer").map((n) => n.data.serverName);
    expect(names).toEqual(["GitHub", "01234567…"]);
  });

  it("counts the tools of each server node", () => {
    const { nodes } = buildWorkflowGraph([
      task("a", [], 0, [binding("s1", "read"), binding("s1", "write")]),
    ]);
    const server = nodes.find((n) => n.type === "mcpServer");
    expect(server?.data.toolCount).toBe(2);
  });

  it("keeps every node id unique even when a binding is repeated", () => {
    const { nodes } = buildWorkflowGraph([
      task("a", [], 0, [binding("s1", "read"), binding("s1", "read")]),
    ]);
    expect(new Set(nodes.map((n) => n.id)).size).toBe(nodes.length);
    expect(nodes.filter((n) => n.type === "mcpTool")).toHaveLength(1);
  });
});

describe("layoutWorkflowGraph", () => {
  it("assigns a position to every node without mutating inputs", () => {
    const graph = buildWorkflowGraph([task("a"), task("b", ["a"])]);
    const laidOut = layoutWorkflowGraph(graph);
    expect(laidOut).toHaveLength(2);
    for (const node of laidOut) {
      expect(Number.isFinite(node.position.x)).toBe(true);
      expect(Number.isFinite(node.position.y)).toBe(true);
    }
    // Inputs untouched (still at origin).
    expect(graph.nodes[0].position).toEqual({ x: 0, y: 0 });
  });

  it("stacks a dependent task below its dependency", () => {
    const { nodes } = buildLayoutedWorkflowGraph([task("a"), task("b", ["a"])]);
    const a = nodes.find((n) => n.id === "a");
    const b = nodes.find((n) => n.id === "b");
    expect(b?.position.y).toBeGreaterThan(a?.position.y ?? 0);
  });

  it("puts every task at the same x, however the dependencies branch", () => {
    // Two independent tasks depend on the first and both feed the last: a
    // hierarchical layout would spread them across a rank. This is the whole
    // point of the column, so pin it.
    const { nodes } = buildLayoutedWorkflowGraph([
      task("a", [], 0, [binding("s1", "read"), binding("s2", "write")]),
      task("b", ["a"], 1, [binding("s1", "read")]),
      task("c", ["a"], 2),
      task("d", ["b", "c"], 3),
    ]);

    const xs = nodes.filter((n) => n.type === "workflowTask").map((n) => n.position.x);
    expect(xs).toHaveLength(4);
    expect(new Set(xs).size).toBe(1);
  });

  it("places a task's servers to its right and its tools right of the servers", () => {
    const { nodes } = buildLayoutedWorkflowGraph([task("a", [], 0, [binding("s1", "read")])]);
    const taskX = nodes.find((n) => n.id === "a")?.position.x ?? 0;
    const serverX = nodes.find((n) => n.id === serverNodeId("a", "s1"))?.position.x ?? 0;
    const toolX = nodes.find((n) => n.id === toolNodeId("a", "s1", "read"))?.position.x ?? 0;

    expect(serverX).toBeGreaterThan(taskX);
    expect(toolX).toBeGreaterThan(serverX);
  });

  it("stacks a server's tools in binding order", () => {
    const { nodes } = buildLayoutedWorkflowGraph([
      task("a", [], 0, [binding("s1", "read"), binding("s1", "write")]),
    ]);
    const first = nodes.find((n) => n.id === toolNodeId("a", "s1", "read"))?.position.y ?? 0;
    const second = nodes.find((n) => n.id === toolNodeId("a", "s1", "write"))?.position.y ?? 0;
    expect(second).toBeGreaterThan(first);
  });

  it("never overlaps two nodes", () => {
    const { nodes } = buildLayoutedWorkflowGraph([
      task("a", [], 0, [binding("s1", "read"), binding("s1", "write"), binding("s2", "post")]),
      task("b", ["a"], 1, [binding("s2", "post")]),
      task("c", ["a"], 2),
      task("d", ["b", "c"], 3, [binding("s1", "read")]),
    ]);

    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i];
        const b = nodes[j];
        const sa = nodeSize(a);
        const sb = nodeSize(b);
        const overlaps =
          a.position.x < b.position.x + sb.width &&
          b.position.x < a.position.x + sa.width &&
          a.position.y < b.position.y + sb.height &&
          b.position.y < a.position.y + sa.height;
        expect(overlaps, `${a.id} overlaps ${b.id}`).toBe(false);
      }
    }
  });
});
