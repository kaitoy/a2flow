import type { Message } from "@ag-ui/core";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import type { WorkflowTask } from "@/lib/api";
import { MessageList } from "./MessageList";

const makeTask = (id: string, title: string): WorkflowTask =>
  ({
    id,
    workflowSessionId: "ws",
    title,
    status: "in_progress",
    position: 0,
    dependsOnIds: [],
    toolBindings: [],
  }) as WorkflowTask;

vi.mock("./MessageBubble", () => ({
  MessageBubble: ({
    message,
    isStreaming,
    avatar,
  }: {
    message: Message;
    isStreaming: boolean;
    avatar?: ReactNode;
  }) => (
    <div data-testid={`bubble-${message.id}`} data-streaming={String(isStreaming)}>
      {avatar}
    </div>
  ),
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

  it("shows the working indicator while running and not streaming", () => {
    const messages: Message[] = [{ id: "m1", role: "user", content: "hi" }];
    render(<MessageList messages={messages} isRunning={true} />);
    expect(screen.getByText("エージェントが考えています…")).toBeInTheDocument();
  });

  it("hides the working indicator while streaming text", () => {
    const messages: Message[] = [{ id: "m1", role: "assistant", content: "" }];
    render(<MessageList messages={messages} isRunning={true} isStreaming={true} />);
    expect(screen.queryByText("エージェントが考えています…")).not.toBeInTheDocument();
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
    expect(screen.queryByText("エージェントが考えています…")).not.toBeInTheDocument();
  });

  it("inserts a task divider where the active task changes", () => {
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

  it("anchors only the first divider for each task", () => {
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
    // Consecutive messages share the task, so there is a single, anchored divider.
    expect(container.querySelectorAll("#wf-task-divider-task-a")).toHaveLength(1);
    expect(screen.getAllByText("Task A")).toHaveLength(1);
  });

  it("renders no dividers when messageTasks is omitted", () => {
    const messages: Message[] = [
      { id: "m1", role: "user", content: "hi" },
      { id: "m2", role: "assistant", content: "hello" },
    ];
    const { container } = render(<MessageList messages={messages} />);
    expect(container.querySelector('[id^="wf-task-divider-"]')).toBeNull();
  });
});
