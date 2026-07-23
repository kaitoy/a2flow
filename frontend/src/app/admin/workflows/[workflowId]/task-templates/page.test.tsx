import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http } from "msw";
import { useParams } from "next/navigation";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
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
            position: 0,
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
            position: 1,
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

    render(<WorkflowTaskTemplatesPage />);
    await waitFor(() => screen.getByText("Template Step 1"));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = screen.getByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /delete/i }));
    expect(deleteSpy).toHaveBeenCalled();
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
