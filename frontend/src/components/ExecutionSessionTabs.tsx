"use client";

import { SegmentedControl } from "@/components/ui/segmented-control";
import type { ExecutionSession } from "@/lib/api";

/** How each session status reads in a tab. */
const STATUS_LABEL: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  waiting_for_input: "Waiting for input",
  waiting_for_approval: "Waiting for approval",
  idle: "Idle",
  done: "Done",
  error: "Error",
};

/** Props for {@link ExecutionSessionTabs}. */
export interface ExecutionSessionTabsProps {
  /** The run's sessions, main session first (as the API lists them). */
  sessions: ExecutionSession[];
  /** The run's main session id (`WorkflowExecution.sessionId`). */
  mainSessionId: string;
  /** The session being shown. */
  value: string;
  /** Called with a session id when the viewer switches to it. */
  onChange: (sessionId: string) => void;
}

/**
 * Switches the workflow session view between the ADK sessions a run is worked
 * in: the main session, and the branch sessions forked when its task graph
 * branched, each with its status — so a viewer can see which branch is waiting
 * on them and open it to answer.
 *
 * Renders nothing while the run has only its main session: there is nothing to
 * switch between, and most runs never branch.
 */
export function ExecutionSessionTabs({
  sessions,
  mainSessionId,
  value,
  onChange,
}: ExecutionSessionTabsProps) {
  if (sessions.length < 2) return null;
  let branch = 0;
  const options = sessions.map((session) => {
    const name = session.id === mainSessionId ? "Main" : `Branch ${++branch}`;
    const status = STATUS_LABEL[session.status ?? ""] ?? session.status ?? "";
    return { value: session.id ?? "", label: status ? `${name} · ${status}` : name };
  });
  return (
    <SegmentedControl
      aria-label="Sessions of this run"
      options={options}
      value={value}
      onChange={onChange}
      className="mt-2 max-w-full overflow-x-auto"
    />
  );
}
