/**
 * @module RunWorkflowDialog — confirms starting a workflow run, and for a draft
 * workflow lets the operator stub individual tools for that run.
 */
"use client";

import { FlaskConical } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Spinner } from "@/components/ui/spinner";
import { listMcpToolMocks, type McpToolMock } from "@/lib/api";

/** Props for {@link RunWorkflowDialog}. */
export interface RunWorkflowDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Name of the workflow about to run, shown in the confirmation sentence. */
  workflowName: string;
  /**
   * Whether the workflow is still `draft`. Only a draft run may stub its tools,
   * so the mock picker is hidden entirely otherwise and the dialog is a plain
   * confirmation.
   */
  isDraft: boolean;
  /** Called with the ids of the mocks to apply (empty when none were chosen). */
  onConfirm: (toolMockIds: string[]) => void;
  /** Called on Cancel, Escape, or a backdrop click. */
  onCancel: () => void;
}

/** Describe one mock's target for the checkbox label. */
function mockLabel(mock: McpToolMock): string {
  return `${mock.name} — ${mock.toolName}`;
}

/**
 * Ask the operator to confirm a run, offering a draft workflow's tool mocks.
 *
 * The mock list is fetched when the dialog opens rather than with the page: a
 * run is a deliberate action and the list is only ever read here, so loading it
 * up front would be a request most page views never need. Selections reset every
 * time the dialog opens — a stubbed run is an explicit choice, never a sticky
 * setting that could silently carry into the next run.
 */
export function RunWorkflowDialog({
  open,
  workflowName,
  isDraft,
  onConfirm,
  onCancel,
}: RunWorkflowDialogProps) {
  const [mocks, setMocks] = useState<McpToolMock[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => {
    if (!open || !isDraft) return;
    setSelected([]);
    setMocks(null);
    let cancelled = false;
    listMcpToolMocks({ limit: 100 })
      .then((items) => {
        if (!cancelled) setMocks(items);
      })
      .catch(() => {
        // The failure toast is shown globally by api.ts; an empty list here
        // still lets the operator start an ordinary, unstubbed run.
        if (!cancelled) setMocks([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open, isDraft]);

  function toggle(id: string) {
    setSelected((current) =>
      current.includes(id) ? current.filter((x) => x !== id) : [...current, id]
    );
  }

  return (
    <Dialog
      open={open}
      onClose={onCancel}
      panelId="run-workflow-dialog"
      title="Run Workflow"
      description={`Run "${workflowName}"? This starts a new execution.`}
      size={isDraft ? "md" : "sm"}
      footer={
        <>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="primary" onClick={() => onConfirm(isDraft ? selected : [])}>
            Run
          </Button>
        </>
      }
    >
      {isDraft && (
        <section className="flex flex-col gap-2">
          <h3 className="text-label-caps text-on-surface-variant">Mock tools</h3>
          <p className="text-sm text-on-surface-variant">
            A stubbed tool is not called: it returns the mock&apos;s configured result and has no
            effect. Leave a tool unchecked to exercise it for real.
          </p>
          {mocks === null ? (
            <div className="flex justify-center py-4">
              <Spinner size="sm" />
            </div>
          ) : mocks.length === 0 ? (
            <EmptyState
              icon={FlaskConical}
              compact
              description="No tool mocks are registered yet."
            />
          ) : (
            <div className="flex max-h-64 flex-col overflow-y-auto">
              {mocks.map((mock) => (
                <Checkbox
                  key={mock.id}
                  label={mockLabel(mock)}
                  checked={selected.includes(mock.id)}
                  onChange={() => toggle(mock.id)}
                />
              ))}
            </div>
          )}
        </section>
      )}
    </Dialog>
  );
}
