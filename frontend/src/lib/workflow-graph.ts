/**
 * Pure helpers that turn a flat list of {@link WorkflowTask}s into the nodes and
 * edges consumed by the React Flow DAG visualization, and that assign positions
 * to those nodes with a dagre hierarchical layout.
 *
 * These functions are deliberately free of any React Flow rendering concerns so
 * they can be unit-tested without a DOM.
 */

import dagre from "@dagrejs/dagre";
import { type Edge, type Node, Position } from "@xyflow/react";
import type { WorkflowTask } from "@/lib/api";

/** Width, in pixels, used for every workflow-task node during layout. */
export const NODE_WIDTH = 220;
/** Height, in pixels, used for every workflow-task node during layout. */
export const NODE_HEIGHT = 72;

/** Data carried by a workflow-task React Flow node. */
export interface WorkflowTaskNodeData extends Record<string, unknown> {
  /** The task this node represents. */
  task: WorkflowTask;
}

/** React Flow node specialized to the workflow-task custom node type. */
export type WorkflowTaskFlowNode = Node<WorkflowTaskNodeData, "workflowTask">;

/**
 * Build React Flow nodes and edges from a list of workflow tasks.
 *
 * Each task becomes one node. For every `dependsOnIds` entry an edge is created
 * from the dependency to the dependent task (`source = dependency`,
 * `target = task`), so the visual flow runs from prerequisites toward the tasks
 * that need them. Dependency IDs that do not correspond to a task in `tasks`
 * (for example a dependency on another page of a paginated list) are skipped to
 * avoid dangling edges.
 *
 * Returned nodes are positioned at the origin; call {@link layoutWorkflowGraph}
 * to assign real coordinates.
 *
 * @param tasks - The tasks belonging to a single workflow session.
 * @returns The unpositioned nodes and the dependency edges between them.
 */
export function buildWorkflowGraph(tasks: WorkflowTask[]): {
  nodes: WorkflowTaskFlowNode[];
  edges: Edge[];
} {
  const ids = new Set(tasks.map((t) => t.id));

  const nodes: WorkflowTaskFlowNode[] = tasks.map((task) => ({
    id: task.id,
    type: "workflowTask",
    position: { x: 0, y: 0 },
    data: { task },
  }));

  const edges: Edge[] = [];
  for (const task of tasks) {
    for (const depId of task.dependsOnIds ?? []) {
      if (!ids.has(depId)) continue;
      edges.push({
        id: `${depId}->${task.id}`,
        source: depId,
        target: task.id,
      });
    }
  }

  return { nodes, edges };
}

/**
 * Assign coordinates to workflow-task nodes using a dagre top-to-bottom
 * hierarchical layout, so dependencies sit above the tasks that depend on them.
 *
 * dagre reports node centers; the returned positions are converted to React
 * Flow's top-left origin. Source/target handle positions are set to bottom/top
 * to match the vertical flow direction.
 *
 * @param nodes - Nodes produced by {@link buildWorkflowGraph}.
 * @param edges - Edges produced by {@link buildWorkflowGraph}.
 * @returns A new array of nodes with `position`, `sourcePosition`, and
 *   `targetPosition` filled in. The input arrays are not mutated.
 */
export function layoutWorkflowGraph(
  nodes: WorkflowTaskFlowNode[],
  edges: Edge[]
): WorkflowTaskFlowNode[] {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "TB", nodesep: 48, ranksep: 64 });

  for (const node of nodes) {
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const edge of edges) {
    graph.setEdge(edge.source, edge.target);
  }

  dagre.layout(graph);

  return nodes.map((node) => {
    const { x, y } = graph.node(node.id);
    return {
      ...node,
      sourcePosition: Position.Bottom,
      targetPosition: Position.Top,
      position: { x: x - NODE_WIDTH / 2, y: y - NODE_HEIGHT / 2 },
    };
  });
}

/**
 * Convenience wrapper that builds the graph and lays it out in one call.
 *
 * @param tasks - The tasks belonging to a single workflow session.
 * @returns Positioned nodes and dependency edges ready for `<ReactFlow>`.
 */
export function buildLayoutedWorkflowGraph(tasks: WorkflowTask[]): {
  nodes: WorkflowTaskFlowNode[];
  edges: Edge[];
} {
  const { nodes, edges } = buildWorkflowGraph(tasks);
  return { nodes: layoutWorkflowGraph(nodes, edges), edges };
}
