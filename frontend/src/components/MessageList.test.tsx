import type { Message } from "@ag-ui/core";
import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { useEffect } from "react";
import { describe, expect, it, vi } from "vitest";
import type { WorkflowTask } from "@/lib/api";
import { MessageList } from "./MessageList";

const makeTask = (id: string, title: string): WorkflowTask => ({
  id,
  workflowSessionId: "ws",
  title,
  status: "in_progress",
  position: 0,
  dependsOnIds: [],
  toolBindings: [],
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-01T00:00:00Z",
  createdBy: "",
  updatedBy: "",
});

const { mountSpy } = vi.hoisted(() => ({ mountSpy: vi.fn() }));

vi.mock("./MessageBubble", () => ({
  MessageBubble: ({
    message,
    isStreaming,
    isThinking,
    avatar,
    pendingToolCallIds,
    toolResultContentByCallId,
  }: {
    message: Message;
    isStreaming: boolean;
    isThinking?: boolean;
    avatar?: ReactNode;
    pendingToolCallIds?: Set<string>;
    toolResultContentByCallId?: Map<string, string>;
  }) => {
    // Mount-only (empty deps), mirroring how ApprovalControls fetches on mount —
    // lets tests detect an unwanted remount of a message bubble.
    // biome-ignore lint/correctness/useExhaustiveDependencies: intentionally mount-only
    useEffect(() => {
      mountSpy(message.id);
    }, []);
    return (
      <div
        data-testid={`bubble-${message.id}`}
        data-streaming={String(isStreaming)}
        data-thinking={String(isThinking)}
        data-pending={pendingToolCallIds ? Array.from(pendingToolCallIds).join(",") : ""}
        data-tool-content={toolResultContentByCallId?.get("tc-1") ?? ""}
      >
        {avatar}
      </div>
    );
  },
}));

