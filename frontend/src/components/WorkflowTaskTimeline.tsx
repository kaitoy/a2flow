"use client";

import { ChevronLeft, ListTree, Wrench } from "lucide-react";
import { useRef, useState } from "react";
import { TaskToolsDialog } from "@/components/TaskToolsDialog";
import { Tooltip } from "@/components/ui/tooltip";
import { useT } from "@/i18n/provider";
import { listMcpServers, type ToolBinding, type WorkflowTaskStatus } from "@/lib/api";
import { formatStatusLabel, STATUS_RAIL_CLASS } from "@/lib/workflow-task-status";

/** Upper bound used to fetch the whole MCP server registry for the tools dialog's labels. */
const SERVER_LIMIT = 1000;

/**
 * One entry of the timeline: a session's WorkflowTask, or — in a design
 * session — a workflow task template, which has no status (the lifecycle
 * belongs to a run, not the design).
 */
export interface TimelineTask {
  /** Identifier used for selection, hover linkage, and chat-group anchors. */
  id: string;
  /** Title shown as the entry's label. */
  title: string;
  /** Lifecycle status, or absent for status-less entries (task templates). */
  status?: WorkflowTaskStatus | null;
  /** Longer explanation of the task, shown in a hover tooltip when present. */
  description?: string | null;
  /** MCP tools bound to this task/template, shown as a small count indicator when non-empty. */
  toolBindings?: ToolBinding[];
  /**
   * Id of the session working the task, or absent while none is assigned (a
   * task not runnable yet, or a task template). Drives the branch indent and
   * the dimming of other sessions' tasks.
   */
  sessionId?: string | null;
}

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
  /** The session's workflow tasks (or a workflow's task templates), in creation order. */
  tasks: TimelineTask[];
  /** Id of the task currently in progress, highlighted in the list. */
  activeTaskId: string | null;
  /**
   * Optional WorkflowTask id -> 1-based ordinal shown in each entry's badge,
   * shared with the chat groups. Falls back to the list order when omitted.
   */
  taskIndexById?: Map<string, number>;
  /** Id of the focused task (chat hover / scroll-spy), shown with a ring. */
  highlightedTaskId?: string | null;
  /**
   * Branch session id -> the name its tab shows ("Branch 1"). A task worked by
   * one of these sessions is indented off the rail and labelled with the name.
   */
  branchNames?: Map<string, string>;
  /**
   * Id of the session whose chat is on screen. Tasks another session works are
   * dimmed; tasks no session works yet are not.
   */
  viewedSessionId?: string;
  /** Called with a task id when its entry is clicked (to scroll the chat to it). */
  onSelectTask: (taskId: string) => void;
  /** Called with a task id on hover and `null` on leave, to drive chat linkage. */
  onHoverTask?: (taskId: string | null) => void;
  /** Whether the panel is collapsed to a thin toggle bar. */
  collapsed: boolean;
  /** Toggles the collapsed state. */
  onToggle: () => void;
  /** Extra classes for the root element (e.g. `max-md:hidden` for the static desktop sidebar). */
  className?: string;
}

/**
 * Collapsible left-hand timeline of a workflow execution's tasks. Each entry shows
 * a numbered status badge and the task's title, highlights the in-progress task,
 * follows the chat's scroll position / hover, and scrolls the chat to the
 * matching {@link WorkflowTaskGroup} when clicked. The badge number matches the
 * chat group's heading so the two views can be paired at a glance. Hovering a
 * title with a description reveals it in a tooltip beside the panel, clear of
 * the neighbouring entries. Once a run has branched, a
 * task worked by a branch session is indented off the rail on an elbow and
 * labelled with the branch's name, and tasks of sessions other than the one on
 * screen are dimmed. When a task or template
 * has bound MCP tools, a small tool icon and count appear below the
 * title/status; clicking it opens a dialog listing each tool and its owning
 * MCP server.
 */
