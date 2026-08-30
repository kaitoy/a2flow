import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@/test/test-utils";
import { AUDIT_TABS, AuditTabs } from "./audit-tabs";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

describe("AuditTabs", () => {
  it("renders one tab per audit list", () => {
    render(<AuditTabs active="tool-invocations" />);
    for (const tab of AUDIT_TABS) {
      expect(screen.getByRole("tab", { name: tab.label })).toBeInTheDocument();
    }
  });

  it("marks only the active list's tab as selected", () => {
    render(<AuditTabs active="impersonations" />);
    expect(screen.getByRole("tab", { name: "Impersonations" })).toHaveAttribute(
      "aria-selected",
      "true"
    );
    expect(screen.getByRole("tab", { name: "Tool Invocations" })).toHaveAttribute(
      "aria-selected",
      "false"
    );
  });

  it("navigates to the selected list", async () => {
    push.mockClear();
    render(<AuditTabs active="tool-invocations" />);
    await userEvent.click(screen.getByRole("tab", { name: "Emails" }));
    expect(push).toHaveBeenCalledWith("/admin/audit/outbound-emails");
  });
});
