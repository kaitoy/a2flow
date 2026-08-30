import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { MCP_TOOL_INVOCATION_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import AuditToolInvocationDetailPage from "./page";

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
  useParams: () => ({ invocationId: "invocation-1" }),
  useRouter: () => ({ push: vi.fn() }),
}));

describe("AuditToolInvocationDetailPage", () => {
  it("shows the full arguments digest the list truncates", async () => {
    render(<AuditToolInvocationDetailPage />);
    await waitFor(() =>
      expect(screen.getByText(MCP_TOOL_INVOCATION_1.argumentsDigest)).toBeInTheDocument()
    );
  });

  it("shows the proxy's decision", async () => {
    render(<AuditToolInvocationDetailPage />);
    await waitFor(() => expect(screen.getByText("allowed")).toBeInTheDocument());
  });

  it("links to the run the call belonged to", async () => {
    render(<AuditToolInvocationDetailPage />);
    const link = await screen.findByRole("link", { name: "execution-1" });
    expect(link).toHaveAttribute("href", "/admin/workflow-executions/execution-1");
  });

  it("shows an access-denied state when the caller lacks the role", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/mcp-tool-invocations/:id", () =>
        envelopeErr("FORBIDDEN", "Forbidden", 403)
      )
    );
    render(<AuditToolInvocationDetailPage />);
    await waitFor(() => expect(screen.getByText(/access/i)).toBeInTheDocument());
  });

  it("shows the denial reason for a refused call", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/mcp-tool-invocations/:id", () =>
        envelope({
          ...MCP_TOOL_INVOCATION_1,
          decision: "denied",
          denialReason: "no certificate presented",
        })
      )
    );
    render(<AuditToolInvocationDetailPage />);
    await waitFor(() => expect(screen.getByText("no certificate presented")).toBeInTheDocument());
  });
});
