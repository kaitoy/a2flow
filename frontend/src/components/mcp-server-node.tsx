"use client";

import { Handle, type NodeProps, Position } from "@xyflow/react";
import { Server } from "lucide-react";
import {
  BRANCH_SOURCE_HANDLE,
  BRANCH_TARGET_HANDLE,
  type McpServerFlowNode,
} from "@/lib/workflow-graph";

/**
 * Custom React Flow node rendering one MCP server in a task's tool branch. It
 * sits between the task node on its left and that task's bound tools on its
 * right, and shows the server's registered name (or a truncated id when the
 * registry could not be loaded), with the full value in a `title` tooltip since
 * the label is truncated to a fixed width.
 *
 * The height is pinned with a utility class matching `SERVER_NODE_HEIGHT`: the
 * branch layout stacks these rows with no slack, so a CSS/constant mismatch
 * would compound down the column.
 *
 * @param props - React Flow node props carrying the server in `data`.
 */
export function McpServerNode({ data }: NodeProps<McpServerFlowNode>) {
  const { serverName } = data;

  return (
    <div className="glass-panel flex h-9 w-[176px] items-center gap-1.5 rounded-lg px-2.5 text-on-surface shadow-sm">
      <Handle
        type="target"
        id={BRANCH_TARGET_HANDLE}
        position={Position.Left}
        className="!bg-on-surface-variant"
      />
      <Server
        size={14}
        strokeWidth={1.8}
        aria-hidden="true"
        className="shrink-0 text-on-surface-variant"
      />
      <span className="truncate font-medium text-xs" title={serverName}>
        {serverName}
      </span>
      <Handle
        type="source"
        id={BRANCH_SOURCE_HANDLE}
        position={Position.Right}
        className="!bg-on-surface-variant"
      />
    </div>
  );
}
