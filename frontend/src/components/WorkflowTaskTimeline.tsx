"use client";

import { ChevronLeft, ListTree } from "lucide-react";
import type { WorkflowTask } from "@/lib/api";
import { formatStatusLabel, STATUS_DOT_CLASS } from "@/lib/workflow-task-status";

/**
 * Props for {@link WorkflowTaskTimeline}.
 */
export interface WorkflowTaskTimelineProps {
  /** The session's workflow tasks, in position order. */
  tasks: WorkflowTask[];
  /** Id of the task currently in progress, highlighted in the list. */
  activeTaskId: string | null;
  /** Called with a task id when its entry is clicked (to scroll the chat to it). */
  onSelectTask: (taskId: string) => void;
  /** Whether the panel is collapsed to a thin toggle bar. */
  collapsed: boolean;
  /** Toggles the collapsed state. */
  onToggle: () => void;
}

/**
 * Collapsible left-hand timeline of a workflow session's tasks. Each entry shows
 * the task's status dot and title, highlights the in-progress task, and scrolls
 * the chat to the matching {@link WorkflowTaskDivider} when clicked.
 */
export function WorkflowTaskTimeline({
  tasks,
  activeTaskId,
  onSelectTask,
  collapsed,
  onToggle,
}: WorkflowTaskTimelineProps) {
  if (collapsed) {
    return (
      <div className="flex w-12 shrink-0 flex-col items-center border-r border-glass-border bg-glass py-3 backdrop-blur-xl">
        <button
          type="button"
          onClick={onToggle}
          aria-label="Show task timeline"
          aria-expanded={false}
          className="rounded-lg p-2 text-on-surface-variant transition-colors hover:bg-glass hover:text-on-surface"
        >
          <ListTree size={18} strokeWidth={1.8} aria-hidden="true" />
        </button>
      </div>
    );
  }

  return (
    <aside className="flex w-[260px] shrink-0 flex-col border-r border-glass-border bg-glass backdrop-blur-xl">
      <div className="flex items-center justify-between px-4 py-3">
        <h2 className="text-xs font-semibold uppercase tracking-wide text-on-surface-variant">
          Tasks
        </h2>
        <button
          type="button"
          onClick={onToggle}
          aria-label="Hide task timeline"
          aria-expanded={true}
          className="rounded-lg p-1.5 text-on-surface-variant transition-colors hover:bg-glass hover:text-on-surface"
        >
          <ChevronLeft size={16} strokeWidth={1.8} aria-hidden="true" />
        </button>
      </div>
      <ol className="relative flex-1 overflow-y-auto px-3 pb-4">
        {tasks.length === 0 ? (
          <li className="px-2 py-3 text-sm text-on-surface-variant">No tasks yet.</li>
        ) : (
          tasks.map((task, i) => {
            const status = task.status ?? "pending";
            const isActive = task.id === activeTaskId;
            return (
              <li key={task.id} className="relative">
                {i < tasks.length - 1 && (
                  <span
                    aria-hidden="true"
                    className="absolute bottom-0 left-[0.8rem] top-[1.9rem] w-px bg-glass-border"
                  />
                )}
                <button
                  type="button"
                  onClick={() => onSelectTask(task.id)}
                  aria-current={isActive ? "true" : undefined}
                  className={`relative flex w-full items-start gap-2.5 rounded-xl px-2 py-2 text-left transition-colors ${
                    isActive
                      ? "bg-accent-soft text-on-surface"
                      : "text-on-surface-variant hover:bg-glass hover:text-on-surface"
                  }`}
                >
                  <span
                    className={`mt-1 inline-block size-2.5 shrink-0 rounded-full ${STATUS_DOT_CLASS[status]} ${
                      isActive ? "shadow-glow" : ""
                    }`}
                    aria-hidden="true"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium leading-snug">
                      {task.title}
                    </span>
                    <span className="block text-xs text-on-surface-variant">
                      {formatStatusLabel(status)}
                    </span>
                  </span>
                </button>
              </li>
            );
          })
        )}
      </ol>
    </aside>
  );
}
