import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { DEVELOPER, REQUESTER } from "@/test/auth-state";
import { envelope } from "@/test/msw/envelope";
import { KNOWLEDGE_BASE_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import KnowledgeBaseDetailPage from "./page";

function setup() {
  vi.mocked(useParams).mockReturnValue({ knowledgeBaseId: "kb-1" });
}

describe("KnowledgeBaseDetailPage", () => {
  it("shows the knowledge base with its sources and pages", async () => {
    setup();
    render(<KnowledgeBaseDetailPage />, { preloadedState: DEVELOPER });
    expect(await screen.findByRole("heading", { name: "IT" })).toBeInTheDocument();
    expect(screen.getByDisplayValue("IT know-how")).toBeInTheDocument();
    expect(await screen.findByText("vpn.pdf")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "VPN setup" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download bundle" })).toBeInTheDocument();
  });

  it("saves edits to the name and description", async () => {
    setup();
    const patched = vi.fn();
    server.use(
      http.patch("http://localhost:8000/api/v1/knowledge-bases/:kbId", async ({ request }) => {
        patched(await request.json());
        return envelope({ ...KNOWLEDGE_BASE_1, name: "Ops" });
      })
    );
    const user = userEvent.setup();
    render(<KnowledgeBaseDetailPage />, { preloadedState: DEVELOPER });
    const name = await screen.findByDisplayValue("IT");

    await user.clear(name);
    await user.type(name, "Ops");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() =>
      expect(patched).toHaveBeenCalledWith({ name: "Ops", description: "IT know-how" })
    );
    expect(await screen.findByRole("heading", { name: "Ops" })).toBeInTheDocument();
  });

  it("renders read-only for a viewer without the developer role", async () => {
    setup();
    render(<KnowledgeBaseDetailPage />, { preloadedState: REQUESTER });
    await screen.findByRole("heading", { name: "IT" });
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    expect(screen.queryByLabelText("Web page URL")).toBeNull();
    expect(await screen.findByText("vpn.pdf")).toBeInTheDocument();
  });
});
