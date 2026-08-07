/**
 * Pure helpers that turn a flat list of {@link WorkflowTask}s into the nodes and
 * edges consumed by the React Flow visualization, and that assign positions to
 * those nodes.
 *
 * The graph has two axes. Tasks are stacked in a single vertical column in
 * dependency order, so the whole run reads top to bottom as one list. Each task
 * then branches rightward into the MCP servers it binds tools from, and each
 * server into the individual tool names. Servers are duplicated per task rather
 * than shared across the whole graph, so the column stays straight instead of
 * being pulled sideways by crossing edges.
 *
 * The column is deliberately not a hierarchical (dagre-style) layout: that
 * spreads independent tasks across a rank, which is exactly the horizontal
 * drift this view is meant to avoid. Tasks are ordered by a topological sort
 * instead, tie-broken by `position` so the column matches the order the task
 * list shows.
 *
 * These functions are deliberately free of any React Flow rendering concerns so
 * they can be unit-tested without a DOM.
 */

import type { Edge, Node } from "@xyflow/react";
import type { ToolBinding, WorkflowTaskStatus } from "@/lib/api";

/** Width, in pixels, of a workflow-task node. */
export const TASK_NODE_WIDTH = 220;
/** Height, in pixels, of a workflow-task node. */
export const TASK_NODE_HEIGHT = 72;
/** Width, in pixels, of an MCP server node. */
export const SERVER_NODE_WIDTH = 176;
/** Height, in pixels, of an MCP server node. Must match the node component's height class. */
export const SERVER_NODE_HEIGHT = 36;
/** Width, in pixels, of an MCP tool node. */
export const TOOL_NODE_WIDTH = 200;
/** Height, in pixels, of an MCP tool node. Must match the node component's height class. */
export const TOOL_NODE_HEIGHT = 36;
/** Horizontal gutter between the task, server, and tool columns of a row. */
export const COLUMN_GAP = 56;
/** Vertical gap between sibling tool nodes of one server. */
export const TOOL_GAP = 12;
/** Vertical gap between the server rows of one task. */
export const SERVER_GAP = 20;
/** Vertical gap between two tasks of the column. */
export const ROW_GAP = 40;
/** How far a row-skipping dependency edge steps out to the left of the column. */
export const SKIP_EDGE_OFFSET = 28;

/** Handle id of the task node's incoming handle from the task directly above (top edge). */
export const TASK_DEP_TARGET_HANDLE = "dep-in";
/** Handle id of the task node's outgoing handle to the task directly below (bottom edge). */
export const TASK_DEP_SOURCE_HANDLE = "dep-out";
/** Handle id of the task node's incoming handle for dependencies further up the column (left edge). */
export const TASK_SKIP_TARGET_HANDLE = "skip-in";
/** Handle id of the task node's outgoing handle for dependents further down the column (left edge). */
export const TASK_SKIP_SOURCE_HANDLE = "skip-out";
/** Handle id of the task node's outgoing handle toward its MCP servers (right edge). */
export const TASK_TOOLS_SOURCE_HANDLE = "tools-out";
/** Handle id of the incoming handle on server and tool nodes (left edge). */
export const BRANCH_TARGET_HANDLE = "branch-in";
/** Handle id of the server node's outgoing handle toward its tools (right edge). */
export const BRANCH_SOURCE_HANDLE = "branch-out";

/**
 * One vertex of the DAG: a session's WorkflowTask, or a workflow's task
 * template, which has no status (the lifecycle belongs to a run, not the
 * design). Both satisfy this shape structurally.
 */
export interface GraphTask {
  /** Node identifier; dependency edges reference these. */
  id: string;
  /** Title shown inside the node. */
  title: string;
  /** Layout/order hint shown as the node's ordinal, and the column's tie-break. */
  position?: number | null;
  /** Ids of the tasks this one depends on (incoming edges). */
  dependsOnIds?: string[] | null;
  /** Lifecycle status, or absent for status-less entries (task templates). */
  status?: WorkflowTaskStatus | null;
  /** MCP tools bound to this task, rendered as the task's rightward branch. */
  toolBindings?: ToolBinding[] | null;
}

/** Data carried by a workflow-task React Flow node. */
export interface WorkflowTaskNodeData extends Record<string, unknown> {
  /** The task this node represents. */
  task: GraphTask;
}

/** Data carried by an MCP server React Flow node. */
export interface McpServerNodeData extends Record<string, unknown> {
  /** Id of the registered MCP server. */
  serverId: string;
  /** Display name, or a truncated id when the server registry is unavailable. */
  serverName: string;
  /** How many of this task's tools come from this server. */
  toolCount: number;
}

