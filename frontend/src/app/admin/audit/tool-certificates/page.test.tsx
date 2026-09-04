import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { TOOL_CERTIFICATE_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import AuditToolCertificatesPage from "./page";

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

/** Serve exactly one certificate, for the cases that assert on a single row. */
function serveOne(overrides: Record<string, unknown> = {}) {
  server.use(
    http.get("http://localhost:8000/api/v1/mcp-tool-certificates", () =>
      envelope([{ ...TOOL_CERTIFICATE_1, ...overrides }])
    )
  );
}

describe("AuditToolCertificatesPage", () => {
  it("renders a certificate after load", async () => {
    serveOne();
    render(<AuditToolCertificatesPage />);
    await waitFor(() => expect(screen.getByText("123456789")).toBeInTheDocument());
    expect(screen.getByText("Live")).toBeInTheDocument();
  });

  it("links the Serial cell to the certificate's detail page", async () => {
    render(<AuditToolCertificatesPage />);
    const link = await screen.findByRole("link", { name: "123456789" });
    expect(link).toHaveAttribute("href", "/admin/audit/tool-certificates/certificate-1");
  });

  it("names the authority behind each grant kind", async () => {
    // The default fixture serves one of each kind, which is the distinction
    // this column exists to make.
    render(<AuditToolCertificatesPage />);
    await waitFor(() => expect(screen.getByText("Approver")).toBeInTheDocument());
    expect(screen.getByText("Run initiator")).toBeInTheDocument();
  });

  it("shows each granted tool as a chip", async () => {
    serveOne();
    render(<AuditToolCertificatesPage />);
    // The MCP server name resolves through the registry fixture; the tool name
    // is what the signed certificate actually granted.
    await waitFor(() => expect(screen.getByText(/search$/)).toBeInTheDocument());
  });

  it("shows a revoked certificate as Revoked", async () => {
    serveOne({ revokedAt: "2026-01-01T02:00:00Z", revocationReason: "task_finished" });
    render(<AuditToolCertificatesPage />);
    await waitFor(() => expect(screen.getByText("Revoked")).toBeInTheDocument());
    expect(screen.queryByText("Live")).not.toBeInTheDocument();
  });

  it("shows the audit tabs with Certificates selected", async () => {
    render(<AuditToolCertificatesPage />);
    const tab = await screen.findByRole("tab", { name: "Certificates" });
    expect(tab).toHaveAttribute("aria-selected", "true");
  });

  it("shows the empty state when no task has been granted tool authority", async () => {
    server.use(http.get("http://localhost:8000/api/v1/mcp-tool-certificates", () => envelope([])));
    render(<AuditToolCertificatesPage />);
    await waitFor(() =>
      expect(screen.getByText("No task has been granted tool authority yet.")).toBeInTheDocument()
    );
  });
});
