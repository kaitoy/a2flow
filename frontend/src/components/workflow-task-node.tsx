"use client";

import { Handle, type NodeProps, Position } from "@xyflow/react";
import {
  TASK_DEP_SOURCE_HANDLE,
  TASK_DEP_TARGET_HANDLE,
  TASK_SKIP_SOURCE_HANDLE,
  TASK_SKIP_TARGET_HANDLE,
  TASK_TOOLS_SOURCE_HANDLE,
  type WorkflowTaskFlowNode,
} from "@/lib/workflow-graph";
import { formatStatusLabel, STATUS_DOT_CLASS } from "@/lib/workflow-task-status";

/**
 * Custom React Flow node rendering a single workflow task as a glass panel with
 * its ordinal within the column, title, and — for status-ful session tasks — a
 * colored status dot; task templates carry no status, so the dot row is
 * omitted.
 *
 * Handles wire the node into the two axes of the graph. A dependency between
 * neighbouring rows of the column flows in from the top and out of the bottom;
 * one that skips rows uses the pair of left handles instead, so it bows out
 * beside the column rather than disappearing behind the tasks it passes. The
 * task's MCP servers hang off the right. Every handle is explicitly identified
 * because the node has several handles per type, and React Flow matches edges
 * to handles by id.
 *
 * @param props - React Flow node props carrying the task in `data.task`.
 */
export function WorkflowTaskNode({ data }: NodeProps<WorkflowTaskFlowNode>) {
  const { task, columnIndex } = data;
  const status = task.status ?? null;

  return (
    <div className="glass-panel w-[220px] rounded-lg px-3 py-2 text-on-surface shadow-sm">
      <Handle
        type="target"
        id={TASK_DEP_TARGET_HANDLE}
        position={Position.Top}
        className="!bg-on-surface-variant"
      />
      <Handle
        type="target"
        id={TASK_SKIP_TARGET_HANDLE}
        position={Position.Left}
        className="!top-[30%] !bg-on-surface-variant"
      />
      <Handle
        type="source"
        id={TASK_SKIP_SOURCE_HANDLE}
        position={Position.Left}
        className="!top-[70%] !bg-on-surface-variant"
      />
      <div className="flex items-start gap-2">
        <span className="mt-1 inline-block w-5 shrink-0 font-mono text-xs text-on-surface-variant">
          #{columnIndex + 1}
        </span>
        <span className="line-clamp-2 flex-1 font-medium text-sm leading-snug">{task.title}</span>
      </div>
      {status !== null && (
        <div className="mt-1.5 flex items-center gap-1.5 pl-7">
          <span
            className={`inline-block size-2 rounded-full ${STATUS_DOT_CLASS[status]}`}
            aria-hidden
          />
          <span className="text-on-surface-variant text-xs">{formatStatusLabel(status)}</span>
        </div>
      )}
      <Handle
        type="source"
        id={TASK_DEP_SOURCE_HANDLE}
        position={Position.Bottom}
        className="!bg-on-surface-variant"
      />
      <Handle
        type="source"
        id={TASK_TOOLS_SOURCE_HANDLE}
        position={Position.Right}
        className="!bg-on-surface-variant"
      />
    </div>
  );
}