/** Data carried by an MCP tool React Flow node. */
export interface McpToolNodeData extends Record<string, unknown> {
  /** Id of the MCP server advertising this tool. */
  serverId: string;
  /** Name of the bound tool. */
  toolName: string;
}

/** React Flow node specialized to the workflow-task custom node type. */
export type WorkflowTaskFlowNode = Node<WorkflowTaskNodeData, "workflowTask">;
/** React Flow node specialized to the MCP server custom node type. */
export type McpServerFlowNode = Node<McpServerNodeData, "mcpServer">;
/** React Flow node specialized to the MCP tool custom node type. */
export type McpToolFlowNode = Node<McpToolNodeData, "mcpTool">;

/** Any node the workflow graph can contain, discriminated by its `type`. */
export type WorkflowGraphNode = WorkflowTaskFlowNode | McpServerFlowNode | McpToolFlowNode;

/** The MCP servers of one task, each with the tool names bound from it. */
export interface TaskServerGroup {
  /** Id of the registered MCP server. */
  serverId: string;
  /** Display name, or a truncated id when the server registry is unavailable. */
  serverName: string;
  /** Tool names bound from this server, in binding order. Never empty. */
  toolNames: string[];
}

/** A task together with the branch hanging off it, in column order. */
export interface TaskRow {
  /** Id of the task this row belongs to. */
  taskId: string;
  /** The task's MCP servers in binding order; empty when nothing is bound. */
  servers: TaskServerGroup[];
}

/** Unpositioned graph produced by {@link buildWorkflowGraph}. */
export interface WorkflowGraph {
  /** Task, server, and tool nodes, all still at the origin. */
  nodes: WorkflowGraphNode[];
  /** Dependency, task-to-server, and server-to-tool edges. */
  edges: Edge[];
  /** The task rows in column order, consumed by {@link layoutWorkflowGraph}. */
  rows: TaskRow[];
}

/** Build the React Flow node id of a task's MCP server node. */
export function serverNodeId(taskId: string, serverId: string): string {
  return `${taskId}::server::${serverId}`;
}

/** Build the React Flow node id of a task's MCP tool node. */
export function toolNodeId(taskId: string, serverId: string, toolName: string): string {
  return `${taskId}::tool::${serverId}::${toolName}`;
}

/** Label an MCP server by name, falling back to a truncated id when unknown. */
function serverLabel(serverId: string, serverNameById: Map<string, string>): string {
  return serverNameById.get(serverId) ?? `${serverId.slice(0, 8)}…`;
}

/**
 * Group a task's tool bindings by MCP server, preserving binding order for both
 * the servers and the tools within each server, and dropping exact duplicate
 * `(server, tool)` pairs so no two nodes end up sharing an id.
 */
function groupBindingsByServer(
  bindings: ToolBinding[],
  serverNameById: Map<string, string>
): TaskServerGroup[] {
  const groups: TaskServerGroup[] = [];
  const byId = new Map<string, TaskServerGroup>();

  for (const binding of bindings) {
    let group = byId.get(binding.mcpServerId);
    if (!group) {
      group = {
        serverId: binding.mcpServerId,
        serverName: serverLabel(binding.mcpServerId, serverNameById),
        toolNames: [],
      };
      byId.set(binding.mcpServerId, group);
      groups.push(group);
    }
    if (!group.toolNames.includes(binding.toolName)) {
      group.toolNames.push(binding.toolName);
    }
  }

  return groups;
}

/**
 * Order tasks for the vertical column: a topological sort over the dependency
 * edges, so a task always sits below everything it depends on, with ties broken
 * by `position` (then input order) so the column matches the task list.
 *
 * Dependencies on ids outside `tasks` — a dependency on another page of a
 * paginated list — are ignored, exactly as the edge builder ignores them.
 * A cycle would leave tasks unreachable; the backend rejects cycles, but any
 * leftovers are appended in input order rather than dropped, so the view never
 * silently loses a task.
 *
 * @param tasks - The tasks to order.
 * @returns The same tasks, in column order.
 */
