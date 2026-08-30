import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { OUTBOUND_EMAIL_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import AuditOutboundEmailDetailPage from "./page";

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
  useParams: () => ({ emailId: "email-1" }),
  useRouter: () => ({ push: vi.fn() }),
}));

describe("AuditOutboundEmailDetailPage", () => {
  it("shows the message body in full", async () => {
    render(<AuditOutboundEmailDetailPage />);
    await waitFor(() =>
      expect(screen.getByText("Please review the pending approval.")).toBeInTheDocument()
    );
  });

  it("shows the recipient and delivery status", async () => {
    render(<AuditOutboundEmailDetailPage />);
    await waitFor(() => expect(screen.getByText("alice@example.com")).toBeInTheDocument());
    expect(screen.getByText("sent")).toBeInTheDocument();
  });

  it("shows the recorded reason on a dead letter", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/outbound-emails/:id", () =>
        envelope({
          ...OUTBOUND_EMAIL_1,
          status: "failed",
          sentAt: null,
          lastError: "relay refused the recipient",
        })
      )
    );
    render(<AuditOutboundEmailDetailPage />);
    await waitFor(() =>
      expect(screen.getByText("relay refused the recipient")).toBeInTheDocument()
    );
    expect(screen.getByText("failed")).toBeInTheDocument();
  });

  it("shows an access-denied state when the caller lacks the role", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/outbound-emails/:id", () =>
        envelopeErr("FORBIDDEN", "Forbidden", 403)
      )
    );
    render(<AuditOutboundEmailDetailPage />);
    await waitFor(() => expect(screen.getByText("Access denied")).toBeInTheDocument());
  });
});
