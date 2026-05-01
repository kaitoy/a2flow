"use client";

import { useEffect, useState } from "react";
import { listSessions, type SessionInfo } from "@/lib/api";

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
    <div className="flex flex-col w-56 shrink-0 border-r border-gray-200 bg-gray-50 h-full">
      <div className="shrink-0 px-3 py-3 border-b border-gray-200">
        <button
          type="button"
          onClick={onNew}
          disabled={disabled}
          className="w-full rounded-md bg-gray-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-gray-700 disabled:opacity-50"
        >
          + New session
        </button>
      </div>
      <div className="flex-1 overflow-y-auto py-2">
        {loading && sessions.length === 0 && <p className="px-3 text-xs text-gray-400">Loading…</p>}
        {!loading && sessions.length === 0 && (
          <p className="px-3 text-xs text-gray-400">No sessions</p>
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
                  ? "bg-gray-200 text-gray-900 font-medium"
                  : "text-gray-600 hover:bg-gray-100"
              } disabled:cursor-default`}
            >
              <span className="block truncate font-mono text-[10px] text-gray-400">
                {s.session_id.slice(0, 8)}…
              </span>
              <span className="block">{label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
