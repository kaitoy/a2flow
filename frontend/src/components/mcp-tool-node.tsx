"use client";

import { Handle, type NodeProps, Position } from "@xyflow/react";
import { Wrench } from "lucide-react";
import { BRANCH_TARGET_HANDLE, type McpToolFlowNode } from "@/lib/workflow-graph";

/**
 * Custom React Flow node rendering one MCP tool bound to a task, at the right
 * end of that task's branch. Tool names are shown in the mono data face — the
 * same treatment they get in {@link TaskToolsDialog} and the MCP server tools
 * panel — and truncated to a fixed width, with the full name in a `title`
 * tooltip since real tool names run long.
 *
 * The height is pinned with a utility class matching `TOOL_NODE_HEIGHT`,
 * because the branch layout stacks these rows at exact offsets.
 *
 * @param props - React Flow node props carrying the tool in `data`.
 */
export function McpToolNode({ data }: NodeProps<McpToolFlowNode>) {
  const { toolName } = data;

  return (
    <div className="glass-panel flex h-9 w-[200px] items-center gap-1.5 rounded-lg px-2.5 shadow-sm">
      <Handle
        type="target"
        id={BRANCH_TARGET_HANDLE}
        position={Position.Left}
        className="!bg-on-surface-variant"
      />
      <Wrench
        size={12}
        strokeWidth={1.8}
        aria-hidden="true"
        className="shrink-0 text-on-surface-variant"
      />
      <span className="truncate font-mono text-on-surface-variant text-xs" title={toolName}>
        {toolName}
      </span>
    </div>
  );
}
