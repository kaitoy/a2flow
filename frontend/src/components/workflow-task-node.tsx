"use client";

import { Handle, type NodeProps, Position } from "@xyflow/react";
import type { WorkflowTaskFlowNode } from "@/lib/workflow-graph";
import { formatStatusLabel, STATUS_DOT_CLASS } from "@/lib/workflow-task-status";

/**
 * Custom React Flow node rendering a single workflow task as a glass panel with
 * its position number, title, and a colored status dot. Left and right handles
 * connect dependency edges (prerequisites flow in from the left, dependents flow
 * out of the right).
 *
 * @param props - React Flow node props carrying the task in `data.task`.
 */
export function WorkflowTaskNode({ data }: NodeProps<WorkflowTaskFlowNode>) {
  const { task } = data;
  const status = task.status ?? "pending";

  return (
    <div className="glass-panel w-[220px] rounded-lg px-3 py-2 text-on-surface shadow-sm">
      <Handle type="target" position={Position.Left} className="!bg-on-surface-variant" />
      <div className="flex items-start gap-2">
        <span className="mt-1 inline-block w-5 shrink-0 font-mono text-xs text-on-surface-variant">
          #{task.position ?? 0}
        </span>
        <span className="line-clamp-2 flex-1 font-medium text-sm leading-snug">{task.title}</span>
      </div>
      <div className="mt-1.5 flex items-center gap-1.5 pl-7">
        <span
          className={`inline-block size-2 rounded-full ${STATUS_DOT_CLASS[status]}`}
          aria-hidden
        />
        <span className="text-on-surface-variant text-xs">{formatStatusLabel(status)}</span>
      </div>
      <Handle type="source" position={Position.Right} className="!bg-on-surface-variant" />
    </div>
  );
}
