"use client";

import { ChevronLeft, ListTree } from "lucide-react";
import type { WorkflowTask } from "@/lib/api";
import { formatStatusLabel, STATUS_RAIL_CLASS } from "@/lib/workflow-task-status";

/** Expanded panel's outer `aside` class, shared with {@link WorkflowSessionSkeleton} so its loading chrome can't drift from the real sidebar. */
export const TASK_TIMELINE_ASIDE_CLASS =
  "flex w-64 shrink-0 flex-col border-r border-glass-border glass-chrome";

/** Expanded panel's header row class, shared with {@link WorkflowSessionSkeleton}. */
export const TASK_TIMELINE_HEADER_CLASS = "flex items-center justify-between px-4 py-3";

/** Expanded panel's task-list class, shared with {@link WorkflowSessionSkeleton}. */
export const TASK_TIMELINE_LIST_CLASS = "relative flex-1 overflow-y-auto px-3 pb-4";

/**
 * Props for {@link WorkflowTaskTimeline}.
 */
export interface WorkflowTaskTimelineProps {
  /** The session's workflow tasks, in position order. */
  tasks: WorkflowTask[];
  /** Id of the task currently in progress, highlighted in the list. */
  activeTaskId: string | null;
  /**
   * Optional WorkflowTask id -> 1-based ordinal shown in each entry's badge,
   * shared with the chat groups. Falls back to the list order when omitted.
   */
  taskIndexById?: Map<string, number>;
  /** Id of the focused task (chat hover / scroll-spy), shown with a ring. */
  highlightedTaskId?: string | null;
  /** Called with a task id when its entry is clicked (to scroll the chat to it). */
  onSelectTask: (taskId: string) => void;
  /** Called with a task id on hover and `null` on leave, to drive chat linkage. */
  onHoverTask?: (taskId: string | null) => void;
  /** Whether the panel is collapsed to a thin toggle bar. */
  collapsed: boolean;
  /** Toggles the collapsed state. */
  onToggle: () => void;
}

/**
 * Collapsible left-hand timeline of a workflow session's tasks. Each entry shows
 * a numbered status badge and the task's title, highlights the in-progress task,
 * follows the chat's scroll position / hover, and scrolls the chat to the
 * matching {@link WorkflowTaskGroup} when clicked. The badge number matches the
 * chat group's heading so the two views can be paired at a glance.
 */
export function WorkflowTaskTimeline({
  tasks,
  activeTaskId,
  taskIndexById,
  highlightedTaskId = null,
  onSelectTask,
  onHoverTask,
  collapsed,
  onToggle,
}: WorkflowTaskTimelineProps) {
  if (collapsed) {
    return (
      <div className="flex w-12 shrink-0 flex-col items-center border-r border-glass-border glass-chrome py-3">
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
    <aside className={TASK_TIMELINE_ASIDE_CLASS}>
      <div className={TASK_TIMELINE_HEADER_CLASS}>
        <h2 className="text-label-caps">Tasks</h2>
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
      <ol className={TASK_TIMELINE_LIST_CLASS}>
        {tasks.length === 0 ? (
          <li className="px-2 py-3 text-sm text-on-surface-variant">No tasks yet.</li>
        ) : (
          tasks.map((task, i) => {
            const status = task.status ?? "pending";
            const isActive = task.id === activeTaskId;
            const isHighlighted = task.id === highlightedTaskId;
            const index = taskIndexById?.get(task.id) ?? i + 1;
            return (
              <li key={task.id} className="relative">
                {i < tasks.length - 1 && (
                  <span
                    aria-hidden="true"
                    className="absolute bottom-0 left-[1.125rem] top-[1.85rem] w-px bg-glass-border"
                  />
                )}
                <button
                  type="button"
                  onClick={() => onSelectTask(task.id)}
                  onMouseEnter={() => onHoverTask?.(task.id)}
                  onMouseLeave={() => onHoverTask?.(null)}
                  aria-current={isActive ? "true" : undefined}
                  className={`relative flex w-full items-start gap-2.5 rounded-xl px-2 py-2 text-left transition-all ${
                    isActive
                      ? "bg-accent-soft text-on-surface"
                      : isHighlighted
                        ? "bg-glass text-on-surface"
                        : "text-on-surface-variant hover:bg-glass hover:text-on-surface"
                  } ${isHighlighted ? "ring-2 ring-inset ring-accent/50" : ""}`}
                >
                  <span
                    className={`mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full border-2 bg-surface text-[11px] font-semibold leading-none text-on-surface ${STATUS_RAIL_CLASS[status]} ${
                      isActive ? "shadow-glow" : ""
                    }`}
                    aria-hidden="true"
                  >
                    {index}
                  </span>
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
