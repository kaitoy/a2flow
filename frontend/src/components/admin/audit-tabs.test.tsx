import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { defaultTranslator } from "@/i18n/translate";
import { render, screen } from "@/test/test-utils";
import { AUDIT_TABS, AuditTabs } from "./audit-tabs";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

// Records what each bar asks its pill to do, while keeping the real hook.
const slidingIndicatorCalls = vi.hoisted(() => [] as { activeKey: unknown; fromKey: unknown }[]);
vi.mock("@/hooks/useSlidingIndicator", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/useSlidingIndicator")>();
  return {
    ...actual,
    useSlidingIndicator: (options: Parameters<typeof actual.useSlidingIndicator>[0]) => {
      slidingIndicatorCalls.push({ activeKey: options.activeKey, fromKey: options.fromKey });
      return actual.useSlidingIndicator(options);
    },
  };
});

describe("AuditTabs", () => {
  it("renders one tab per audit list", () => {
    render(<AuditTabs active="tool-invocations" />);
    for (const tab of AUDIT_TABS) {
      expect(
        screen.getByRole("tab", { name: defaultTranslator.maybe(tab.label) })
      ).toBeInTheDocument();
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
    expect(push).toHaveBeenCalledWith("/audit/outbound-emails");
  });

  it("starts the next list's pill on the tab the click left, once", async () => {
    // Each list renders its own bar, so a switch is an unmount and a fresh mount.
    const first = render(<AuditTabs active="tool-invocations" />);
    await userEvent.click(screen.getByRole("tab", { name: "Emails" }));
    first.unmount();

    slidingIndicatorCalls.length = 0;
    const second = render(<AuditTabs active="outbound-emails" />);
    expect(slidingIndicatorCalls.at(-1)).toEqual({
      activeKey: "outbound-emails",
      fromKey: "tool-invocations",
    });
    second.unmount();

    // Arriving any other way (sidebar, back/forward) places the pill directly.
    slidingIndicatorCalls.length = 0;
    render(<AuditTabs active="outbound-emails" />);
    expect(slidingIndicatorCalls.at(-1)).toEqual({
      activeKey: "outbound-emails",
      fromKey: undefined,
    });
  });
});
