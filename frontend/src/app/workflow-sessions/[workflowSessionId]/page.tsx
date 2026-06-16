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
import { Skeleton } from "@/components/ui/skeleton";
import { useWorkflowSessionChat } from "@/hooks/useWorkflowSessionChat";
import { getWorkflowSession, type WorkflowSession } from "@/lib/api";
import { clearError } from "@/store/chatSlice";
import { useAppDispatch } from "@/store/hooks";

function WorkflowSessionView({ ws }: { ws: WorkflowSession }) {
  const dispatch = useAppDispatch();
  const { messages, isRunning, isStreaming, error, sendMessage, sendApprovalResult } =
    useWorkflowSessionChat(ws.id, ws.sessionId, ws.workflowPrompt);

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

        <MessageList
          messages={messages}
          isStreaming={isStreaming}
          onApprovalResolved={sendApprovalResult}
        />
        <ChatInput onSend={sendMessage} disabled={isRunning} />
      </div>
    </div>
  );
}

/**
 * Placeholder chat layout shown while the WorkflowSession record loads, so the
 * page presents the header shell and a few message-bubble skeletons instead of
 * flashing a blank screen.
 */
function WorkflowSessionSkeleton() {
  return (
    <div role="status" aria-label="Loading" className="flex h-screen overflow-hidden">
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
            <Skeleton className="h-5 w-40" />
          </div>
          <ThemeToggle />
        </header>

        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto flex max-w-3xl flex-col gap-4">
            <Skeleton className="ml-auto h-16 w-2/3 rounded-2xl rounded-tr-md" />
            <Skeleton className="h-24 w-3/4 rounded-2xl rounded-tl-md" />
            <Skeleton className="ml-auto h-12 w-1/2 rounded-2xl rounded-tr-md" />
            <Skeleton className="h-20 w-2/3 rounded-2xl rounded-tl-md" />
          </div>
        </div>

        <div className="shrink-0 px-6 pb-6">
          <Skeleton className="mx-auto h-14 w-full max-w-3xl rounded-2xl" />
        </div>
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

  if (!workflowSession) return <WorkflowSessionSkeleton />;
  return <WorkflowSessionView ws={workflowSession} />;
}
