import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useRouter } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { DEVELOPER, REQUESTER } from "@/test/auth-state";
import { envelope } from "@/test/msw/envelope";
import { KNOWLEDGE_BASE_1 } from "@/test/msw/handlers";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import NewKnowledgeBasePage from "./page";

describe("NewKnowledgeBasePage", () => {
  it("creates the knowledge base and opens it to add sources", async () => {
    const push = vi.fn();
    vi.mocked(useRouter).mockReturnValue({ push } as unknown as ReturnType<typeof useRouter>);
    const created = vi.fn();
    server.use(
      http.post("http://localhost:8000/api/v1/knowledge-bases", async ({ request }) => {
        created(await request.json());
        return envelope({ ...KNOWLEDGE_BASE_1, id: "new-kb-id" }, 201);
      })
    );
    const user = userEvent.setup();
    render(<NewKnowledgeBasePage />, { preloadedState: DEVELOPER });

    await user.type(screen.getByLabelText(/name/i), "Ops");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(created).toHaveBeenCalledWith({ name: "Ops", description: null }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/knowledge-bases/new-kb-id"));
  });

  it("refuses a viewer without the developer role", () => {
    render(<NewKnowledgeBasePage />, { preloadedState: REQUESTER });
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });
});
