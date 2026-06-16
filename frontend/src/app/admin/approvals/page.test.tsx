import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import ApprovalsPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe("ApprovalsPage", () => {
  it("renders an approval row after load", async () => {
    render(<ApprovalsPage />);
    await waitFor(() => expect(screen.getByText("Deploy to production")).toBeInTheDocument());
  });

  it("links to the workflow session chat", async () => {
    render(<ApprovalsPage />);
    await waitFor(() => screen.getByText("Deploy to production"));
    const link = screen.getByRole("link", { name: "Open chat" });
    expect(link).toHaveAttribute("href", "/workflow-sessions/ws-1");
  });

  it("shows the empty-state message when no approvals exist", async () => {
    server.use(http.get("http://localhost:8000/api/v1/approvals", () => envelope([])));
    render(<ApprovalsPage />);
    await waitFor(() => expect(screen.getByText("No approval requests yet.")).toBeInTheDocument());
  });

  it("shows an error banner when load fails", async () => {
    server.use(
      http.get(
        "http://localhost:8000/api/v1/approvals",
        () => new HttpResponse(null, { status: 500 })
      )
    );
    render(<ApprovalsPage />);
    await waitFor(() => expect(screen.getByText(/500/)).toBeInTheDocument());
  });
});
