import { describe, expect, it } from "vitest";
import { canExecuteWorkflow, visibleWorkflowStatuses, WORKFLOW_STATUSES } from "./workflow-status";

describe("visibleWorkflowStatuses", () => {
  it("offers every status to someone who can edit workflows", () => {
    expect(visibleWorkflowStatuses(true)).toEqual(WORKFLOW_STATUSES);
  });

  it("hides draft and modified from everyone else", () => {
    // The backend never sends either to a non-developer: draft rows are
    // filtered out, and a modified workflow is reported as published. A filter
    // for one would always come back empty.
    expect(visibleWorkflowStatuses(false)).toEqual(["generating", "failed", "published"]);
  });

  it("keeps the lifecycle order it filters", () => {
    const visible = visibleWorkflowStatuses(false);
    const order = visible.map((s) => WORKFLOW_STATUSES.indexOf(s));
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });
});

describe("canExecuteWorkflow", () => {
  const requester = { canRun: true, canEdit: false };
  const developer = { canRun: true, canEdit: true };

  it("allows a published workflow for anyone with Run", () => {
    expect(canExecuteWorkflow("published", requester)).toBe(true);
  });

  it("allows a modified workflow, which runs its published version", () => {
    expect(canExecuteWorkflow("modified", requester)).toBe(true);
  });

  it("allows a draft workflow only for someone who can also edit", () => {
    expect(canExecuteWorkflow("draft", requester)).toBe(false);
    expect(canExecuteWorkflow("draft", developer)).toBe(true);
  });

  it("refuses a workflow that is still generating or has failed", () => {
    expect(canExecuteWorkflow("generating", developer)).toBe(false);
    expect(canExecuteWorkflow("failed", developer)).toBe(false);
  });

  it("refuses a workflow whose status has not loaded yet", () => {
    expect(canExecuteWorkflow(undefined, developer)).toBe(false);
  });
});
