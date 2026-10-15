import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import { KnowledgePagesPanel } from "./knowledge-pages-panel";

vi.mock("@a2ui/markdown-it", () => ({ renderMarkdown: (s: string) => s }));

describe("KnowledgePagesPanel", () => {
  it("lists the pages", async () => {
    render(<KnowledgePagesPanel knowledgeBaseId="kb-1" />);
    expect(await screen.findByRole("button", { name: "VPN setup" })).toBeInTheDocument();
    expect(screen.getByText("/procedures/vpn-setup.md")).toBeInTheDocument();
    expect(screen.getByText("Procedure")).toBeInTheDocument();
  });

  it("opens a page as rendered Markdown", async () => {
    const requested = vi.fn();
    server.use(
      http.get("http://localhost:8000/api/v1/knowledge-bases/:kbId/pages/*", ({ request }) => {
        requested(new URL(request.url).pathname);
        return envelope({
          path: "/procedures/vpn-setup.md",
          title: "VPN setup",
          content: "Use port 443.",
        });
      })
    );
    const user = userEvent.setup();
    render(<KnowledgePagesPanel knowledgeBaseId="kb-1" />);

    await user.click(await screen.findByRole("button", { name: "VPN setup" }));

    expect(await screen.findByText("Use port 443.")).toBeInTheDocument();
    expect(requested).toHaveBeenCalledWith(
      "/api/v1/knowledge-bases/kb-1/pages/procedures%2Fvpn-setup.md"
    );
  });

  it("re-fetches when the refresh key changes", async () => {
    const listed = vi.fn(() => envelope([]));
    server.use(http.get("http://localhost:8000/api/v1/knowledge-bases/:kbId/pages", listed));
    const { rerender } = render(<KnowledgePagesPanel knowledgeBaseId="kb-1" refreshKey={0} />);
    await waitFor(() => expect(listed).toHaveBeenCalledTimes(1));

    rerender(<KnowledgePagesPanel knowledgeBaseId="kb-1" refreshKey={1} />);

    await waitFor(() => expect(listed).toHaveBeenCalledTimes(2));
  });
});
