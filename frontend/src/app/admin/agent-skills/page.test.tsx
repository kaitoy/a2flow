import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import AgentSkillsPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

describe("AgentSkillsPage", () => {
  it("shows loading state initially", () => {
    render(<AgentSkillsPage />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("renders skill row after load", async () => {
    render(<AgentSkillsPage />);
    await waitFor(() => expect(screen.getByText("My Skill")).toBeInTheDocument());
  });

  it("shows empty state when no skills", async () => {
    server.use(http.get("http://localhost:8000/api/v1/agent-skills", () => envelope([])));
    render(<AgentSkillsPage />);
    await waitFor(() =>
      expect(screen.getByText("No agent skills registered yet.")).toBeInTheDocument()
    );
  });

  it("shows error banner on api failure", async () => {
    server.use(
      http.get(
        "http://localhost:8000/api/v1/agent-skills",
        () => new HttpResponse(null, { status: 500 })
      )
    );
    render(<AgentSkillsPage />);
    await waitFor(() => expect(screen.getByText(/500/)).toBeInTheDocument());
  });

  it("add skill link is present", async () => {
    render(<AgentSkillsPage />);
    await waitFor(() => screen.getByText("My Skill"));
    expect(screen.getByRole("link", { name: /add skill/i })).toHaveAttribute(
      "href",
      "/admin/agent-skills/new"
    );
  });

  it("calls delete api after confirm", async () => {
    const user = userEvent.setup();
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(http.delete("http://localhost:8000/api/v1/agent-skills/:id", deleteSpy));

    render(<AgentSkillsPage />);
    await waitFor(() => screen.getByText("My Skill"));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });
});
