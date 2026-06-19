import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import WorkflowSessionsPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

describe("WorkflowSessionsPage", () => {
  it("renders session row after load", async () => {
    render(<WorkflowSessionsPage />);
    await waitFor(() => expect(screen.getByText("My Workflow")).toBeInTheDocument());
  });

  it("resolves the session user ID to the user's name", async () => {
    render(<WorkflowSessionsPage />);
    await waitFor(() => expect(screen.getByText("Alice Smith")).toBeInTheDocument());
  });

  it("renders View tasks link to nested admin route", async () => {
    render(<WorkflowSessionsPage />);
    await waitFor(() => screen.getByText("My Workflow"));
    const link = screen.getByRole("link", { name: "View tasks" });
    expect(link).toHaveAttribute("href", "/admin/workflow-sessions/ws-1/workflow-tasks");
  });

  it("renders Open chat link to the chat page", async () => {
    render(<WorkflowSessionsPage />);
    await waitFor(() => screen.getByText("My Workflow"));
    const link = screen.getByRole("link", { name: "Open chat" });
    expect(link).toHaveAttribute("href", "/workflow-sessions/ws-1");
  });

  it("shows empty-state message when no sessions exist", async () => {
    server.use(http.get("http://localhost:8000/api/v1/workflow-sessions", () => envelope([])));
    render(<WorkflowSessionsPage />);
    await waitFor(() =>
      expect(
        screen.getByText("No workflow sessions yet. Run a workflow to create one.")
      ).toBeInTheDocument()
    );
  });

  it("shows an error banner when load fails", async () => {
    server.use(
      http.get(
        "http://localhost:8000/api/v1/workflow-sessions",
        () => new HttpResponse(null, { status: 500 })
      )
    );
    render(<WorkflowSessionsPage />);
    await waitFor(() => expect(screen.getByText(/500/)).toBeInTheDocument());
  });

  it("calls delete api after confirm", async () => {
    const user = userEvent.setup();
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/workflow-sessions/:id", deleteSpy));

    render(<WorkflowSessionsPage />);
    await waitFor(() => screen.getByText("My Workflow"));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });
});
