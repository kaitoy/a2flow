"use client";

import { SegmentedControl } from "@/components/ui/segmented-control";
import type { MessageKey } from "@/i18n/messages/en";
import { useT } from "@/i18n/provider";
import type { Translator } from "@/i18n/translate";
import type { ExecutionSession } from "@/lib/api";

/** How each session status reads in a tab. */
const STATUS_LABEL: Record<string, MessageKey> = {
  queued: "session.status.queued",
  running: "session.status.running",
  waiting_for_input: "session.status.waiting_for_input",
  waiting_for_approval: "session.status.waiting_for_approval",
  waiting_for_initiator: "session.status.waiting_for_initiator",
  scheduled: "session.status.scheduled",
  idle: "session.status.idle",
  done: "session.status.done",
  error: "session.status.error",
};

/** A session's status as its tab reads it, with the resume time of a scheduled one. */
function statusLabel(session: ExecutionSession, t: Translator): string {
  const key = STATUS_LABEL[session.status ?? ""];
  const label = key ? t(key) : (session.status ?? "");
  if (session.status !== "scheduled" || !session.resumeAt) return label;
  const at = new Date(session.resumeAt).toLocaleString(t.locale, {
    dateStyle: "short",
    timeStyle: "short",
  });
  return t("session.statusUntil", { status: label, at });
}

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
 * in: the main session, the branch sessions forked when its task graph
 * branched, and the consultations opened to ask questions while a session waited
 * on an approval, each with its status — so a viewer can see which branch is
 * waiting on them and open it to answer.
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
  const t = useT();
  if (sessions.length < 2) return null;
  let branch = 0;
  let consultation = 0;
  const options = sessions.map((session) => {
    const name =
      session.id === mainSessionId
        ? t("session.main")
        : session.kind === "consultation"
          ? t("app.consultationValue", { value: ++consultation })
          : t("app.branchValue", { value: ++branch });
    const status = statusLabel(session, t);
    return { value: session.id ?? "", label: status ? `${name} · ${status}` : name };
  });
  return (
    <SegmentedControl
      aria-label={t("app.sessionsOfThisRun")}
      options={options}
      value={value}
      onChange={onChange}
      className="mt-2 max-w-full overflow-x-auto"
    />
  );
}
