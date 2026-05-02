import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { server } from "@/test/msw/server";
import { SessionList } from "./SessionList";

const defaultProps = {
  userId: "user",
  currentSessionId: null,
  onSelect: vi.fn(),
  onNew: vi.fn(),
};

describe("SessionList", () => {
  it("shows loading state initially", () => {
    render(<SessionList {...defaultProps} />);
    expect(screen.getByText(/Loading/)).toBeInTheDocument();
  });

  it("renders sessions after fetch sorted by last_update_time desc", async () => {
    render(<SessionList {...defaultProps} />);
    await waitFor(() => expect(screen.queryByText(/Loading/)).not.toBeInTheDocument());
    const buttons = screen.getAllByTitle(/sess-/);
    expect(buttons[0]).toHaveAttribute("title", "sess-1");
    expect(buttons[1]).toHaveAttribute("title", "sess-2");
  });

  it("shows No sessions when API returns empty array", async () => {
    server.use(http.get("http://localhost:8000/sessions", () => HttpResponse.json([])));
    render(<SessionList {...defaultProps} />);
    await waitFor(() => expect(screen.getByText("No sessions")).toBeInTheDocument());
  });

  it("calls onSelect with sessionId when clicking non-active session", async () => {
    const onSelect = vi.fn();
    render(<SessionList {...defaultProps} onSelect={onSelect} />);
    await waitFor(() => screen.getAllByTitle(/sess-/));
    await userEvent.click(screen.getAllByTitle(/sess-/)[0]);
    expect(onSelect).toHaveBeenCalledWith("sess-1");
  });

  it("active session button is disabled", async () => {
    render(<SessionList {...defaultProps} currentSessionId="sess-1" />);
    await waitFor(() => screen.getAllByTitle(/sess-/));
    expect(screen.getByTitle("sess-1")).toBeDisabled();
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
      http.get("http://localhost:8000/sessions", () => HttpResponse.json(null, { status: 500 }))
    );
    render(<SessionList {...defaultProps} />);
    await waitFor(() => expect(screen.getByText("No sessions")).toBeInTheDocument());
  });
});
