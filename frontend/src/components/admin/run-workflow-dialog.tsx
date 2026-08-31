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
import { listMcpToolMocks, listWorkflowTaskTemplates, type McpToolMock } from "@/lib/api";

/** Props for {@link RunWorkflowDialog}. */
export interface RunWorkflowDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Id of the workflow about to run, used to load the mocks that apply to it. */
  workflowId: string;
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

/** Key identifying one bound `(server, tool)` pair. */
function toolKey(mcpServerId: string, toolName: string): string {
  return `${mcpServerId}:${toolName}`;
}

/**
 * Ask the operator to confirm a run, offering a draft workflow's tool mocks.
 *
 * The mock list and the workflow's task templates are fetched when the dialog
 * opens rather than with the page: a run is a deliberate action and neither is
 * read anywhere else here, so loading them up front would be a request most
 * page views never need. Only the mocks worth offering are listed — a mock
 * that stands in for a tool one of the workflow's tasks binds, or a mock of a
 * built-in tool, which every run can reach. A mock for any other tool would
 * never fire in the run, so it is left out. If the templates cannot be loaded
 * the list falls back to every mock rather than hiding all of them. Selections
 * reset every time the dialog opens — a stubbed run is an explicit choice,
 * never a sticky setting that could silently carry into the next run.
 */
export function RunWorkflowDialog({
  open,
  workflowId,
  workflowName,
  isDraft,
  onConfirm,
  onCancel,
}: RunWorkflowDialogProps) {
  const [mocks, setMocks] = useState<McpToolMock[] | null>(null);
  const [applicable, setApplicable] = useState<McpToolMock[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);

  useEffect(() => {
    if (!open || !isDraft) return;
    setSelected([]);
    setMocks(null);
    setApplicable(null);
    let cancelled = false;
    Promise.all([
      listMcpToolMocks({ limit: 100 }),
      // A failed templates load leaves the binding set unknown; `null` tells
      // the handler below to skip filtering rather than hide every mock.
      listWorkflowTaskTemplates(workflowId, { limit: 1000 }).catch(() => null),
    ])
      .then(([items, templates]) => {
        if (cancelled) return;
        setMocks(items);
        if (templates === null) {
          setApplicable(items);
          return;
        }
        const bound = new Set<string>();
        for (const template of templates) {
          for (const binding of template.toolBindings ?? []) {
            bound.add(toolKey(binding.mcpServerId, binding.toolName));
          }
        }
        setApplicable(
          items.filter((mock) => {
            const serverId = mock.mcpServerId;
            // A built-in tool's mock carries no server id and every run can
            // reach it, so it is always offered.
            if (serverId === null || serverId === undefined) return true;
            return bound.has(toolKey(serverId, mock.toolName));
          })
        );
      })
      .catch(() => {
        // The failure toast is shown globally by api.ts; an empty list here
        // still lets the operator start an ordinary, unstubbed run.
        if (cancelled) return;
        setMocks([]);
        setApplicable([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open, isDraft, workflowId]);

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
            effect. Leave a tool unchecked to exercise it for real. Only mocks for a tool this
            workflow&apos;s tasks use, and mocks of a built-in tool, are listed.
          </p>
          {applicable === null || mocks === null ? (
            <div className="flex justify-center py-4">
              <Spinner size="sm" />
            </div>
          ) : applicable.length === 0 ? (
            <EmptyState
              icon={FlaskConical}
              compact
              description={
                mocks.length === 0
                  ? "No tool mocks are registered yet."
                  : "No registered tool mock targets a tool this workflow uses."
              }
            />
          ) : (
            <div className="flex max-h-64 flex-col overflow-y-auto">
              {applicable.map((mock) => (
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
