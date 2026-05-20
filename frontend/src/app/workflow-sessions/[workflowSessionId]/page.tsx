"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ChatInput } from "@/components/ChatInput";
import { MessageList } from "@/components/MessageList";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useWorkflowSessionChat } from "@/hooks/useWorkflowSessionChat";
import { getWorkflowSession, type WorkflowSession } from "@/lib/api";
import { clearError } from "@/store/chatSlice";
import { useAppDispatch } from "@/store/hooks";

function WorkflowSessionView({ ws }: { ws: WorkflowSession }) {
  const dispatch = useAppDispatch();
  const { messages, isRunning, isStreaming, error, sendMessage } = useWorkflowSessionChat(
    ws.id,
    ws.sessionId,
    ws.workflowPrompt
  );

  return (
    <div className="flex h-screen overflow-hidden">
      <div className="flex flex-col flex-1 min-w-0">
        <header className="shrink-0 flex items-center justify-between px-6 py-3 border-b border-glass-border bg-glass backdrop-blur-xl">
          <div className="flex items-center gap-3">
            <span className="inline-block h-2 w-2 rounded-full bg-accent shadow-glow animate-pulse" />
            <h1 className="text-[18px] leading-[28px] font-semibold tracking-tight text-gradient-accent">
              {ws.workflowName}
            </h1>
          </div>
          <ThemeToggle />
        </header>

        {error && (
          <div className="shrink-0 mx-4 mt-3 flex items-center justify-between gap-3 rounded-xl border border-error/40 bg-error-container px-4 py-2 text-sm text-on-error-container backdrop-blur-md">
            <span className="flex items-center gap-2">
              <span aria-hidden="true">⚠</span>
              {error}
            </span>
            <button
              type="button"
              onClick={() => dispatch(clearError())}
              className="cursor-pointer rounded-full px-2 leading-none text-on-error-container/70 transition-colors hover:bg-error/15 hover:text-on-error-container"
              aria-label="Dismiss error"
            >
              ✕
            </button>
          </div>
        )}

        <MessageList messages={messages} isStreaming={isStreaming} />
        <ChatInput onSend={sendMessage} disabled={isRunning} />
      </div>
    </div>
  );
}

export default function WorkflowSessionPage() {
  const params = useParams<{ workflowSessionId: string }>();
  const workflowSessionId = params.workflowSessionId;
  const [workflowSession, setWorkflowSession] = useState<WorkflowSession | null>(null);

  useEffect(() => {
    getWorkflowSession(workflowSessionId)
      .then(setWorkflowSession)
      .catch(() => {});
  }, [workflowSessionId]);

  if (!workflowSession) return null;
  return <WorkflowSessionView ws={workflowSession} />;
}
