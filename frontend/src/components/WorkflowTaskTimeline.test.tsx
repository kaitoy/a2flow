import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { WorkflowTask } from "@/lib/api";
import { WorkflowTaskTimeline } from "./WorkflowTaskTimeline";

const makeTask = (
  id: string,
  title: string,
  status: WorkflowTask["status"] = "pending",
  position = 0
): WorkflowTask =>
  ({
    id,
    workflowSessionId: "ws",
    title,
    status,
    position,
    dependsOnIds: [],
    toolBindings: [],
  }) as WorkflowTask;

const tasks = [
  makeTask("t1", "Gather sources", "completed", 0),
  makeTask("t2", "Draft", "in_progress", 1),
  makeTask("t3", "Review", "pending", 2),
];

describe("WorkflowTaskTimeline", () => {
  it("renders each task's title", () => {
    render(
      <WorkflowTaskTimeline
        tasks={tasks}
        activeTaskId="t2"
        onSelectTask={vi.fn()}
        collapsed={false}
        onToggle={vi.fn()}
      />
    );
    expect(screen.getByText("Gather sources")).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
    expect(screen.getByText("Review")).toBeInTheDocument();
  });

  it("marks the active task with aria-current", () => {
    render(
      <WorkflowTaskTimeline
        tasks={tasks}
        activeTaskId="t2"
        onSelectTask={vi.fn()}
        collapsed={false}
        onToggle={vi.fn()}
      />
    );
    const active = screen.getByRole("button", { name: /Draft/ });
    expect(active).toHaveAttribute("aria-current", "true");
  });

  it("calls onSelectTask with the clicked task id", async () => {
    const onSelectTask = vi.fn();
    render(
      <WorkflowTaskTimeline
        tasks={tasks}
        activeTaskId="t2"
        onSelectTask={onSelectTask}
        collapsed={false}
        onToggle={vi.fn()}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: /Review/ }));
    expect(onSelectTask).toHaveBeenCalledWith("t3");
  });

  it("toggles open when collapsed", async () => {
    const onToggle = vi.fn();
    render(
      <WorkflowTaskTimeline
        tasks={tasks}
        activeTaskId={null}
        onSelectTask={vi.fn()}
        collapsed={true}
        onToggle={onToggle}
      />
    );
    // Collapsed: task titles are hidden, only the show toggle is present.
    expect(screen.queryByText("Draft")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Show task timeline/ }));
    expect(onToggle).toHaveBeenCalled();
  });

  it("numbers each entry from its position by default", () => {
    render(
      <WorkflowTaskTimeline
        tasks={tasks}
        activeTaskId="t2"
        onSelectTask={vi.fn()}
        collapsed={false}
        onToggle={vi.fn()}
      />
    );
    // Default ordinals follow the task order: 1, 2, 3.
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("shows an empty state when there are no tasks", () => {
    render(
      <WorkflowTaskTimeline
        tasks={[]}
        activeTaskId={null}
        onSelectTask={vi.fn()}
        collapsed={false}
        onToggle={vi.fn()}
      />
    );
    expect(screen.getByText("No tasks yet.")).toBeInTheDocument();
  });
});
