import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { MCP_TOOL_INVOCATION_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import AuditToolInvocationsPage from "./page";

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

describe("AuditToolInvocationsPage", () => {
  it("renders a recorded decision after load", async () => {
    render(<AuditToolInvocationsPage />);
    await waitFor(() => expect(screen.getByText("search")).toBeInTheDocument());
    expect(screen.getByText("allowed")).toBeInTheDocument();
  });

  it("links the Tool cell to the record's detail page", async () => {
    render(<AuditToolInvocationsPage />);
    const link = await screen.findByRole("link", { name: "search" });
    expect(link).toHaveAttribute("href", "/admin/audit/tool-invocations/invocation-1");
  });

  it("reads the tenant-wide endpoint, not one run's", async () => {
    const seen: string[] = [];
    server.use(
      http.get("http://localhost:8000/api/v1/mcp-tool-invocations", ({ request }) => {
        seen.push(new URL(request.url).pathname);
        return envelope([MCP_TOOL_INVOCATION_1]);
      })
    );
    render(<AuditToolInvocationsPage />);
    await waitFor(() => expect(seen).toContain("/api/v1/mcp-tool-invocations"));
  });

  it("shows the audit tabs with Tool Invocations selected", async () => {
    render(<AuditToolInvocationsPage />);
    const tab = await screen.findByRole("tab", { name: "Tool Invocations" });
    expect(tab).toHaveAttribute("aria-selected", "true");
  });

  it("shows the empty state when nothing has been recorded", async () => {
    server.use(http.get("http://localhost:8000/api/v1/mcp-tool-invocations", () => envelope([])));
    render(<AuditToolInvocationsPage />);
    await waitFor(() =>
      expect(screen.getByText("No MCP tool calls have been recorded yet.")).toBeInTheDocument()
    );
  });
});
