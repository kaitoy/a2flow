import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { FailedExecutionEntry } from "@/lib/api";
import { FailureTicker } from "./failure-ticker";

vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const FAILURE: FailedExecutionEntry = {
  executionId: "e1",
  name: "Invoice run 42",
  workflowId: "w1",
  workflowName: "Invoices",
  status: "failed",
  finishedAt: null,
  failedTasks: [
    {
      taskId: "t1",
      title: "Fetch invoice",
      errorKind: "timeout",
      errorMessage: "upstream timed out",
      failedAt: new Date().toISOString(),
    },
  ],
};

describe("FailureTicker", () => {
  it("renders nothing when no run needs triage", () => {
    const { container } = render(<FailureTicker entries={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("links each failed run to its page and names the cause", () => {
    render(<FailureTicker entries={[FAILURE]} />);
    const ticker = screen.getByRole("region", { name: "Needs attention" });
    const link = within(ticker).getByRole("link", { name: /Invoice run 42/ });
    expect(link).toHaveAttribute("href", "/workflow-executions/e1");
    expect(link).toHaveTextContent("timeout");
  });

  it("hides the looping copy from assistive technology and the tab order", () => {
    const { container } = render(<FailureTicker entries={[FAILURE]} />);
    const copy = container.querySelector("ul[aria-hidden='true']");
    expect(copy?.querySelector("a")).toHaveAttribute("tabindex", "-1");
    // Only the first copy is reachable.
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });
});