export function WorkflowTaskTimeline({
  tasks,
  activeTaskId,
  taskIndexById,
  highlightedTaskId = null,
  branchNames,
  viewedSessionId,
  onSelectTask,
  onHoverTask,
  collapsed,
  onToggle,
  className,
}: WorkflowTaskTimelineProps) {
  const t = useT();
  const [openToolsTask, setOpenToolsTask] = useState<TimelineTask | null>(null);
  const [serverNames, setServerNames] = useState<Map<string, string>>(new Map());
  const [serverNamesLoading, setServerNamesLoading] = useState(false);
  const serverNamesFetched = useRef(false);
  const asideRef = useRef<HTMLElement>(null);

  function openToolsDialog(task: TimelineTask) {
    setOpenToolsTask(task);
    if (serverNamesFetched.current) return;
    serverNamesFetched.current = true;
    setServerNamesLoading(true);
    listMcpServers({ limit: SERVER_LIMIT })
      .then((servers) => setServerNames(new Map(servers.map((s) => [s.id, s.name]))))
      .catch(() => {
        // Server names are cosmetic; the dialog falls back to each binding's raw id.
      })
      .finally(() => setServerNamesLoading(false));
  }

  if (collapsed) {
    return (
      <div
        className={`flex w-12 shrink-0 flex-col items-center border-r border-glass-border glass-chrome py-3 ${className ?? ""}`}
      >
        <button
          type="button"
          onClick={onToggle}
          aria-label={t("app.showTaskTimeline")}
          aria-expanded={false}
          className="rounded-lg p-2 pointer-coarse:p-3 text-on-surface-variant transition-colors hover:bg-glass hover:text-on-surface"
        >
          <ListTree size={18} strokeWidth={1.8} aria-hidden="true" />
        </button>
      </div>
    );
  }

  return (
    <aside ref={asideRef} className={`${TASK_TIMELINE_ASIDE_CLASS} ${className ?? ""}`}>
      <div className={TASK_TIMELINE_HEADER_CLASS}>
        <h2 className="text-label">{t("app.tasks")}</h2>
        <button
          type="button"
          onClick={onToggle}
          aria-label={t("app.hideTaskTimeline")}
          aria-expanded={true}
          className="rounded-lg p-1.5 pointer-coarse:p-2.5 text-on-surface-variant transition-colors hover:bg-glass hover:text-on-surface"
        >
          <ChevronLeft size={16} strokeWidth={1.8} aria-hidden="true" />
        </button>
      </div>
      <ol className={TASK_TIMELINE_LIST_CLASS}>
        {tasks.length === 0 ? (
          <li className="px-2 py-3 text-sm text-on-surface-variant">{t("app.noTasksYet")}</li>
        ) : (
          tasks.map((task, i) => {
            const status = task.status ?? null;
            const isActive = task.id === activeTaskId;
            const isHighlighted = task.id === highlightedTaskId;
            const index = taskIndexById?.get(task.id) ?? i + 1;
            const toolBindings = task.toolBindings ?? [];
            const branchName = task.sessionId ? branchNames?.get(task.sessionId) : undefined;
            const isDimmed =
              viewedSessionId !== undefined &&
              task.sessionId != null &&
              task.sessionId !== viewedSessionId;
            return (
              <li
                key={task.id}
                data-branch={branchName ? "true" : undefined}
                className={`relative ${branchName ? "pl-5" : ""}`}
              >
                {/* The rail: from under the badge down to the next entry — or, beside
                    a branch entry, straight past it, since the branch hangs off it. */}
                {i < tasks.length - 1 && (
                  <span
                    aria-hidden="true"
                    className={`absolute bottom-0 left-[1.125rem] w-px bg-glass-border ${
                      branchName ? "top-0" : "top-[1.85rem]"
                    }`}
                  />
                )}
                {/* The elbow from the rail to a branch entry's badge. */}
                {branchName && (
                  <span
                    aria-hidden="true"
                    className="absolute left-[1.125rem] top-0 h-5 w-2.5 rounded-bl-lg border-b border-l border-glass-border"
                  />
                )}
                {/* biome-ignore lint/a11y/noStaticElementInteractions: hover is a non-essential visual link to the chat; the core linkage is click + aria-current */}
                <div
                  onMouseEnter={() => onHoverTask?.(task.id)}
                  onMouseLeave={() => onHoverTask?.(null)}
                  className={`relative flex flex-col items-start rounded-xl px-2 py-2 transition-all ${
                    isActive
                      ? "bg-accent-soft text-on-surface"
                      : isHighlighted
                        ? "bg-glass text-on-surface"
                        : "text-on-surface-variant hover:bg-glass hover:text-on-surface"
                  } ${isHighlighted ? "ring-2 ring-inset ring-accent/50" : ""} ${
                    isDimmed ? "opacity-60 hover:opacity-100 focus-within:opacity-100" : ""
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => onSelectTask(task.id)}
                    aria-current={isActive ? "true" : undefined}
                    data-testid="workflow-task"
                    className="flex w-full items-start gap-2.5 text-left"
                  >
                    <span
                      className={`mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full border-2 bg-surface text-[11px] font-semibold leading-none text-on-surface ${STATUS_RAIL_CLASS[status ?? "pending"]} ${
                        isActive ? "shadow-glow" : ""
                      }`}
                      aria-hidden="true"
                    >
                      {index}
                    </span>
                    <span className="min-w-0 flex-1">
                      <Tooltip
                        label={task.description ?? ""}
                        placement="right"
                        anchorRef={asideRef}
                        disabled={!task.description}
                      >
                        <span className="block truncate text-sm font-medium leading-snug">
                          {task.title}
                        </span>
                      </Tooltip>
                      {(status !== null || branchName) && (
                        <span className="block truncate text-xs text-on-surface-variant">
                          {status !== null && (
                            <span data-testid="workflow-task-status">
                              {formatStatusLabel(status)}
                            </span>
                          )}
                          {status !== null && branchName && " · "}
                          {branchName && (
                            <span data-testid="workflow-task-branch">{branchName}</span>
                          )}
                        </span>
                      )}
                    </span>
                  </button>
                  {toolBindings.length > 0 && (
                    <button
                      type="button"
                      onClick={() => openToolsDialog(task)}
                      aria-label={t("app.boundToolsCount", { count: toolBindings.length })}
                      className="ml-[1.875rem] mt-0.5 inline-flex items-center gap-1 rounded-full glass-panel px-1.5 py-0.5 text-xs text-on-surface-variant transition-all hover:text-accent hover:shadow-glow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
                    >
                      <Wrench size={11} strokeWidth={1.8} aria-hidden="true" />
                      {toolBindings.length}
                    </button>
                  )}
                </div>
              </li>
            );
          })
        )}
      </ol>
      <TaskToolsDialog
        task={
          openToolsTask
            ? { title: openToolsTask.title, toolBindings: openToolsTask.toolBindings ?? [] }
            : null
        }
        serverNames={serverNames}
        serverNamesLoading={serverNamesLoading}
        onClose={() => setOpenToolsTask(null)}
      />
    </aside>
  );
}
