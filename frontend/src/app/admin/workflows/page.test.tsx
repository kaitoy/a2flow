import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import type { User } from "@/lib/api";
import type { Role } from "@/lib/roles";
import type { RootState } from "@/store";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
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

/** Build a preloaded auth slice for a signed-in user holding the given roles. */
function authState(roles: Role[]): Partial<RootState> {
  return { auth: { user: { id: "u1", roles } as User, status: "authenticated" } };
}

/** Roles granting every workflow action (run plus create/edit/delete). */
const FULL_ACCESS = authState(["developer", "requester"]);

describe("WorkflowsPage", () => {
  it("renders workflow row after load", async () => {
    render(<WorkflowsPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => expect(screen.getByText("my-workflow")).toBeInTheDocument());
  });

  it("renders a Run button per workflow", async () => {
    render(<WorkflowsPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByText("my-workflow"));
    expect(screen.getByRole("button", { name: "Run" })).toBeInTheDocument();
  });

  it("navigates to the new session after Run succeeds", async () => {
    pushMock.mockClear();
    const user = userEvent.setup();
    render(<WorkflowsPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByText("my-workflow"));
    await user.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/workflow-sessions/ws-1"));
  });

  it("shows an error banner when Run fails", async () => {
    server.use(
      http.post(
        "http://localhost:8000/api/v1/workflows/:id/execute",
        () => new HttpResponse(null, { status: 500 })
      )
    );
    const user = userEvent.setup();
    render(<WorkflowsPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByText("my-workflow"));
    await user.click(screen.getByRole("button", { name: "Run" }));
    await waitFor(() => expect(screen.getByText(/500/)).toBeInTheDocument());
  });

  it("calls delete api after confirm", async () => {
    const user = userEvent.setup();
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/workflows/:id", deleteSpy));

    render(<WorkflowsPage />, { preloadedState: FULL_ACCESS });
    await waitFor(() => screen.getByText("my-workflow"));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });

  it("hides the Run button from a user without the requester role", async () => {
    render(<WorkflowsPage />, { preloadedState: authState(["developer"]) });
    await waitFor(() => screen.getByText("my-workflow"));
    expect(screen.queryByRole("button", { name: "Run" })).not.toBeInTheDocument();
  });

  it("hides the add and delete actions from a user without the developer role", async () => {
    render(<WorkflowsPage />, { preloadedState: authState(["requester"]) });
    await waitFor(() => screen.getByText("my-workflow"));
    expect(screen.getByRole("button", { name: "Run" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Add workflow/ })).not.toBeInTheDocument();
  });
});
