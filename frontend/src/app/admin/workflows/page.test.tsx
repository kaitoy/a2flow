import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import WorkflowsPage from "./page";

const pushMock = vi.fn();

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

describe("WorkflowsPage", () => {
  it("renders workflow row after load", async () => {
    render(<WorkflowsPage />);
    await waitFor(() => expect(screen.getByText("My Workflow")).toBeInTheDocument());
  });

  it("renders a Run button per workflow", async () => {
    render(<WorkflowsPage />);
    await waitFor(() => screen.getByText("My Workflow"));
    expect(screen.getByRole("button", { name: "Run" })).toBeInTheDocument();
  });

  it("navigates to the new session after Run succeeds", async () => {
    pushMock.mockClear();
    const user = userEvent.setup();
    render(<WorkflowsPage />);
    await waitFor(() => screen.getByText("My Workflow"));
    await user.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/workflow-sessions/ws-1"));
  });

  it("shows an error banner when Run fails", async () => {
    server.use(
      http.post(
        "http://localhost:8000/workflows/:id/execute",
        () => new HttpResponse(null, { status: 500 })
      )
    );
    const user = userEvent.setup();
    render(<WorkflowsPage />);
    await waitFor(() => screen.getByText("My Workflow"));
    await user.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(screen.getByText(/500/)).toBeInTheDocument());
  });

  it("calls delete api after confirm", async () => {
    const user = userEvent.setup();
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/workflows/:id", deleteSpy));

    render(<WorkflowsPage />);
    await waitFor(() => screen.getByText("My Workflow"));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });
});
