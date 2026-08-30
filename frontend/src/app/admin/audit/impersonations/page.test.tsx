import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { IMPERSONATION_EVENT_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import AuditImpersonationsPage from "./page";

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

describe("AuditImpersonationsPage", () => {
  it("renders a recorded session after load", async () => {
    render(<AuditImpersonationsPage />);
    await waitFor(() => expect(screen.getByText("Active")).toBeInTheDocument());
  });

  it("links both parties to their user detail pages", async () => {
    render(<AuditImpersonationsPage />);
    // Wait for the row itself: the breadcrumbs render links immediately, so
    // querying for links before the fetch lands would find only those.
    await screen.findByText("Active");
    const hrefs = screen.getAllByRole("link").map((l) => l.getAttribute("href"));
    expect(hrefs).toContain("/admin/users/user-1");
    expect(hrefs).toContain("/admin/users/user-2");
  });

  it("shows a closed session as Ended", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/impersonation-events", () =>
        envelope([{ ...IMPERSONATION_EVENT_1, endedAt: "2026-01-01T01:00:00Z" }])
      )
    );
    render(<AuditImpersonationsPage />);
    await waitFor(() => expect(screen.getByText("Ended")).toBeInTheDocument());
    expect(screen.queryByText("Active")).not.toBeInTheDocument();
  });

  it("shows the audit tabs with Impersonations selected", async () => {
    render(<AuditImpersonationsPage />);
    const tab = await screen.findByRole("tab", { name: "Impersonations" });
    expect(tab).toHaveAttribute("aria-selected", "true");
  });

  it("shows the empty state when no one has impersonated anyone", async () => {
    server.use(http.get("http://localhost:8000/api/v1/impersonation-events", () => envelope([])));
    render(<AuditImpersonationsPage />);
    await waitFor(() =>
      expect(screen.getByText("No one has acted as another user yet.")).toBeInTheDocument()
    );
  });
});
