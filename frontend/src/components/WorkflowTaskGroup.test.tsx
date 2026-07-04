import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { WorkflowTask } from "@/lib/api";
import { WorkflowTaskGroup } from "./WorkflowTaskGroup";

const task = {
  id: "t1",
  workflowSessionId: "ws",
  title: "Draft the report",
  status: "in_progress",
  position: 0,
  dependsOnIds: [],
  toolBindings: [],
} as WorkflowTask;

describe("WorkflowTaskGroup", () => {
  it("shows the task title, status, and ordinal badge", () => {
    render(
      <WorkflowTaskGroup task={task} index={2} isHighlighted={false} onHover={vi.fn()}>
        <div>body</div>
      </WorkflowTaskGroup>
    );
    expect(screen.getByText("Draft the report")).toBeInTheDocument();
    expect(screen.getByText("in progress")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("applies the anchor id when provided", () => {
    const { container } = render(
      <WorkflowTaskGroup
        task={task}
        index={1}
        anchorId="wf-task-group-t1"
        isHighlighted={false}
        onHover={vi.fn()}
      >
        <div>body</div>
      </WorkflowTaskGroup>
    );
    expect(container.querySelector("#wf-task-group-t1")).not.toBeNull();
  });

  it("falls back to a generic label when the task is unresolved", () => {
    render(
      <WorkflowTaskGroup index={1} isHighlighted={false} onHover={vi.fn()}>
        <div>body</div>
      </WorkflowTaskGroup>
    );
    expect(screen.getByText("Task")).toBeInTheDocument();
  });

  it("reports hover enter and leave with the task id", async () => {
    const onHover = vi.fn();
    render(
      <WorkflowTaskGroup task={task} index={1} isHighlighted={false} onHover={onHover}>
        <div>body</div>
      </WorkflowTaskGroup>
    );
    const section = screen.getByText("Draft the report").closest("section");
    if (!section) throw new Error("section not found");
    await userEvent.hover(section);
    expect(onHover).toHaveBeenCalledWith("t1");
    await userEvent.unhover(section);
    expect(onHover).toHaveBeenCalledWith(null);
  });
});
