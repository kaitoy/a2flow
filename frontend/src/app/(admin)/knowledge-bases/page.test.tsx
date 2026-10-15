import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { DEVELOPER, REQUESTER } from "@/test/auth-state";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import KnowledgeBasesPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

describe("KnowledgeBasesPage", () => {
  it("links each knowledge base to its detail page", async () => {
    render(<KnowledgeBasesPage />, { preloadedState: DEVELOPER });
    const link = await screen.findByRole("link", { name: "IT" });
    expect(link).toHaveAttribute("href", "/knowledge-bases/kb-1");
    expect(screen.getByText("IT know-how")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "+ Add knowledge base" })).toBeInTheDocument();
  });

  it("deletes a knowledge base after confirmation", async () => {
    const deleted = vi.fn();
    server.use(
      http.delete("http://localhost:8000/api/v1/knowledge-bases/:kbId", ({ params }) => {
        deleted(params.kbId);
        return envelope(null);
      })
    );
    const user = userEvent.setup();
    render(<KnowledgeBasesPage />, { preloadedState: DEVELOPER });
    await screen.findByRole("link", { name: "IT" });

    await user.click(screen.getByRole("button", { name: "Delete" }));
    const buttons = screen.getAllByRole("button", { name: "Delete" });
    await user.click(buttons[buttons.length - 1]);

    await waitFor(() => expect(deleted).toHaveBeenCalledWith("kb-1"));
  });

  it("hides Add and Delete from a viewer without the developer role", async () => {
    render(<KnowledgeBasesPage />, { preloadedState: REQUESTER });
    await screen.findByRole("link", { name: "IT" });
    expect(screen.queryByRole("link", { name: "+ Add knowledge base" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete" })).toBeNull();
  });
});