function orderTasksForColumn(tasks: GraphTask[]): GraphTask[] {
  const indexById = new Map(tasks.map((task, index) => [task.id, index]));
  const remaining = new Map<string, number>();
  const dependents = new Map<string, string[]>();

  for (const task of tasks) {
    const deps = (task.dependsOnIds ?? []).filter((id) => indexById.has(id) && id !== task.id);
    remaining.set(task.id, new Set(deps).size);
    for (const dep of new Set(deps)) {
      dependents.set(dep, [...(dependents.get(dep) ?? []), task.id]);
    }
  }

  /** Column order among tasks whose dependencies are all already placed. */
  const byPosition = (a: string, b: string): number => {
    const left = tasks[indexById.get(a) as number];
    const right = tasks[indexById.get(b) as number];
    return (
      (left.position ?? 0) - (right.position ?? 0) ||
      (indexById.get(a) as number) - (indexById.get(b) as number)
    );
  };

  const ready = tasks.filter((t) => remaining.get(t.id) === 0).map((t) => t.id);
  const ordered: GraphTask[] = [];
  const placed = new Set<string>();

  while (ready.length > 0) {
    ready.sort(byPosition);
    const id = ready.shift() as string;
    placed.add(id);
    ordered.push(tasks[indexById.get(id) as number]);
    for (const dependent of dependents.get(id) ?? []) {
      const left = (remaining.get(dependent) as number) - 1;
      remaining.set(dependent, left);
      if (left === 0) ready.push(dependent);
    }
  }

  for (const task of tasks) {
    if (!placed.has(task.id)) ordered.push(task);
  }
  return ordered;
}

/**
 * Build React Flow nodes and edges from a list of workflow tasks.
 *
 * Tasks are ordered into a single column (see {@link orderTasksForColumn}) and
 * each becomes one node. For every `dependsOnIds` entry an edge is created from
 * the dependency to the dependent task, so the visual flow runs from
 * prerequisites toward the tasks that need them. Dependency IDs that do not
 * correspond to a task in `tasks` (for example a dependency on another page of
 * a paginated list) are skipped to avoid dangling edges.
 *
 * A dependency between neighbouring rows runs straight down through the
 * top/bottom handles. One that skips rows is routed out of the *left* handles
 * instead: with every task at the same x, a straight edge would be drawn
 * underneath the tasks it passes and vanish behind them.
 *
 * Each task's `toolBindings` additionally produce one node per distinct MCP
 * server and one node per bound tool, wired task → server → tool. Servers are
 * scoped to their task, so two tasks binding the same server get two nodes.
 *
 * Every edge names its handles explicitly: the task node carries several source
 * handles, and React Flow only matches a handle-less edge against a handle-less
 * node.
 *
 * Returned nodes are positioned at the origin; call {@link layoutWorkflowGraph}
 * to assign real coordinates.
 *
 * @param tasks - The tasks of a single workflow execution or workflow design.
 * @param serverNameById - Registered MCP server names by id, used to label
 *   server nodes. Ids missing from the map fall back to a truncated id.
 * @returns The unpositioned nodes, the edges between them, and the task rows in
 *   column order.
 */
export function buildWorkflowGraph(
  tasks: GraphTask[],
  serverNameById: Map<string, string> = new Map()
): WorkflowGraph {
  const ordered = orderTasksForColumn(tasks);
  const rowByTaskId = new Map(ordered.map((task, row) => [task.id, row]));

  const nodes: WorkflowGraphNode[] = [];
  const edges: Edge[] = [];
  const rows: TaskRow[] = [];

  for (const task of ordered) {
    nodes.push({
      id: task.id,
      type: "workflowTask",
      position: { x: 0, y: 0 },
      data: { task },
    });

    const servers = groupBindingsByServer(task.toolBindings ?? [], serverNameById);
    rows.push({ taskId: task.id, servers });

    for (const group of servers) {
      const serverId = serverNodeId(task.id, group.serverId);
      nodes.push({
        id: serverId,
        type: "mcpServer",
        position: { x: 0, y: 0 },
        data: {
          serverId: group.serverId,
          serverName: group.serverName,
          toolCount: group.toolNames.length,
        },
      });
      edges.push({
        id: `${task.id}->${serverId}`,
        source: task.id,
        target: serverId,
        sourceHandle: TASK_TOOLS_SOURCE_HANDLE,
        targetHandle: BRANCH_TARGET_HANDLE,
      });

      for (const toolName of group.toolNames) {
        const toolId = toolNodeId(task.id, group.serverId, toolName);
        nodes.push({
          id: toolId,
          type: "mcpTool",
          position: { x: 0, y: 0 },
          data: { serverId: group.serverId, toolName },
        });
        edges.push({
          id: `${serverId}->${toolId}`,
          source: serverId,
          target: toolId,
          sourceHandle: BRANCH_SOURCE_HANDLE,
          targetHandle: BRANCH_TARGET_HANDLE,
        });
      }
    }
  }

  for (const task of ordered) {
    const targetRow = rowByTaskId.get(task.id) as number;
    for (const depId of task.dependsOnIds ?? []) {
      const sourceRow = rowByTaskId.get(depId);
      if (sourceRow === undefined || depId === task.id) continue;
      const adjacent = targetRow - sourceRow === 1;
      edges.push({
        id: `${depId}->${task.id}`,
        source: depId,
        target: task.id,
        sourceHandle: adjacent ? TASK_DEP_SOURCE_HANDLE : TASK_SKIP_SOURCE_HANDLE,
        targetHandle: adjacent ? TASK_DEP_TARGET_HANDLE : TASK_SKIP_TARGET_HANDLE,
        // Both side handles share an x, so the default bezier would collapse
        // into a vertical line hugging the column. smoothstep steps out to the
        // left instead, which is what makes the detour readable.
        ...(adjacent ? {} : { type: "smoothstep", pathOptions: { offset: SKIP_EDGE_OFFSET } }),
      });
    }
  }

  return { nodes, edges, rows };
}

