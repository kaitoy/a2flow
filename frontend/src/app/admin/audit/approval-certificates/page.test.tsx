import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { APPROVAL_CERTIFICATE_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import AuditApprovalCertificatesPage from "./page";

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

describe("AuditApprovalCertificatesPage", () => {
  it("renders a certificate after load", async () => {
    render(<AuditApprovalCertificatesPage />);
    await waitFor(() => expect(screen.getByText("123456789")).toBeInTheDocument());
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("links the Serial cell to the certificate's detail page", async () => {
    render(<AuditApprovalCertificatesPage />);
    const link = await screen.findByRole("link", { name: "123456789" });
    expect(link).toHaveAttribute("href", "/admin/audit/approval-certificates/certificate-1");
  });

  it("shows each granted tool as a chip", async () => {
    render(<AuditApprovalCertificatesPage />);
    // The MCP server name resolves through the registry fixture; the tool name
    // is what the signed certificate actually granted.
    await waitFor(() => expect(screen.getByText(/search$/)).toBeInTheDocument());
  });

  it("shows a revoked certificate as Revoked", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/approval-certificates", () =>
        envelope([
          {
            ...APPROVAL_CERTIFICATE_1,
            revokedAt: "2026-01-01T02:00:00Z",
            revocationReason: "task_finished",
          },
        ])
      )
    );
    render(<AuditApprovalCertificatesPage />);
    await waitFor(() => expect(screen.getByText("Revoked")).toBeInTheDocument());
    expect(screen.queryByText("Live")).not.toBeInTheDocument();
  });

  it("shows the audit tabs with Certificates selected", async () => {
    render(<AuditApprovalCertificatesPage />);
    const tab = await screen.findByRole("tab", { name: "Certificates" });
    expect(tab).toHaveAttribute("aria-selected", "true");
  });

  it("shows the empty state when no approval has granted tool authority", async () => {
    server.use(http.get("http://localhost:8000/api/v1/approval-certificates", () => envelope([])));
    render(<AuditApprovalCertificatesPage />);
    await waitFor(() =>
      expect(screen.getByText("No approval has granted tool authority yet.")).toBeInTheDocument()
    );
  });
});
