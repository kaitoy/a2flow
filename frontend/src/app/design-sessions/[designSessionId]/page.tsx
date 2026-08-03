/** @module DesignSessionPage — Loads a DesignSession and renders the design chat. */
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
  type DesignSession,
  generateWorkflowDescription,
  getDesignSession,
  getWorkflow,
  listWorkflowTaskTemplates,
  type Workflow,
  type WorkflowTaskTemplate,
} from "@/lib/api";
import logger from "@/lib/logger";
import { Role, useHasRole } from "@/lib/roles";
import { clearError } from "@/store/chatSlice";
import { useAppDispatch } from "@/store/hooks";
import { showToast } from "@/store/toastSlice";

/** How often (ms) to re-fetch the workflow's task templates while designing. */
const TEMPLATE_POLL_INTERVAL_MS = 10_000;

/**
 * The design chat of a workflow's design session: the template
 * timeline on the left, the conversation with the design agent on the right.
 * Templates are re-fetched after every agent turn (and on an interval) so the
 * timeline follows the task templates the agent is editing. A developer can also open
 * the chat input's action menu to re-summarize the conversation into the
 * workflow's description; `DescriptionDiffDialog` opens immediately (showing
 * a loading skeleton and the live edge while the request is in flight) and
 * then reviews the change once it lands.
 */
function DesignSessionView({
  ds,
  workflow,
  onWorkflowUpdate,
}: {
  ds: DesignSession;
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
  } = useWorkflowSessionChat(ds.id, ds.sessionId, null, ds.userId, "design");
  const [timelineCollapsed, setTimelineCollapsed] = useState(false);
  const [timelineDrawerOpen, setTimelineDrawerOpen] = useState(false);
  const [templates, setTemplates] = useState<WorkflowTaskTemplate[]>([]);

  const refreshTemplates = useCallback(async () => {
    try {
      setTemplates(await listWorkflowTaskTemplates(ds.workflowId));
    } catch (err) {
      logger.error(err, "failed to load task templates");
    }
  }, [ds.workflowId]);

  // Load on mount and re-fetch whenever an agent turn finishes (the design
  // agent edits the templates through its tools), plus a slow interval so
  // edits made elsewhere (the admin template editor) appear too.
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
        label="Design tasks"
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
              { label: "Design" },
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

/** Full-screen error state shown when the DesignSession record fails to load, with a retry action. */
function DesignSessionLoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex h-dvh flex-col items-center justify-center gap-4">
      <EmptyState
        icon={AlertTriangle}
        animation="wiggle"
        title="Couldn't load this design session"
        description="Something went wrong while loading this design session."
      />
      <Button variant="secondary" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}

/**
 * Page shell: loads the DesignSession record and its workflow, then renders
 * the design chat (or a skeleton / retryable error state).
 */
export default function DesignSessionPage() {
  const params = useParams<{ designSessionId: string }>();
  const designSessionId = params.designSessionId;
  const [designSession, setDesignSession] = useState<DesignSession | null>(null);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [retryCount, setRetryCount] = useState(0);

  // biome-ignore lint/correctness/useExhaustiveDependencies: retryCount is a bump counter that re-triggers the fetch, not a data dependency
  useEffect(() => {
    setLoadFailed(false);
    getDesignSession(designSessionId)
      .then(async (ds) => {
        const wf = await getWorkflow(ds.workflowId);
        setDesignSession(ds);
        setWorkflow(wf);
      })
      .catch((err: unknown) => {
        logger.error(err, "failed to load design session");
        setLoadFailed(true);
      });
  }, [designSessionId, retryCount]);

  const retry = useCallback(() => setRetryCount((c) => c + 1), []);

  return (
    <AuthProvider>
      {designSession && workflow ? (
        <DesignSessionView ds={designSession} workflow={workflow} onWorkflowUpdate={setWorkflow} />
      ) : loadFailed ? (
        <DesignSessionLoadError onRetry={retry} />
      ) : (
        <WorkflowSessionSkeleton />
      )}
    </AuthProvider>
  );
}
