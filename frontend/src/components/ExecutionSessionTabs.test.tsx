import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ExecutionSession } from "@/lib/api";
import { ExecutionSessionTabs } from "./ExecutionSessionTabs";

function session(id: string, status: string, parentId: string | null = null): ExecutionSession {
  return {
    id,
    status,
    parentId,
    workflowExecutionId: "exec-1",
    tenantId: "t",
    createdBy: "u",
    updatedBy: "u",
  } as ExecutionSession;
}

describe("ExecutionSessionTabs", () => {
  it("renders nothing for a run that never branched", () => {
    const { container } = render(
      <ExecutionSessionTabs
        sessions={[session("main", "running")]}
        mainSessionId="main"
        value="main"
        onChange={() => {}}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("labels the main session and numbered branches with their status", () => {
    render(
      <ExecutionSessionTabs
        sessions={[
          session("main", "idle"),
          session("b1", "waiting_for_approval", "main"),
          session("b2", "done", "main"),
        ]}
        mainSessionId="main"
        value="main"
        onChange={() => {}}
      />
    );
    const tabs = screen.getAllByRole("tab").map((tab) => tab.textContent);
    expect(tabs).toEqual(["Main · Idle", "Branch 1 · Waiting for approval", "Branch 2 · Done"]);
    expect(screen.getByRole("tab", { name: "Main · Idle" })).toHaveAttribute(
      "aria-selected",
      "true"
    );
  });

  it("reports the session the viewer switches to", () => {
    const onChange = vi.fn();
    render(
      <ExecutionSessionTabs
        sessions={[session("main", "idle"), session("b1", "running", "main")]}
        mainSessionId="main"
        value="main"
        onChange={onChange}
      />
    );
    fireEvent.click(screen.getByRole("tab", { name: "Branch 1 · Running" }));
    expect(onChange).toHaveBeenCalledWith("b1");
  });
});
