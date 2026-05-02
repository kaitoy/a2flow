"use client";

import { useEffect, useState } from "react";
import { listSessions, type SessionInfo } from "@/lib/api";
import { Button } from "./ui/button";

interface SessionListProps {
  userId: string;
  currentSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onNew: () => void;
  disabled?: boolean;
}

export function SessionList({
  userId,
  currentSessionId,
  onSelect,
  onNew,
  disabled,
}: SessionListProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    listSessions(userId)
      .then((list) =>
        setSessions([...list].sort((a, b) => b.last_update_time - a.last_update_time))
      )
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, [userId]);

  return (
    <div className="flex flex-col w-60 shrink-0 border-r border-outline-variant bg-surface-container-low h-full">
      <div className="shrink-0 px-3 py-3 border-b border-outline-variant">
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
          const isActive = s.session_id === currentSessionId;
          const date = new Date(s.last_update_time * 1000);
          const label = date.toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "2-digit",
            minute: "2-digit",
          });
          return (
            <button
              type="button"
              key={s.session_id}
              onClick={() => !isActive && onSelect(s.session_id)}
              disabled={disabled || isActive}
              title={s.session_id}
              className={`w-full text-left px-3 py-2 text-xs truncate ${
                isActive
                  ? "bg-primary-container text-on-primary-container font-medium"
                  : "text-on-surface-variant hover:bg-surface-container"
              } disabled:cursor-default`}
            >
              <span className="block truncate font-mono text-[10px] text-on-surface-variant/60">
                {s.session_id.slice(0, 8)}…
              </span>
              <span className="block text-on-surface">{label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
