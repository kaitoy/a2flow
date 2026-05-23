"use client";

import { useEffect, useState } from "react";
import { deleteSession, listSessions, type Session } from "@/lib/api";
import { Button } from "./ui/button";
import { ConfirmDialog } from "./ui/confirm-dialog";

interface SessionListProps {
  userId: string;
  currentSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onNew: () => void;
  onDeleted?: (sessionId: string) => void;
  disabled?: boolean;
}

/** Sidebar listing past sessions with controls to create a new session or delete an existing one. */
export function SessionList({
  userId,
  currentSessionId,
  onSelect,
  onNew,
  onDeleted,
  disabled,
}: SessionListProps) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(false);
  const [confirmTarget, setConfirmTarget] = useState<{ id: string } | null>(null);

  useEffect(() => {
    setLoading(true);
    listSessions(userId)
      .then((list) =>
        setSessions(
          [...list].sort((a, b) => Date.parse(b.lastUpdateTime) - Date.parse(a.lastUpdateTime))
        )
      )
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, [userId]);

  async function executeDelete() {
    if (!confirmTarget) return;
    const targetId = confirmTarget.id;
    try {
      await deleteSession(targetId, userId);
      setSessions((prev) => prev.filter((s) => s.id !== targetId));
      if (targetId === currentSessionId) {
        onDeleted?.(targetId);
      }
    } catch {
      // Swallow — sidebar has no error UI surface; user can retry.
    } finally {
      setConfirmTarget(null);
    }
  }

  return (
    <aside className="relative flex h-full w-64 shrink-0 flex-col border-r border-glass-border bg-glass backdrop-blur-xl">
      <div className="shrink-0 px-3 py-4 border-b border-glass-border">
        <Button variant="primary" onClick={onNew} disabled={disabled} className="w-full">
          + New session
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {loading && sessions.length === 0 && (
          <p className="px-3 text-xs text-on-surface-variant">Loading…</p>
        )}
        {!loading && sessions.length === 0 && (
          <p className="px-3 text-xs text-on-surface-variant">No sessions</p>
        )}
        {sessions.map((s) => {
          const isActive = s.id === currentSessionId;
          const date = new Date(s.lastUpdateTime);
          const label = date.toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          });
          return (
            <div
              key={s.id}
              className={[
                "group relative mx-2 my-0.5 flex w-[calc(100%-1rem)] items-stretch rounded-xl",
                "transition-all duration-150",
                isActive
                  ? "bg-accent-soft text-on-surface shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]"
                  : "text-on-surface-variant hover:bg-glass hover:text-on-surface",
              ].join(" ")}
            >
              {isActive && (
                <span
                  aria-hidden="true"
                  className="absolute left-0 top-1/2 h-2/3 w-[3px] -translate-y-1/2 rounded-r-full bg-accent shadow-glow"
                />
              )}
              <button
                type="button"
                onClick={() => !isActive && onSelect(s.id)}
                disabled={disabled || isActive}
                title={s.id}
                className="flex min-w-0 flex-1 flex-col gap-0.5 rounded-xl px-3 py-2 text-left text-xs disabled:cursor-default"
              >
                <span className="block truncate font-mono text-[10px] uppercase tracking-wider opacity-60">
                  {s.id.slice(0, 8)}…
                </span>
                <span className="block truncate text-[12px] font-medium text-on-surface">
                  {label}
                </span>
              </button>
              <button
                type="button"
                aria-label="Delete session"
                onClick={() => setConfirmTarget({ id: s.id })}
                disabled={disabled}
                className={[
                  "mr-1 my-1 flex w-7 shrink-0 items-center justify-center rounded-lg",
                  "text-on-surface-variant opacity-0 transition-all duration-150",
                  "group-hover:opacity-100 hover:bg-error/10 hover:text-error",
                  "focus-visible:opacity-100 disabled:cursor-default disabled:hover:bg-transparent disabled:hover:text-on-surface-variant",
                ].join(" ")}
              >
                <span aria-hidden="true" className="text-[14px] leading-none">
                  ✕
                </span>
              </button>
            </div>
          );
        })}
      </div>
      <ConfirmDialog
        open={confirmTarget !== null}
        title="Delete session?"
        description="This session and its messages will be permanently deleted."
        onConfirm={executeDelete}
        onCancel={() => setConfirmTarget(null)}
      />
    </aside>
  );
}
