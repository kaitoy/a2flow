"use client";

import { animated, useTransition } from "@react-spring/web";
import { useEffect, useRef, useState } from "react";
import { deleteSession, getSession, listSessions, type Session } from "@/lib/api";
import { useMotionConfig } from "@/lib/motion";
import { useAppSelector } from "@/store/hooks";
import { Button } from "./ui/button";
import { ConfirmDialog } from "./ui/confirm-dialog";
import { Skeleton } from "./ui/skeleton";
import { SlidingIndicator } from "./ui/sliding-indicator";
import { Tooltip } from "./ui/tooltip";

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
  const reduxSessionId = useAppSelector((s) => s.chat.sessionId);
  const isStreaming = useAppSelector((s) => s.chat.isStreaming);

  const itemMap = useRef<Map<string, HTMLElement | null>>(new Map());

  const config = useMotionConfig("gentle");
  const transitions = useTransition(sessions, {
    keys: (s) => s.id,
    from: { opacity: 0, transform: "translateX(-12px)" },
    enter: { opacity: 1, transform: "translateX(0px)" },
    leave: { opacity: 0, transform: "translateX(-24px)" },
    trail: 40,
    config,
  });

  // biome-ignore lint/correctness/useExhaustiveDependencies: re-fetch when the active user changes
  useEffect(() => {
    setLoading(true);
    listSessions()
      .then((list) =>
        setSessions(
          [...list].sort((a, b) => Date.parse(b.lastUpdateTime) - Date.parse(a.lastUpdateTime))
        )
      )
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, [userId]);

  useEffect(() => {
    if (!reduxSessionId || !isStreaming) return;
    getSession(reduxSessionId)
      .then((session) =>
        setSessions((prev) => {
          if (prev.some((s) => s.id === session.id)) return prev;
          return [session, ...prev].sort(
            (a, b) => Date.parse(b.lastUpdateTime) - Date.parse(a.lastUpdateTime)
          );
        })
      )
      .catch(() => {});
  }, [reduxSessionId, isStreaming]);

  async function executeDelete() {
    if (!confirmTarget) return;
    const targetId = confirmTarget.id;
    try {
      await deleteSession(targetId);
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
      <div className="relative flex-1 overflow-y-auto py-2">
        {loading && sessions.length === 0 && (
          <div role="status" aria-label="Loading" className="flex flex-col">
            {Array.from({ length: 5 }, (_, i) => (
              <div
                // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length placeholder list with no identity
                key={i}
                className="mx-2 my-0.5 flex w-[calc(100%-1rem)] flex-col gap-1 rounded-xl px-3 py-2"
              >
                <Skeleton className="h-2 w-16" />
                <Skeleton className="h-3 w-28" />
              </div>
            ))}
          </div>
        )}
        {!loading && sessions.length === 0 && (
          <p className="px-3 text-xs text-on-surface-variant">No sessions</p>
        )}
        {transitions((style, s) => {
          const isActive = s.id === currentSessionId;
          const date = new Date(s.lastUpdateTime);
          const label = date.toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          });
          return (
            <animated.div
              ref={(el: HTMLDivElement | null) => {
                if (el) itemMap.current.set(s.id, el);
                else itemMap.current.delete(s.id);
              }}
              style={style}
              className={[
                "group relative mx-2 my-0.5 flex w-[calc(100%-1rem)] items-stretch rounded-xl",
                "transition-[background-color,color,box-shadow] duration-[var(--motion-duration-base)] ease-[var(--motion-ease-standard)]",
                isActive
                  ? "bg-accent-soft text-on-surface shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]"
                  : "text-on-surface-variant hover:bg-glass hover:text-on-surface",
              ].join(" ")}
            >
              <Tooltip label={s.id} placement="right">
                <button
                  type="button"
                  onClick={() => !isActive && onSelect(s.id)}
                  disabled={disabled || isActive}
                  className="flex min-w-0 flex-1 flex-col gap-0.5 rounded-xl px-3 py-2 text-left text-xs disabled:cursor-default"
                >
                  <span className="block truncate font-mono text-[10px] uppercase tracking-wider opacity-60">
                    {s.id.slice(0, 8)}…
                  </span>
                  <span className="block truncate text-[12px] font-medium text-on-surface">
                    {label}
                  </span>
                </button>
              </Tooltip>
              <button
                type="button"
                aria-label="Delete session"
                onClick={() => setConfirmTarget({ id: s.id })}
                disabled={disabled}
                className={[
                  "mr-1 my-1 flex w-7 shrink-0 items-center justify-center rounded-lg",
                  "text-on-surface-variant opacity-0",
                  "transition-[opacity,background-color,color,transform,translate,scale] duration-[var(--motion-duration-fast)] ease-[var(--motion-ease-standard)]",
                  "group-hover:opacity-100 hover:bg-error/10 hover:text-error motion-safe:hover:scale-110",
                  "focus-visible:opacity-100 disabled:cursor-default disabled:hover:bg-transparent disabled:hover:text-on-surface-variant",
                ].join(" ")}
              >
                <span aria-hidden="true" className="text-[14px] leading-none">
                  ✕
                </span>
              </button>
            </animated.div>
          );
        })}
        <SlidingIndicator
          itemMap={itemMap}
          activeKey={currentSessionId}
          deps={[sessions, currentSessionId]}
        />
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
