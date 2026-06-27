import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { WorkflowTask } from "@/lib/api";
import { WorkflowTaskDivider } from "./WorkflowTaskDivider";

const task = {
  id: "t1",
  workflowSessionId: "ws",
  title: "Draft the report",
  status: "in_progress",
  position: 0,
  dependsOnIds: [],
  toolBindings: [],
} as WorkflowTask;

describe("WorkflowTaskDivider", () => {
  it("shows the task title and status", () => {
    render(<WorkflowTaskDivider task={task} />);
    expect(screen.getByText("Draft the report")).toBeInTheDocument();
    expect(screen.getByText("in progress")).toBeInTheDocument();
  });

  it("applies the anchor id when provided", () => {
    const { container } = render(<WorkflowTaskDivider task={task} anchorId="wf-task-divider-t1" />);
    expect(container.querySelector("#wf-task-divider-t1")).not.toBeNull();
  });

  it("falls back to a generic label when the task is unresolved", () => {
    render(<WorkflowTaskDivider />);
    expect(screen.getByText("タスク")).toBeInTheDocument();
  });
});
