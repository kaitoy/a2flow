import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import { SessionList } from "./SessionList";

const defaultProps = {
  userId: "user",
  currentSessionId: null,
  onSelect: vi.fn(),
  onNew: vi.fn(),
};

async function clickDeleteForSession(user: ReturnType<typeof userEvent.setup>, sessionId: string) {
  const row = screen.getByRole("button", { name: new RegExp(sessionId) }).closest("div");
  if (!row) throw new Error(`row for ${sessionId} not found`);
  await user.click(within(row as HTMLElement).getByRole("button", { name: "Delete session" }));
}

describe("SessionList", () => {
  it("shows loading state initially", () => {
    render(<SessionList {...defaultProps} />);
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders sessions after fetch sorted by lastUpdateTime desc", async () => {
    render(<SessionList {...defaultProps} />);
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    const buttons = screen.getAllByRole("button", { name: /sess-/ });
    expect(buttons[0]).toHaveTextContent("sess-1");
    expect(buttons[1]).toHaveTextContent("sess-2");
  });

  it("renders session title in place of the id fragment when provided", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/sessions", () =>
        envelope([
          {
            id: "sess-titled",
            userId: "user",
            lastUpdateTime: "2026-05-10T12:00:01.000Z",
            title: "Plan the launch",
          },
        ])
      )
    );
    render(<SessionList {...defaultProps} />);
    await waitFor(() => expect(screen.getByText("Plan the launch")).toBeInTheDocument());
    expect(screen.queryByText(/sess-titl/i)).not.toBeInTheDocument();
  });

  it("shows No sessions when API returns empty array", async () => {
    server.use(http.get("http://localhost:8000/api/v1/sessions", () => envelope([])));
    render(<SessionList {...defaultProps} />);
    await waitFor(() => expect(screen.getByText("No sessions")).toBeInTheDocument());
  });

  it("calls onSelect with sessionId when clicking non-active session", async () => {
    const onSelect = vi.fn();
    render(<SessionList {...defaultProps} onSelect={onSelect} />);
    await waitFor(() => screen.getAllByRole("button", { name: /sess-/ }));
    await userEvent.click(screen.getAllByRole("button", { name: /sess-/ })[0]);
    expect(onSelect).toHaveBeenCalledWith("sess-1");
  });

  it("active session button is disabled", async () => {
    render(<SessionList {...defaultProps} currentSessionId="sess-1" />);
    await waitFor(() => screen.getAllByRole("button", { name: /sess-/ }));
    expect(screen.getByRole("button", { name: /sess-1/ })).toBeDisabled();
  });

  it("New session button calls onNew", async () => {
    const onNew = vi.fn();
    render(<SessionList {...defaultProps} onNew={onNew} />);
    await userEvent.click(screen.getByRole("button", { name: /New session/ }));
    expect(onNew).toHaveBeenCalled();
  });

  it("New session button is disabled when disabled prop is true", () => {
    render(<SessionList {...defaultProps} disabled={true} />);
    expect(screen.getByRole("button", { name: /New session/ })).toBeDisabled();
  });

  it("shows No sessions on API error", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/sessions", () =>
        envelopeErr("INTERNAL_ERROR", "Internal server error", 500)
      )
    );
    render(<SessionList {...defaultProps} />);
    await waitFor(() => expect(screen.getByText("No sessions")).toBeInTheDocument());
  });

  it("renders a Delete session button per session", async () => {
    render(<SessionList {...defaultProps} />);
    await waitFor(() => screen.getAllByRole("button", { name: /sess-/ }));
    expect(screen.getAllByRole("button", { name: "Delete session" })).toHaveLength(2);
  });

  it("opens ConfirmDialog when delete button is clicked", async () => {
    const user = userEvent.setup();
    render(<SessionList {...defaultProps} />);
    await waitFor(() => screen.getAllByRole("button", { name: /sess-/ }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await clickDeleteForSession(user, "sess-1");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("calls delete API and removes session from list after confirm", async () => {
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/sessions/:id", deleteSpy));
    const user = userEvent.setup();
    render(<SessionList {...defaultProps} />);
    await waitFor(() => screen.getAllByRole("button", { name: /sess-/ }));
    await clickDeleteForSession(user, "sess-1");
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    await waitFor(() => expect(deleteSpy).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /sess-1/ })).not.toBeInTheDocument()
    );
    expect(screen.getByRole("button", { name: /sess-2/ })).toBeInTheDocument();
  });

  it("does not call delete API when Cancel is clicked", async () => {
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/sessions/:id", deleteSpy));
    const user = userEvent.setup();
    render(<SessionList {...defaultProps} />);
    await waitFor(() => screen.getAllByRole("button", { name: /sess-/ }));
    await clickDeleteForSession(user, "sess-1");
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(deleteSpy).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /sess-1/ })).toBeInTheDocument();
  });

  it("calls onDeleted with the active session id when active session is deleted", async () => {
    const onDeleted = vi.fn();
    const user = userEvent.setup();
    render(<SessionList {...defaultProps} currentSessionId="sess-1" onDeleted={onDeleted} />);
    await waitFor(() => screen.getAllByRole("button", { name: /sess-/ }));
    await clickDeleteForSession(user, "sess-1");
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("sess-1"));
  });

  it("does not call onDeleted when a non-active session is deleted", async () => {
    const onDeleted = vi.fn();
    const user = userEvent.setup();
    render(<SessionList {...defaultProps} currentSessionId="sess-1" onDeleted={onDeleted} />);
    await waitFor(() => screen.getAllByRole("button", { name: /sess-/ }));
    await clickDeleteForSession(user, "sess-2");
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: /sess-2/ })).not.toBeInTheDocument()
    );
    expect(onDeleted).not.toHaveBeenCalled();
  });

  it("delete buttons are disabled when disabled prop is true", async () => {
    render(<SessionList {...defaultProps} disabled={true} />);
    await waitFor(() => screen.getAllByRole("button", { name: /sess-/ }));
    for (const btn of screen.getAllByRole("button", { name: "Delete session" })) {
      expect(btn).toBeDisabled();
    }
  });
});
