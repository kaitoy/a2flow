import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ToolBinding, WorkflowTask } from "@/lib/api";
import { WorkflowTaskTimeline } from "./WorkflowTaskTimeline";

const makeTask = (
  id: string,
  title: string,
  status: WorkflowTask["status"] = "pending",
  position = 0,
  toolBindings: ToolBinding[] = [],
  description: string | null = null
): WorkflowTask => ({
  id,
  workflowExecutionId: "execution",
  title,
  status,
  position,
  dependsOnIds: [],
  toolBindings,
  description,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
});

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

  it("shows a task's description in a tooltip on hover", async () => {
    const user = userEvent.setup();
    const withDescription = [
      makeTask("t1", "Gather sources", "completed", 0, [], "Collect all reference material."),
    ];
    render(
      <WorkflowTaskTimeline
        tasks={withDescription}
        activeTaskId={null}
        onSelectTask={vi.fn()}
        collapsed={false}
        onToggle={vi.fn()}
      />
    );
    await user.hover(screen.getByText("Gather sources"));
    expect(await screen.findByRole("tooltip")).toHaveTextContent("Collect all reference material.");
  });

  it("shows no tooltip for a task with no description", async () => {
    const user = userEvent.setup();
    render(
      <WorkflowTaskTimeline
        tasks={tasks}
        activeTaskId={null}
        onSelectTask={vi.fn()}
        collapsed={false}
        onToggle={vi.fn()}
      />
    );
    await user.hover(screen.getByText("Gather sources"));
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
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

  it("shows a tool-count indicator for a task with bound tools", () => {
    const withTools = [
      makeTask("t1", "Gather sources", "completed", 0, [
        { mcpServerId: "srv-1", toolName: "extract_text" },
        { mcpServerId: "srv-1", toolName: "ocr_scan" },
      ]),
      makeTask("t2", "Draft", "in_progress", 1),
    ];
    render(
      <WorkflowTaskTimeline
        tasks={withTools}
        activeTaskId="t2"
        onSelectTask={vi.fn()}
        collapsed={false}
        onToggle={vi.fn()}
      />
    );
    expect(screen.getByLabelText("2 bound tools")).toBeInTheDocument();
    const draftRow = screen.getByRole("button", { name: /Draft/ }).closest("li") as HTMLElement;
    expect(within(draftRow).queryByLabelText(/bound tool/)).not.toBeInTheDocument();
  });

  it("opens a dialog listing the bound tools and their servers on click", async () => {
    const user = userEvent.setup();
    const withTools = [
      makeTask("t1", "Gather sources", "completed", 0, [
        { mcpServerId: "mcp-1", toolName: "extract_text" },
      ]),
    ];
    render(
      <WorkflowTaskTimeline
        tasks={withTools}
        activeTaskId={null}
        onSelectTask={vi.fn()}
        collapsed={false}
        onToggle={vi.fn()}
      />
    );
    await user.click(screen.getByLabelText("1 bound tool"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("extract_text")).toBeInTheDocument();
    expect(await within(dialog).findByText("my-mcp-server")).toBeInTheDocument();
  });

  it("falls back to 'Unknown server' when the bound server isn't registered", async () => {
    const user = userEvent.setup();
    const withTools = [
      makeTask("t1", "Gather sources", "completed", 0, [
        { mcpServerId: "missing-server", toolName: "extract_text" },
      ]),
    ];
    render(
      <WorkflowTaskTimeline
        tasks={withTools}
        activeTaskId={null}
        onSelectTask={vi.fn()}
        collapsed={false}
        onToggle={vi.fn()}
      />
    );
    await user.click(screen.getByLabelText("1 bound tool"));
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Unknown server")).toBeInTheDocument();
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
