/** @module workflow-execution-status — the shared status readout for a WorkflowExecution. */
import { StatusDot } from "@/components/ui/status-dot";
import type { WorkflowExecutionStatus as WorkflowExecutionStatusValue } from "@/lib/api";

/**
 * Tailwind background-color class for the status dot of each lifecycle state,
 * keyed by the wire value.
 *
 * Mirrors the palette convention shared with `lib/workflow-status.ts` and
 * `lib/workflow-task-status.ts`: accent for an in-progress state, green for a
 * successful terminal state, red for a failed one.
 */
const STATUS_DOT_CLASS: Record<WorkflowExecutionStatusValue, string> = {
  running: "bg-accent",
  completed: "bg-success/80",
  failed: "bg-error",
};

/**
 * Render a workflow execution's status as a colour-coded dot beside its name.
 *
 * Shared by the workflow-executions list and detail pages, mirroring
 * `ApprovalStatusLabel`.
 *
 * @param status - The execution's status; `undefined` reads as `running`, the
 *   state an execution starts in (unlike an approval, a run has no `pending`
 *   state — it is already under way once it exists).
 */
export function WorkflowExecutionStatusLabel({
  status,
}: {
  status?: WorkflowExecutionStatusValue | null;
}) {
  const value = status ?? "running";
  return <StatusDot dotClass={STATUS_DOT_CLASS[value]} label={value} />;
}
