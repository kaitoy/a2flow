import { http } from "msw";
import { useParams } from "next/navigation";
import { describe, expect, it, vi } from "vitest";
import { DEVELOPER, REQUESTER } from "@/test/auth-state";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen, waitFor } from "@/test/test-utils";
import NewWorkflowTaskTemplatePage from "./page";

const BASE = "http://localhost:8000";

function setup() {
  vi.mocked(useParams).mockReturnValue({ workflowId: "wf-1" });
}

/** Render the form as a developer — the role adding a task template requires. */
function renderPage() {
  return render(<NewWorkflowTaskTemplatePage />, { preloadedState: DEVELOPER });
}

describe("NewWorkflowTaskTemplatePage", () => {
  it("renders the title and description fields", async () => {
    setup();
    renderPage();

    expect(await screen.findByLabelText(/^title/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save/i })).toBeInTheDocument();
  });

  it("offers the workflow's other templates as dependencies", async () => {
    setup();
    server.use(
      http.get(`${BASE}/api/v1/workflows/:workflowId/task-templates`, () =>
        envelope([
          {
            id: "tmpl-1",
            workflowId: "wf-1",
            title: "Existing Step",
            description: null,
            dependsOnIds: [],
            toolBindings: [],
            createdAt: "2026-01-01T00:00:00Z",
            updatedAt: "2026-01-01T00:00:00Z",
            createdBy: "",
            updatedBy: "",
          },
        ])
      )
    );

    renderPage();

    expect(await screen.findByRole("checkbox", { name: "Existing Step" })).toBeInTheDocument();
  });

  it("refuses the form for a viewer without the developer role", async () => {
    setup();
    const candidates = vi.fn(() => envelope([]));
    server.use(http.get(`${BASE}/api/v1/workflows/:workflowId/task-templates`, candidates));

    render(<NewWorkflowTaskTemplatePage />, { preloadedState: REQUESTER });

    expect(screen.getByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
    // The dependency candidates are only there to fill a picker this viewer
    // never sees, so the list is not fetched at all.
    await waitFor(() => expect(candidates).not.toHaveBeenCalled());
  });
});
