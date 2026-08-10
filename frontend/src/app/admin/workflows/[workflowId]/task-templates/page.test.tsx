import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { DEVELOPER, REQUESTER } from "@/test/auth-state";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor, within } from "@/test/test-utils";
import WorkflowTaskTemplatesPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

beforeEach(() => {
  vi.mocked(useParams).mockReturnValue({ workflowId: "wf-1" });
});

describe("WorkflowTaskTemplatesPage", () => {
  it("names the parent workflow in the breadcrumb trail", async () => {
    render(<WorkflowTaskTemplatesPage />);
    const nav = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(await within(nav).findByRole("link", { name: "my-workflow" })).toHaveAttribute(
      "href",
      "/admin/workflows/wf-1"
    );
  });

  it("renders template row after load", async () => {
    render(<WorkflowTaskTemplatesPage />);
    await waitFor(() => expect(screen.getByText("Template Step 1")).toBeInTheDocument());
  });

  it("links the template title to the template detail route", async () => {
    render(<WorkflowTaskTemplatesPage />);
    await waitFor(() => screen.getByText("Template Step 1"));
    const link = screen.getByRole("link", { name: "Template Step 1" });
    expect(link).toHaveAttribute("href", "/admin/workflows/wf-1/task-templates/tmpl-1");
  });

  it("renders a Depends on column resolving dependency ids to titles", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id/task-templates", () =>
        envelope([
          {
            id: "tmpl-1",
            workflowId: "wf-1",
            title: "Template Step 1",
            description: null,
            dependsOnIds: [],
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
          },
          {
            id: "tmpl-2",
            workflowId: "wf-1",
            title: "Template Step 2",
            description: null,
            dependsOnIds: ["tmpl-1"],
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
          },
        ])
      )
    );

    render(<WorkflowTaskTemplatesPage />);
    expect(await screen.findByText("Depends on")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Template Step 2")).toBeInTheDocument());
    // "Template Step 1" appears twice: once as its own title, once as
    // tmpl-2's resolved dependency chip.
    expect(screen.getAllByText("Template Step 1")).toHaveLength(2);
  });

  it("highlights the dependency's own row while its chip is hovered", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id/task-templates", () =>
        envelope([
          {
            id: "tmpl-1",
            workflowId: "wf-1",
            title: "Template Step 1",
            description: null,
            dependsOnIds: [],
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
          },
          {
            id: "tmpl-2",
            workflowId: "wf-1",
            title: "Template Step 2",
            description: null,
            dependsOnIds: ["tmpl-1"],
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
          },
        ])
      )
    );

    const { container } = render(<WorkflowTaskTemplatesPage />);
    await waitFor(() => screen.getByText("Template Step 2"));
    const dependencyRow = container.querySelector('[data-row-key="tmpl-1"]');
    expect(dependencyRow?.className).not.toContain("ring-accent/50");

    // The chip is the second "Template Step 1" — the first is the row's own title.
    await user.hover(screen.getAllByText("Template Step 1")[1]);
    await waitFor(() => expect(dependencyRow?.className).toContain("ring-accent/50"));

    await user.unhover(screen.getAllByText("Template Step 1")[1]);
    await waitFor(() => expect(dependencyRow?.className).not.toContain("ring-accent/50"));
  });

  it("fetches every template in one unpaginated request", async () => {
    const urls: string[] = [];
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id/task-templates", ({ request }) => {
        urls.push(request.url);
        return envelope([]);
      })
    );

    render(<WorkflowTaskTemplatesPage />);
    await waitFor(() => expect(urls).not.toHaveLength(0));
    const params = new URL(urls[0]).searchParams;
    expect(params.get("limit")).toBe("1000");
    // The shared list helper always sends offset; it just never leaves 0 now.
    expect(params.get("offset")).toBe("0");
    expect(screen.queryByRole("button", { name: /previous/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /next/i })).not.toBeInTheDocument();
  });

  it("has no Status column (templates carry no lifecycle)", async () => {
    render(<WorkflowTaskTemplatesPage />);
    await waitFor(() => screen.getByText("Template Step 1"));
    expect(screen.queryByText("Status")).not.toBeInTheDocument();
  });

  it("calls delete api after confirm", async () => {
    const user = userEvent.setup();
    const deleteSpy = vi.fn(() => envelope(null));
    server.use(
      http.delete("http://localhost:8000/api/v1/workflow-task-templates/:templateId", deleteSpy)
    );

    render(<WorkflowTaskTemplatesPage />, { preloadedState: DEVELOPER });
    await waitFor(() => screen.getByText("Template Step 1"));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
  });

  it("hides '+ Add task' and per-row Delete from a requester", async () => {
    render(<WorkflowTaskTemplatesPage />, { preloadedState: REQUESTER });
    await waitFor(() => screen.getByText("Template Step 1"));
    expect(screen.queryByRole("link", { name: /\+ add task/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
  });

  it("shows an error toast when load fails", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows/:id/task-templates", () =>
        envelopeErr("INTERNAL_ERROR", "Internal server error", 500)
      )
    );
    render(<WorkflowTaskTemplatesPage />);
    await waitFor(() =>
      expect(store.getState().toast.items.at(-1)).toMatchObject({
        message: "Internal server error",
        variant: "error",
      })
    );
  });
});
