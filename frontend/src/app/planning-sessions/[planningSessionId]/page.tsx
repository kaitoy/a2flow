/** @module PlanningSessionPage — Loads a PlanningSession and renders the plan-refinement chat. */
"use client";

import { AlertTriangle } from "lucide-react";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { AuthProvider } from "@/components/auth/auth-provider";
import { ChatInput } from "@/components/ChatInput";
import { MessageList } from "@/components/MessageList";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorBanner } from "@/components/ui/error-banner";
import { SidebarDrawer } from "@/components/ui/sidebar-drawer";
import { WorkflowSessionSkeleton } from "@/components/WorkflowSessionSkeleton";
import { WorkflowTaskTimeline } from "@/components/WorkflowTaskTimeline";
import { useWorkflowSessionChat } from "@/hooks/useWorkflowSessionChat";
import {
  getPlanningSession,
  getWorkflow,
  listWorkflowTaskTemplates,
  type PlanningSession,
  type Workflow,
  type WorkflowTaskTemplate,
} from "@/lib/api";
import logger from "@/lib/logger";
import { clearError } from "@/store/chatSlice";
import { useAppDispatch } from "@/store/hooks";

/** How often (ms) to re-fetch the workflow's task templates while planning. */
const TEMPLATE_POLL_INTERVAL_MS = 10_000;

/**
 * The plan-refinement chat of a workflow's planning session: the template
 * timeline on the left, the conversation with the planning agent on the right.
 * Templates are re-fetched after every agent turn (and on an interval) so the
 * timeline follows the plan the agent is editing.
 */
function PlanningSessionView({ ps, workflow }: { ps: PlanningSession; workflow: Workflow }) {
  const dispatch = useAppDispatch();
  const {
    messages,
    isRunning,
    isStreaming,
    error,
    pendingRenderCalls,
    sendMessage,
    sendA2uiAction,
    sendApprovalResult,
  } = useWorkflowSessionChat(ps.id, ps.sessionId, null, ps.userId, "planning");
  const [timelineCollapsed, setTimelineCollapsed] = useState(false);
  const [timelineDrawerOpen, setTimelineDrawerOpen] = useState(false);
  const [templates, setTemplates] = useState<WorkflowTaskTemplate[]>([]);

  const refreshTemplates = useCallback(async () => {
    try {
      setTemplates(await listWorkflowTaskTemplates(ps.workflowId));
    } catch (err) {
      logger.error(err, "failed to load task templates");
    }
  }, [ps.workflowId]);

  // Load on mount and re-fetch whenever an agent turn finishes (the planning
  // agent edits the templates through its tools), plus a slow interval so
  // edits made elsewhere (the admin plan editor) appear too.
  useEffect(() => {
    if (!isRunning) void refreshTemplates();
  }, [isRunning, refreshTemplates]);
  useEffect(() => {
    const id = setInterval(() => void refreshTemplates(), TEMPLATE_POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refreshTemplates]);

  const taskIndexById = useMemo(() => new Map(templates.map((t, i) => [t.id, i + 1])), [templates]);

  return (
    <div className="flex h-dvh overflow-hidden">
      <WorkflowTaskTimeline
        tasks={templates}
        activeTaskId={null}
        taskIndexById={taskIndexById}
        onSelectTask={() => {}}
        collapsed={timelineCollapsed}
        onToggle={() => setTimelineCollapsed((c) => !c)}
        className="max-md:hidden"
      />
      <SidebarDrawer
        open={timelineDrawerOpen}
        onClose={() => setTimelineDrawerOpen(false)}
        label="Plan tasks"
      >
        <WorkflowTaskTimeline
          tasks={templates}
          activeTaskId={null}
          taskIndexById={taskIndexById}
          onSelectTask={() => {}}
          collapsed={false}
          onToggle={() => setTimelineDrawerOpen(false)}
        />
      </SidebarDrawer>
      <div className="flex flex-col flex-1 min-w-0">
        <AppHeader onMenuClick={() => setTimelineDrawerOpen(true)} />

        <div className="shrink-0 px-4 pt-3 sm:px-6">
          <Breadcrumbs
            items={[
              { label: "Admin", href: "/admin" },
              { label: "Workflows", href: "/admin/workflows" },
              { label: workflow.name, href: `/admin/workflows/${encodeURIComponent(workflow.id)}` },
              { label: "Planning" },
            ]}
          />
        </div>

        {error && (
          <div className="shrink-0 mx-4 mt-3">
            <ErrorBanner error={error} onDismiss={() => dispatch(clearError())} />
          </div>
        )}

        <MessageList
          messages={messages}
          isStreaming={isStreaming}
          isRunning={isRunning}
          onAction={sendA2uiAction}
          onApprovalResolved={sendApprovalResult}
          pendingRenderCalls={pendingRenderCalls}
        />
        <ChatInput onSend={sendMessage} disabled={isRunning} />
      </div>
    </div>
  );
}

/** Full-screen error state shown when the PlanningSession record fails to load, with a retry action. */
function PlanningSessionLoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-4">
      <EmptyState
        icon={AlertTriangle}
        animation="wiggle"
        title="Couldn't load this planning session"
        description="Something went wrong while loading this planning session."
      />
      <Button variant="secondary" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}

/**
 * Page shell: loads the PlanningSession record and its workflow, then renders
 * the plan-refinement chat (or a skeleton / retryable error state).
 */
export default function PlanningSessionPage() {
  const params = useParams<{ planningSessionId: string }>();
  const planningSessionId = params.planningSessionId;
  const [planningSession, setPlanningSession] = useState<PlanningSession | null>(null);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  // biome-ignore lint/correctness/useExhaustiveDependencies: retryCount is a bump counter that re-triggers the fetch, not a data dependency
  useEffect(() => {
    setLoadFailed(false);
    getPlanningSession(planningSessionId)
      .then(async (ps) => {
        const wf = await getWorkflow(ps.workflowId);
        setPlanningSession(ps);
        setWorkflow(wf);
      })
      .catch((err: unknown) => {
        logger.error(err, "failed to load planning session");
        setLoadFailed(true);
      });
  }, [planningSessionId, retryCount]);

  const retry = useCallback(() => setRetryCount((c) => c + 1), []);

  return (
    <AuthProvider>
      {planningSession && workflow ? (
        <PlanningSessionView ps={planningSession} workflow={workflow} />
      ) : loadFailed ? (
        <PlanningSessionLoadError onRetry={retry} />
      ) : (
        <WorkflowSessionSkeleton />
      )}
    </AuthProvider>
  );
}
