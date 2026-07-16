"use client";

import { Background, BackgroundVariant, Controls, type NodeTypes, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import { buildLayoutedWorkflowGraph, type GraphTask } from "@/lib/workflow-graph";
import { useTheme } from "./ThemeProvider";
import { WorkflowTaskNode } from "./workflow-task-node";

/** Maps the custom node `type` string to its renderer. Defined once outside the
 * component so React Flow does not warn about a new object on every render. */
const NODE_TYPES: NodeTypes = { workflowTask: WorkflowTaskNode };

/** Props for {@link WorkflowTaskGraph}. */
export interface WorkflowTaskGraphProps {
  /** Tasks of a single workflow session (or a plan's templates) to visualize as a DAG. */
  tasks: GraphTask[];
}

/**
 * Read-only React Flow visualization of a workflow session's task DAG.
 *
 * Nodes are laid out top-to-bottom with dagre so that dependencies sit above
 * the tasks that depend on them. Users can pan, zoom, and nudge nodes, but
 * cannot create or remove dependency edges — editing happens on the task forms.
 *
 * @param props - The tasks to render.
 */
export function WorkflowTaskGraph({ tasks }: WorkflowTaskGraphProps) {
  const { theme } = useTheme();
  const { nodes, edges } = useMemo(() => buildLayoutedWorkflowGraph(tasks), [tasks]);

  if (tasks.length === 0) {
    return (
      <div className="flex h-[70vh] items-center justify-center rounded-xl glass-panel text-on-surface-variant text-sm">
        No tasks to visualize yet.
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
        nodesConnectable={false}
        edgesFocusable={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}
