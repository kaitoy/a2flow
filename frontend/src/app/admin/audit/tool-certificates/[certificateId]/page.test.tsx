import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { TOOL_CERTIFICATE_1, TOOL_CERTIFICATE_INITIATOR } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import AuditToolCertificateDetailPage from "./page";

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
  useParams: () => ({ certificateId: "certificate-1" }),
  useRouter: () => ({ push: vi.fn() }),
}));

describe("AuditToolCertificateDetailPage", () => {
  it("shows the serial and a live grant", async () => {
    render(<AuditToolCertificateDetailPage />);
    // The serial appears twice — as the trailing breadcrumb and as a field.
    await waitFor(() => expect(screen.getAllByText("123456789")).toHaveLength(2));
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("never renders key material", async () => {
    render(<AuditToolCertificateDetailPage />);
    await waitFor(() => expect(screen.getAllByText("123456789").length).toBeGreaterThan(0));
    expect(screen.queryByText(/BEGIN CERTIFICATE/)).not.toBeInTheDocument();
    expect(screen.queryByText(/private key/i)).not.toBeInTheDocument();
  });

  it("links to the approval it was issued for", async () => {
    render(<AuditToolCertificateDetailPage />);
    const link = await screen.findByRole("link", { name: "appr-1" });
    expect(link).toHaveAttribute("href", "/admin/approvals/appr-1");
    expect(screen.getByText("Approver")).toBeInTheDocument();
  });

  it("names the run initiator and links to no approval for a self-granted one", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/mcp-tool-certificates/:id", () =>
        envelope(TOOL_CERTIFICATE_INITIATOR)
      )
    );
    render(<AuditToolCertificateDetailPage />);
    await waitFor(() => expect(screen.getByText("Run initiator")).toBeInTheDocument());
    // There is no approval record behind this grant, so nothing links to one.
    expect(screen.queryByRole("link", { name: "appr-1" })).not.toBeInTheDocument();
  });

  it("shows a revoked certificate with its reason", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/mcp-tool-certificates/:id", () =>
        envelope({
          ...TOOL_CERTIFICATE_1,
          revokedAt: "2026-01-01T02:00:00Z",
          revocationReason: "task_finished",
        })
      )
    );
    render(<AuditToolCertificateDetailPage />);
    await waitFor(() => expect(screen.getByText("Revoked")).toBeInTheDocument());
    expect(screen.getByText("task finished")).toBeInTheDocument();
  });

  it("shows an access-denied state when the caller lacks the role", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/mcp-tool-certificates/:id", () =>
        envelopeErr("FORBIDDEN", "Forbidden", 403)
      )
    );
    render(<AuditToolCertificateDetailPage />);
    await waitFor(() => expect(screen.getByText("Access denied")).toBeInTheDocument());
  });
});
