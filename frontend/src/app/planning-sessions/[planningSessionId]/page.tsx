/** @module PlanningSessionPage — Loads a PlanningSession and renders the plan-refinement chat. */
"use client";

import { AlertTriangle } from "lucide-react";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { Breadcrumbs } from "@/components/admin/breadcrumbs";
import { DescriptionDiffDialog } from "@/components/admin/description-diff-dialog";
import { AuthProvider } from "@/components/auth/auth-provider";
import { ChatInput } from "@/components/ChatInput";
import { ChatInputMenu } from "@/components/ChatInputMenu";
import { MessageList } from "@/components/MessageList";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorBanner } from "@/components/ui/error-banner";
import { SidebarDrawer } from "@/components/ui/sidebar-drawer";
import { WorkflowSessionSkeleton } from "@/components/WorkflowSessionSkeleton";
import { WorkflowTaskTimeline } from "@/components/WorkflowTaskTimeline";
import { useAsyncAction } from "@/hooks/useAsyncAction";
import { useWorkflowSessionChat } from "@/hooks/useWorkflowSessionChat";
import {
  generateWorkflowDescription,
  getPlanningSession,
  getWorkflow,
  listWorkflowTaskTemplates,
  type PlanningSession,
  type Workflow,
  type WorkflowTaskTemplate,
} from "@/lib/api";
import logger from "@/lib/logger";
import { Role, useHasRole } from "@/lib/roles";
import { clearError } from "@/store/chatSlice";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/** How often (ms) to re-fetch the workflow's task templates while planning. */
const TEMPLATE_POLL_INTERVAL_MS = 10_000;

/**
 * The plan-refinement chat of a workflow's planning session: the template
 * timeline on the left, the conversation with the planning agent on the right.
 * Templates are re-fetched after every agent turn (and on an interval) so the
 * timeline follows the plan the agent is editing. A developer can also open
 * the chat input's action menu to re-summarize the conversation into the
 * workflow's description; `DescriptionDiffDialog` opens immediately (showing
 * a loading skeleton and the live edge while the request is in flight) and
 * then reviews the change once it lands.
 */
function PlanningSessionView({
  ps,
  workflow,
  onWorkflowUpdate,
}: {
  ps: PlanningSession;
  workflow: Workflow;
  onWorkflowUpdate: (wf: Workflow) => void;
}) {
  const dispatch = useAppDispatch();
  const canEdit = useHasRole(Role.DEVELOPER);
  const generateDescription = useAsyncAction({ showDone: false });
  const [diffOpen, setDiffOpen] = useState(false);
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

  async function handleGenerateDescription() {
    // Open the dialog immediately, before the request resolves, so the
    // skeleton + live edge give feedback the moment the action starts.
    setDiffOpen(true);
    try {
      await generateDescription.run(async () => {
        const updated = await generateWorkflowDescription(workflow.id);
        onWorkflowUpdate(updated);
        dispatch(showToast({ message: "Description generated" }));
      });
    } catch {
      // Failure toast is shown globally by api.ts; close the dialog rather
      // than leaving it stuck on the loading skeleton.
      setDiffOpen(false);
    }
  }

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
        <ChatInput
          onSend={sendMessage}
          disabled={isRunning}
          leading={
            canEdit ? (
              <ChatInputMenu
                onGenerateDescription={handleGenerateDescription}
                disabled={workflow.status === "generating" || generateDescription.inFlight}
                pending={generateDescription.inFlight}
              />
            ) : undefined
          }
        />
      </div>
      <DescriptionDiffDialog
        open={diffOpen}
        generated={workflow.generatedDescription ?? ""}
        description={workflow.description ?? ""}
        onClose={() => setDiffOpen(false)}
        // Unlike the live-edge convention elsewhere (gated on the 200ms
        // `status === "pending"` stage to avoid flashing on fast responses),
        // this has to flip true the instant the dialog opens: `open`,
        // `generated`, and `description` above are still last render's
        // (stale, usually empty) values until the request resolves, so a
        // `pending`-gated `loading` would show a misleading "no diff" beat
        // before the skeleton ever appears.
        loading={generateDescription.inFlight}
      />
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
        <PlanningSessionView
          ps={planningSession}
          workflow={workflow}
          onWorkflowUpdate={setWorkflow}
        />
      ) : loadFailed ? (
        <PlanningSessionLoadError onRetry={retry} />
      ) : (
        <WorkflowSessionSkeleton />
      )}
    </AuthProvider>
  );
}