/** Height a server row occupies: the server node, or its stack of tools if taller. */
function serverRowHeight(group: TaskServerGroup): number {
  const count = group.toolNames.length;
  return Math.max(SERVER_NODE_HEIGHT, count * TOOL_NODE_HEIGHT + (count - 1) * TOOL_GAP);
}

/** Total height of a task's branch, or 0 when it binds no tools. */
function branchHeight(row: TaskRow): number {
  if (row.servers.length === 0) return 0;
  const stacked = row.servers.reduce((sum, group) => sum + serverRowHeight(group), 0);
  return stacked + (row.servers.length - 1) * SERVER_GAP;
}

/**
 * Assign coordinates to every node by stacking the task rows into one column.
 *
 * Every task node gets the same `x`, so the column is exactly vertical however
 * the dependencies branch. A row is as tall as its branch needs, and the task
 * node is centred against that branch. Server and tool nodes sit in two further
 * columns to the right, each server's tools centred on the server.
 *
 * Handle positions live on the node components, so no
 * `sourcePosition`/`targetPosition` is set here — those only affect built-in
 * node types.
 *
 * @param graph - The graph produced by {@link buildWorkflowGraph}.
 * @returns A new array of nodes with `position` filled in. The input is not
 *   mutated.
 */
export function layoutWorkflowGraph(graph: WorkflowGraph): WorkflowGraphNode[] {
  const serverColumnX = TASK_NODE_WIDTH + COLUMN_GAP;
  const toolColumnX = serverColumnX + SERVER_NODE_WIDTH + COLUMN_GAP;

  /** Top-left corner of every node, keyed by node id. */
  const positions = new Map<string, { x: number; y: number }>();
  let cursor = 0;

  for (const row of graph.rows) {
    const height = Math.max(TASK_NODE_HEIGHT, branchHeight(row));
    const rowCenter = cursor + height / 2;
    positions.set(row.taskId, { x: 0, y: rowCenter - TASK_NODE_HEIGHT / 2 });

    let branchCursor = rowCenter - branchHeight(row) / 2;
    for (const group of row.servers) {
      const groupHeight = serverRowHeight(group);
      const groupCenter = branchCursor + groupHeight / 2;
      positions.set(serverNodeId(row.taskId, group.serverId), {
        x: serverColumnX,
        y: groupCenter - SERVER_NODE_HEIGHT / 2,
      });

      const count = group.toolNames.length;
      const toolsHeight = count * TOOL_NODE_HEIGHT + (count - 1) * TOOL_GAP;
      group.toolNames.forEach((toolName, index) => {
        positions.set(toolNodeId(row.taskId, group.serverId, toolName), {
          x: toolColumnX,
          y: groupCenter - toolsHeight / 2 + index * (TOOL_NODE_HEIGHT + TOOL_GAP),
        });
      });

      branchCursor += groupHeight + SERVER_GAP;
    }

    cursor += height + ROW_GAP;
  }

  return graph.nodes.map((node) => ({
    ...node,
    position: positions.get(node.id) ?? node.position,
  }));
}

/**
 * Convenience wrapper that builds the graph and lays it out in one call.
 *
 * @param tasks - The tasks of a single workflow execution or workflow design.
 * @param serverNameById - Registered MCP server names by id, used to label
 *   server nodes.
 * @returns Positioned nodes and edges ready for `<ReactFlow>`.
 */
export function buildLayoutedWorkflowGraph(
  tasks: GraphTask[],
  serverNameById?: Map<string, string>
): { nodes: WorkflowGraphNode[]; edges: Edge[] } {
  const graph = buildWorkflowGraph(tasks, serverNameById);
  return { nodes: layoutWorkflowGraph(graph), edges: graph.edges };
}
