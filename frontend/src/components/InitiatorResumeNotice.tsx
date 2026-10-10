/** @module InitiatorResumeNotice — the bar a workflow session shows while it waits for its initiator. */
import { Hand } from "lucide-react";
import { Button } from "@/components/ui/button";

/** What the initiator's resume button sends; the turn it starts may begin the held task. */
export const RESUME_MESSAGE = "I'm here — resume the workflow.";

/** Props for {@link InitiatorResumeNotice}. */
export interface InitiatorResumeNoticeProps {
  /** Title of the task held back for the initiator, if it is known yet. */
  taskTitle: string | null;
  /** Whether the viewer is the run's initiator — the only one who may resume it. */
  canResume: boolean;
  /** Sends a chat message on the viewer's behalf. */
  onSend: (text: string) => void;
}

/**
 * Notice above the chat input of a session that is `waiting_for_initiator`.
 *
 * Its next task binds a tool that asks the run's initiator questions while it
 * runs, so the server holds the task back until the initiator is in the chat.
 * The initiator gets a **Resume** button, which sends an ordinary chat message:
 * a turn the initiator drove is what lets the task start, and its questions then
 * appear right here. Anyone else viewing the run only sees what it waits for.
 * The page hides the notice while a turn runs, so a pressed button goes away.
 */
export function InitiatorResumeNotice({
  taskTitle,
  canResume,
  onSend,
}: InitiatorResumeNoticeProps) {
  const task = taskTitle ? `“${taskTitle}”` : "The next task";
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-3 rounded-xl glass-panel px-4 py-3 text-sm text-on-surface animate-message-in"
      role="status"
    >
      <span className="flex items-start gap-2">
        <Hand className="mt-0.5 size-4 shrink-0 text-accent" aria-hidden="true" />
        <span>
          {canResume
            ? `${task} will ask you questions while it runs. Resume when you are ready to answer them.`
            : `${task} is waiting for the person who started this run to resume it.`}
        </span>
      </span>
      {canResume && <Button onClick={() => onSend(RESUME_MESSAGE)}>Resume</Button>}
    </div>
  );
}