describe("MessageList", () => {
  it("shows empty state when messages is empty", () => {
    render(<MessageList messages={[]} />);
    expect(screen.getByText("Start a conversation")).toBeInTheDocument();
  });

  it("renders one MessageBubble per message", () => {
    const messages: Message[] = [
      { id: "m1", role: "user", content: "hi" },
      { id: "m2", role: "assistant", content: "hello" },
    ];
    render(<MessageList messages={messages} />);
    expect(screen.getByTestId("bubble-m1")).toBeInTheDocument();
    expect(screen.getByTestId("bubble-m2")).toBeInTheDocument();
  });

  it("passes a renderAvatar result to each bubble when provided", () => {
    const messages: Message[] = [
      { id: "m1", role: "user", content: "hi" },
      { id: "m2", role: "assistant", content: "hello" },
    ];
    render(
      <MessageList
        messages={messages}
        renderAvatar={(m) => <span data-testid={`avatar-${m.id}`}>{m.role}</span>}
      />
    );
    expect(screen.getByTestId("avatar-m1")).toHaveTextContent("user");
    expect(screen.getByTestId("avatar-m2")).toHaveTextContent("assistant");
  });

  it("only the last bubble receives isStreaming=true when list isStreaming", () => {
    const messages: Message[] = [
      { id: "m1", role: "user", content: "hi" },
      { id: "m2", role: "assistant", content: "" },
    ];
    render(<MessageList messages={messages} isStreaming={true} />);
    expect(screen.getByTestId("bubble-m1")).toHaveAttribute("data-streaming", "false");
    expect(screen.getByTestId("bubble-m2")).toHaveAttribute("data-streaming", "true");
  });

  it("calls scrollIntoView on mount", () => {
    render(<MessageList messages={[]} />);
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it("follows new messages to the bottom while the viewer is near the bottom", () => {
    const initial: Message[] = [{ id: "m1", role: "user", content: "hi" }];
    const { container, rerender } = render(<MessageList messages={initial} />);
    const scrollEl = container.querySelector(".overflow-y-auto") as HTMLElement;
    // Near the bottom: scrollHeight === clientHeight, scrollTop 0 -> distance 0.
    Object.defineProperty(scrollEl, "scrollHeight", { value: 200, configurable: true });
    Object.defineProperty(scrollEl, "clientHeight", { value: 200, configurable: true });
    fireEvent.scroll(scrollEl);

    vi.mocked(Element.prototype.scrollIntoView).mockClear();
    rerender(<MessageList messages={[...initial, { id: "m2", role: "user", content: "yo" }]} />);
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it("does not follow new messages after the viewer scrolls up", () => {
    const initial: Message[] = [{ id: "m1", role: "user", content: "hi" }];
    const { container, rerender } = render(<MessageList messages={initial} />);
    const scrollEl = container.querySelector(".overflow-y-auto") as HTMLElement;
    // Scrolled up: 1000 - 0 - 200 = 800px from the bottom, well past the 120 threshold.
    Object.defineProperty(scrollEl, "scrollHeight", { value: 1000, configurable: true });
    Object.defineProperty(scrollEl, "clientHeight", { value: 200, configurable: true });
    fireEvent.scroll(scrollEl);

    vi.mocked(Element.prototype.scrollIntoView).mockClear();
    rerender(<MessageList messages={[...initial, { id: "m2", role: "user", content: "yo" }]} />);
    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled();
  });

  it("shows the working indicator with the live edge while running and not streaming", () => {
    const messages: Message[] = [{ id: "m1", role: "user", content: "hi" }];
    const { container } = render(<MessageList messages={messages} isRunning={true} />);
    expect(screen.getByText("Agent is thinking…")).toBeInTheDocument();
    expect(screen.getByText("Agent is thinking…").closest(".live-edge")).not.toBeNull();
    expect(container.querySelectorAll(".live-edge")).toHaveLength(1);
  });

  it("hides the working indicator while streaming text", () => {
    const messages: Message[] = [{ id: "m1", role: "assistant", content: "" }];
    render(<MessageList messages={messages} isRunning={true} isStreaming={true} />);
    expect(screen.queryByText("Agent is thinking…")).not.toBeInTheDocument();
  });

  it("hides the working indicator when the last message is a running tool line", () => {
    const messages: Message[] = [
      {
        id: "tc-1",
        role: "activity",
        activityType: "tool_call",
        content: { name: "create_workflow_task", status: "running" },
      } as Message,
    ];
    render(<MessageList messages={messages} isRunning={true} />);
    expect(screen.queryByText("Agent is thinking…")).not.toBeInTheDocument();
  });

  it("hides the working indicator when the last message is a live reasoning panel", () => {
    const messages: Message[] = [
      {
        id: "r-1",
        role: "activity",
        activityType: "reasoning",
        content: { text: "Planning the steps." },
      } as Message,
    ];
    render(<MessageList messages={messages} isRunning={true} />);
    expect(screen.queryByText("Agent is thinking…")).not.toBeInTheDocument();
  });

  it("only the last message receives isThinking=true while running and not streaming", () => {
    const messages: Message[] = [
      { id: "m1", role: "user", content: "hi" },
      {
        id: "r-1",
        role: "activity",
        activityType: "reasoning",
        content: { text: "Planning the steps." },
      } as Message,
    ];
    render(<MessageList messages={messages} isRunning={true} />);
    expect(screen.getByTestId("bubble-m1")).toHaveAttribute("data-thinking", "false");
    expect(screen.getByTestId("bubble-r-1")).toHaveAttribute("data-thinking", "true");
  });

  it("does not mark the last message as thinking once text is streaming", () => {
    const messages: Message[] = [
      {
        id: "r-1",
        role: "activity",
        activityType: "reasoning",
        content: { text: "Planning the steps." },
      } as Message,
      { id: "m2", role: "assistant", content: "" },
    ];
    render(<MessageList messages={messages} isRunning={true} isStreaming={true} />);
    expect(screen.getByTestId("bubble-r-1")).toHaveAttribute("data-thinking", "false");
    expect(screen.getByTestId("bubble-m2")).toHaveAttribute("data-thinking", "false");
  });

  it("wraps each task's messages in a group where the active task changes", () => {
    const messages: Message[] = [
      { id: "m1", role: "user", content: "go" },
      { id: "m2", role: "assistant", content: "on task A" },
      { id: "m3", role: "assistant", content: "on task B" },
    ];
    const messageTasks = new Map([
      ["m2", "task-a"],
      ["m3", "task-b"],
    ]);
    const tasksById = new Map<string, WorkflowTask>([
      ["task-a", makeTask("task-a", "Task A")],
      ["task-b", makeTask("task-b", "Task B")],
    ]);
    render(<MessageList messages={messages} messageTasks={messageTasks} tasksById={tasksById} />);
    expect(screen.getByText("Task A")).toBeInTheDocument();
    expect(screen.getByText("Task B")).toBeInTheDocument();
  });

  it("anchors only the first group for each task", () => {
    const messages: Message[] = [
      { id: "m1", role: "assistant", content: "a1" },
      { id: "m2", role: "assistant", content: "a2" },
    ];
    const messageTasks = new Map([
      ["m1", "task-a"],
      ["m2", "task-a"],
    ]);
    const tasksById = new Map<string, WorkflowTask>([["task-a", makeTask("task-a", "Task A")]]);
    const { container } = render(
      <MessageList messages={messages} messageTasks={messageTasks} tasksById={tasksById} />
    );
    // Consecutive messages share the task, so there is a single, anchored group.
    expect(container.querySelectorAll("#wf-task-group-task-a")).toHaveLength(1);
    expect(screen.getAllByText("Task A")).toHaveLength(1);
  });

  it("keeps an unmapped activity bubble inside its task group", () => {
    // A2UI / approval / MCP activity bubbles, reasoning and tool messages carry
    // generated ids absent from messageTasks. They must inherit the surrounding
    // task instead of splitting the run into duplicate headings.
    const messages: Message[] = [
      { id: "evt-1", role: "assistant", content: "rendering a surface" },
      // Synthesized A2UI activity bubble — id is not an ADK event id.
      {
        id: "a2ui-surface-s1-tc-1",
        role: "activity",
        activityType: "a2ui",
        content: {},
      } as Message,
      { id: "evt-2", role: "assistant", content: "done" },
    ];
    const messageTasks = new Map([
      ["evt-1", "task-a"],
      ["evt-2", "task-a"],
    ]);
    const tasksById = new Map<string, WorkflowTask>([["task-a", makeTask("task-a", "Task A")]]);
    const { container } = render(
      <MessageList messages={messages} messageTasks={messageTasks} tasksById={tasksById} />
    );
    // The unmapped activity bubble does not break the run: one heading, one anchor.
    expect(screen.getAllByText("Task A")).toHaveLength(1);
    expect(container.querySelectorAll("#wf-task-group-task-a")).toHaveLength(1);
  });

  it("leaves leading pre-task messages ungrouped", () => {
    const messages: Message[] = [
      { id: "m0", role: "user", content: "kick off" },
      { id: "evt-1", role: "assistant", content: "on task A" },
    ];
    // Only the task message is mapped; the opening prompt has no task.
    const messageTasks = new Map([["evt-1", "task-a"]]);
    const tasksById = new Map<string, WorkflowTask>([["task-a", makeTask("task-a", "Task A")]]);
    const { container } = render(
      <MessageList messages={messages} messageTasks={messageTasks} tasksById={tasksById} />
    );
    // The opening prompt stays outside any group; only task A is wrapped.
    expect(container.querySelectorAll("#wf-task-group-task-a")).toHaveLength(1);
    expect(screen.getByTestId("bubble-m0")).toBeInTheDocument();
    const group = container.querySelector("#wf-task-group-task-a");
    expect(group?.querySelector('[data-testid="bubble-m0"]')).toBeNull();
  });

  it("numbers each group from taskIndexById", () => {
    const messages: Message[] = [
      { id: "m1", role: "assistant", content: "a" },
      { id: "m2", role: "assistant", content: "b" },
    ];
    const messageTasks = new Map([
      ["m1", "task-a"],
      ["m2", "task-b"],
    ]);
    const tasksById = new Map<string, WorkflowTask>([
      ["task-a", makeTask("task-a", "Task A")],
      ["task-b", makeTask("task-b", "Task B")],
    ]);
    const taskIndexById = new Map([
      ["task-a", 1],
      ["task-b", 2],
    ]);
    render(
      <MessageList
        messages={messages}
        messageTasks={messageTasks}
        tasksById={tasksById}
        taskIndexById={taskIndexById}
      />
    );
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("does not remount a task group's bubbles when a lagging messageTasks update changes the run's leading message", () => {
    const messages: Message[] = [
      { id: "m0", role: "user", content: "kick off" },
      { id: "m1", role: "assistant", content: "working" },
      { id: "appr-1", role: "activity", activityType: "approval", content: {} } as Message,
    ];
    const tasksById = new Map<string, WorkflowTask>([["task-a", makeTask("task-a", "Task A")]]);

    const { rerender } = render(
      <MessageList
        messages={messages}
        messageTasks={new Map([["m1", "task-a"]])}
        tasksById={tasksById}
      />
    );
    mountSpy.mockClear();

    // messageTasks "catches up" and now also maps the earlier message to the
    // same task — this changes the run's leading message from m1 to m0
    // without changing the task itself, which must not remount the group.
    rerender(
      <MessageList
        messages={messages}
        messageTasks={
          new Map([
            ["m0", "task-a"],
            ["m1", "task-a"],
          ])
        }
        tasksById={tasksById}
      />
    );

    expect(mountSpy).not.toHaveBeenCalledWith("appr-1");
  });

  it("derives pendingToolCallIds and toolResultContentByCallId for MessageBubble", () => {
    const messages: Message[] = [
      { id: "t1", role: "tool", toolCallId: "tc-1", content: "answered" } as Message,
      { id: "m1", role: "user", content: "hi" },
    ];
    render(
      <MessageList
        messages={messages}
        pendingRenderCalls={[{ toolCallId: "tc-2", surfaceId: "s2" }]}
      />
    );
    expect(screen.getByTestId("bubble-m1")).toHaveAttribute("data-pending", "tc-2");
    expect(screen.getByTestId("bubble-m1")).toHaveAttribute("data-tool-content", "answered");
  });

  it("renders no task groups when messageTasks is omitted", () => {
    const messages: Message[] = [
      { id: "m1", role: "user", content: "hi" },
      { id: "m2", role: "assistant", content: "hello" },
    ];
    const { container } = render(<MessageList messages={messages} />);
    expect(container.querySelector('[id^="wf-task-group-"]')).toBeNull();
  });
});
