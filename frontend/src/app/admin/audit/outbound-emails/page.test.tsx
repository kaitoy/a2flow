import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { OUTBOUND_EMAIL_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import AuditOutboundEmailsPage from "./page";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
  } & React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe("AuditOutboundEmailsPage", () => {
  it("renders a queued message after load", async () => {
    render(<AuditOutboundEmailsPage />);
    await waitFor(() => expect(screen.getByText("alice@example.com")).toBeInTheDocument());
    expect(screen.getByText("Approval requested")).toBeInTheDocument();
    expect(screen.getByText("sent")).toBeInTheDocument();
  });

  it("links the To cell to the message's detail page", async () => {
    render(<AuditOutboundEmailsPage />);
    const link = await screen.findByRole("link", { name: "alice@example.com" });
    expect(link).toHaveAttribute("href", "/admin/audit/outbound-emails/email-1");
  });

  it("shows the recorded reason on a failed delivery", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/outbound-emails", () =>
        envelope([
          {
            ...OUTBOUND_EMAIL_1,
            status: "failed",
            sentAt: null,
            lastError: "relay refused the recipient",
          },
        ])
      )
    );
    render(<AuditOutboundEmailsPage />);
    await waitFor(() =>
      expect(screen.getByText("relay refused the recipient")).toBeInTheDocument()
    );
  });

  it("shows the audit tabs with Emails selected", async () => {
    render(<AuditOutboundEmailsPage />);
    const tab = await screen.findByRole("tab", { name: "Emails" });
    expect(tab).toHaveAttribute("aria-selected", "true");
  });

  it("shows the empty state when nothing has been queued", async () => {
    server.use(http.get("http://localhost:8000/api/v1/outbound-emails", () => envelope([])));
    render(<AuditOutboundEmailsPage />);
    await waitFor(() =>
      expect(screen.getByText("No notification email has been queued yet.")).toBeInTheDocument()
    );
  });
});
