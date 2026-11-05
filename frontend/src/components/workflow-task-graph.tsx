"use client";

import { Background, BackgroundVariant, Controls, type NodeTypes, ReactFlow } from "@xyflow/react";
import { useT } from "@/i18n/provider";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import { buildLayoutedWorkflowGraph, type GraphTask } from "@/lib/workflow-graph";
import { McpServerNode } from "./mcp-server-node";
import { McpToolNode } from "./mcp-tool-node";
import { useTheme } from "./ThemeProvider";
import { WorkflowTaskNode } from "./workflow-task-node";

/** Maps each custom node `type` string to its renderer. Defined once outside the
 * component so React Flow does not warn about a new object on every render. */
const NODE_TYPES: NodeTypes = {
  workflowTask: WorkflowTaskNode,
  mcpServer: McpServerNode,
  mcpTool: McpToolNode,
};

/** Stable empty default for `serverNameById`, so an omitted prop does not
 * invalidate the layout memo on every render. */
const EMPTY_SERVER_NAMES: Map<string, string> = new Map();

/** Props for {@link WorkflowTaskGraph}. */
export interface WorkflowTaskGraphProps {
  /** Tasks of a single workflow execution (or a workflow's task templates) to visualize as a DAG. */
  tasks: GraphTask[];
  /** Registered MCP server names by id, used to label the server nodes. Ids
   * missing from the map fall back to a truncated id. */
  serverNameById?: Map<string, string>;
}

/**
 * Read-only React Flow visualization of a workflow's task DAG and the MCP tools
 * its tasks are bound to.
 *
 * Tasks are stacked in a single vertical column in dependency order, so the run
 * reads top to bottom as one list. Each task then branches rightward into the
 * MCP servers it binds tools from, and each server into the individual tool
 * names. Servers are repeated per task rather than shared, so the column stays
 * straight.
 *
 * The view is read-only and nodes are fixed in place: dependency editing happens
 * on the task forms, and dragging a task would leave its branch behind.
 *
 * @param props - The tasks to render and the MCP server names to label them with.
 */
export function WorkflowTaskGraph({
  tasks,
  serverNameById = EMPTY_SERVER_NAMES,
}: WorkflowTaskGraphProps) {
  const t = useT();
  const { theme } = useTheme();
  const { nodes, edges } = useMemo(
    () => buildLayoutedWorkflowGraph(tasks, serverNameById),
    [tasks, serverNameById]
  );

  if (tasks.length === 0) {
    return (
      <div className="flex h-[70vh] items-center justify-center rounded-xl glass-panel text-on-surface-variant text-sm">
        {t("app.noTasksToVisualizeYet")}
      </div>
    );
  }

  return (
    <div className="h-[70vh] overflow-hidden rounded-xl glass-panel">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        colorMode={theme}
        fitView
        fitViewOptions={{ padding: 0.15, maxZoom: 1 }}
        nodesDraggable={false}
        nodesConnectable={false}
        edgesFocusable={false}
        onlyRenderVisibleElements
        proOptions={{ hideAttribution: true }}
        ariaLabelConfig={{
          "controls.ariaLabel": t("graph.controls"),
          "controls.zoomIn.ariaLabel": t("graph.zoomIn"),
          "controls.zoomOut.ariaLabel": t("graph.zoomOut"),
          "controls.fitView.ariaLabel": t("graph.fitView"),
        }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
