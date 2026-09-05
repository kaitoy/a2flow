/** @module TaskToolsDialog — modal listing a task's bound MCP tools and their servers. */
import { animated, useTransition } from "@react-spring/web";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { useDialogA11y } from "@/hooks/useDialogA11y";
import type { ToolBinding } from "@/lib/api";
import { useMotionConfig } from "@/lib/motion";

/** Props for {@link TaskToolsDialog}. */
export interface TaskToolsDialogProps {
  /** The task whose bound tools are listed; `null` closes the dialog. */
  task: { title: string; toolBindings: ToolBinding[] } | null;
  /** Registered MCP server names by id, used to label each binding's server. */
  serverNames: Map<string, string>;
  /** Whether {@link serverNames} is still loading (only true on the first open). */
  serverNamesLoading: boolean;
  /** Called when the dialog requests to close (backdrop, Escape, or Close button). */
  onClose: () => void;
}

/**
 * Modal dialog listing the MCP tools bound to a task, and each tool's owning
 * server.
 *
 * A tool the workflow's design exempted from input approval is labelled as
 * such: it is the one thing about a binding that a reader cannot infer from the
 * tool's name, and it changes what an approval covering the task bounds.
 */
export function TaskToolsDialog({
  task,
  serverNames,
  serverNamesLoading,
  onClose,
}: TaskToolsDialogProps) {
  const open = task !== null;
  const config = useMotionConfig("gentle");
  const transitions = useTransition(open, {
    from: { opacity: 0, scale: 0.94 },
    enter: { opacity: 1, scale: 1 },
    leave: { opacity: 0, scale: 0.96 },
    config,
  });

  useDialogA11y({ open, onClose, panelId: "task-tools-dialog", closeOnOutsideClick: false });

  // Guard against SSR — createPortal needs document.body, which is not
  // available during Next.js prerendering.
  if (typeof document === "undefined") return null;

  return createPortal(
    transitions(
      (style, item) =>
        item &&
        task && (
          <div className="fixed inset-0 z-50">
            <animated.button
              type="button"
              style={{ opacity: style.opacity }}
              className="absolute inset-0 bg-black/25 backdrop-blur-[2px] cursor-default"
              onClick={onClose}
              // Stop the backdrop itself from taking focus on click, so the
              // a11y hook's close handler always restores focus to the
              // trigger instead of leaving it on this transient scrim.
              onMouseDown={(e) => e.preventDefault()}
              tabIndex={-1}
              aria-hidden="true"
            />
            <div className="relative flex items-center justify-center min-h-full p-4 pointer-events-none">
              <animated.div
                id="task-tools-dialog"
                tabIndex={-1}
                role="dialog"
                aria-modal="true"
                aria-labelledby="task-tools-dialog-title"
                style={{
                  opacity: style.opacity,
                  transform: style.scale.to((s) => `scale(${s})`),
                }}
                className="glass-panel-overlay rounded-2xl p-6 max-w-sm w-full pointer-events-auto"
              >
                <h2
                  id="task-tools-dialog-title"
                  className="mb-1 font-display text-lg font-semibold tracking-tight text-on-surface"
                >
                  Bound tools
                </h2>
                <p className="mb-4 truncate text-sm text-on-surface-variant">{task.title}</p>
                <ul className="flex flex-col gap-2">
                  {task.toolBindings.map((binding) => (
                    <li
                      key={`${binding.mcpServerId}::${binding.toolName}`}
                      className="rounded-xl glass-panel p-3"
                    >
                      <p className="truncate font-mono text-sm text-on-surface">
                        {binding.toolName}
                      </p>
                      <p className="mt-0.5 truncate text-xs text-on-surface-variant">
                        {serverNamesLoading
                          ? "Loading server…"
                          : (serverNames.get(binding.mcpServerId) ?? "Unknown server")}
                      </p>
                      {binding.requiresInputApproval === false && (
                        <p className="mt-0.5 text-xs text-on-surface-variant">
                          Input needs no approval
                        </p>
                      )}
                    </li>
                  ))}
                </ul>
                <div className="mt-4 flex justify-end">
                  <Button variant="ghost" onClick={onClose}>
                    Close
                  </Button>
                </div>
              </animated.div>
            </div>
          </div>
        )
    ),
    document.body
  );
}
