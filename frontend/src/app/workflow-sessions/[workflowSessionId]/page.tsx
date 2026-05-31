/** @module WorkflowSessionPage — Loads a WorkflowSession record and renders the workflow chat view. */
"use client";

import Image from "next/image";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import logo from "@/../assets/logo.png";
import { ChatErrorBanner } from "@/components/ChatErrorBanner";
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
            <Image
              src={logo}
              alt="A2Flow logo"
              width={logo.width}
              height={logo.height}
              className="h-10 w-auto"
              priority
            />
            <span className="inline-block h-2 w-2 rounded-full bg-accent shadow-glow animate-pulse" />
            <h1 className="text-[18px] leading-[28px] font-semibold tracking-tight text-gradient-accent">
              {ws.workflowName}
            </h1>
          </div>
          <ThemeToggle />
        </header>

        <ChatErrorBanner error={error} onDismiss={() => dispatch(clearError())} />

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
