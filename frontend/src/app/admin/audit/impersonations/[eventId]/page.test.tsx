import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { IMPERSONATION_EVENT_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import AuditImpersonationDetailPage from "./page";

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
  useParams: () => ({ eventId: "impersonation-1" }),
  useRouter: () => ({ push: vi.fn() }),
}));

describe("AuditImpersonationDetailPage", () => {
  it("shows an open session as Active", async () => {
    render(<AuditImpersonationDetailPage />);
    await waitFor(() => expect(screen.getByText("Active")).toBeInTheDocument());
  });

  it("links both parties to their user detail pages", async () => {
    render(<AuditImpersonationDetailPage />);
    await screen.findByText("Active");
    const hrefs = screen.getAllByRole("link").map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("/admin/users/user-1");
    expect(hrefs).toContain("/admin/users/user-2");
  });

  it("shows the impersonated account's tenant", async () => {
    render(<AuditImpersonationDetailPage />);
    const link = await screen.findByRole("link", { name: "tenant-1" });
    expect(link).toHaveAttribute("href", "/admin/tenants/tenant-1");
  });

  it("shows a closed session as Ended with its end instant", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/impersonation-events/:id", () =>
        envelope({ ...IMPERSONATION_EVENT_1, endedAt: "2026-01-01T01:00:00Z" })
      )
    );
    render(<AuditImpersonationDetailPage />);
    await waitFor(() => expect(screen.getByText("Ended")).toBeInTheDocument());
  });

  it("shows an access-denied state when the caller lacks the role", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/impersonation-events/:id", () =>
        envelopeErr("FORBIDDEN", "Forbidden", 403)
      )
    );
    render(<AuditImpersonationDetailPage />);
    await waitFor(() => expect(screen.getByText("Access denied")).toBeInTheDocument());
  });
});
