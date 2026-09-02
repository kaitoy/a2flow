/**
 * @module RunWorkflowDialog — confirms starting a workflow run, lets a developer
 * pick which design a modified workflow runs, and lets a draft run stub
 * individual tools.
 */
"use client";

import { FlaskConical } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Radio } from "@/components/ui/radio";
import { Spinner } from "@/components/ui/spinner";
import {
  listMcpToolMocks,
  listWorkflowTaskTemplates,
  type McpToolMock,
  type WorkflowDesignSource,
} from "@/lib/api";

/** What the operator confirmed: which design to run, and what to stub in it. */
export interface RunWorkflowChoice {
  /** Which design a modified workflow should run. */
  designSource: WorkflowDesignSource;
  /** Ids of the mocks to apply (empty when none were chosen or offered). */
  toolMockIds: string[];
}

/** Props for {@link RunWorkflowDialog}. */
export interface RunWorkflowDialogProps {
  /** Whether the dialog is visible. */
  open: boolean;
  /** Id of the workflow about to run, used to load the mocks that apply to it. */
  workflowId: string;
  /** Name of the workflow about to run, shown in the confirmation sentence. */
  workflowName: string;
  /**
   * Whether the workflow is still `draft`. A draft workflow only ever runs its
   * live design, so it gets the mock picker without the design choice.
   */
  isDraft: boolean;
  /**
   * Whether to offer the choice between the published design and the
   * unpublished edits. True only for a `modified` workflow shown to someone who
   * may edit it — nobody else can see the edits, let alone run them.
   */
  canChooseDesign: boolean;
  /** Called with the operator's choices when Run is clicked. */
  onConfirm: (choice: RunWorkflowChoice) => void;
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
 * Ask the operator to confirm a run, and let them shape it.
 *
 * A `modified` workflow holds two designs — the one published, and the edits
 * since — and a developer picks between them here. The published design is
 * preselected because it is the one everyone else already gets: running the
 * edits is a test, and is treated as one, which is why choosing it reveals the
 * mock picker exactly as a draft workflow does.
 *
 * The mock list and the workflow's task templates are fetched when the dialog
 * opens rather than with the page: a run is a deliberate action and neither is
 * read anywhere else here, so loading them up front would be a request most
 * page views never need. Only the mocks worth offering are listed — a mock
 * that stands in for a tool one of the workflow's tasks binds, or a mock of a
 * built-in tool, which every run can reach. A mock for any other tool would
 * never fire in the run, so it is left out. If the templates cannot be loaded
 * the list falls back to every mock rather than hiding all of them. Both
 * choices reset every time the dialog opens — a stubbed run, or a run of
 * unpublished work, is an explicit decision, never a sticky setting that could
 * silently carry into the next run.
 */
export function RunWorkflowDialog({
  open,
  workflowId,
  workflowName,
  isDraft,
  canChooseDesign,
  onConfirm,
  onCancel,
}: RunWorkflowDialogProps) {
  const [mocks, setMocks] = useState<McpToolMock[] | null>(null);
  const [applicable, setApplicable] = useState<McpToolMock[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [designSource, setDesignSource] = useState<WorkflowDesignSource>("published");

  // A run of unpublished work is a draft run, so it stubs tools like one.
  const isDraftRun = isDraft || designSource === "live";

  useEffect(() => {
    if (!open) return;
    setDesignSource("published");
  }, [open]);

  useEffect(() => {
    if (!open || !isDraftRun) return;
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
  }, [open, isDraftRun, workflowId]);

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
      size={isDraftRun || canChooseDesign ? "md" : "sm"}
      footer={
        <>
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => onConfirm({ designSource, toolMockIds: isDraftRun ? selected : [] })}
          >
            Run
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        {canChooseDesign && (
          <section className="flex flex-col gap-2">
            <h3 className="text-label-caps text-on-surface-variant">Which design to run</h3>
            <p className="text-sm text-on-surface-variant">
              This workflow has edits that have not been published. Everyone else still gets the
              published version, so that is what a real request runs.
            </p>
            <div className="flex flex-col">
              <Radio
                name="run-workflow-design"
                label="Published version — a real request"
                checked={designSource === "published"}
                onChange={() => setDesignSource("published")}
              />
              <Radio
                name="run-workflow-design"
                label="Unpublished edits — a test run"
                checked={designSource === "live"}
                onChange={() => setDesignSource("live")}
              />
            </div>
          </section>
        )}
        {isDraftRun && (
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
      </div>
    </Dialog>
  );
}
