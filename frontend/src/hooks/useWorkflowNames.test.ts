import { renderHook, waitFor } from "@testing-library/react";
import { http } from "msw";
import { describe, expect, it } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { useWorkflowNames } from "./useWorkflowNames";

/** Build the minimal workflow shape the hook reads out of the list response. */
function workflow(id: string, name: string) {
  return {
    id,
    name,
    tenantId: "tenant-1",
    description: null,
    generatedDescription: null,
    agentSkillId: "skill-1",
    sessionId: "design-session-id",
    agentSkillCommitSha: "a".repeat(40),
    status: "published",
    generationError: null,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
  };
}

describe("useWorkflowNames", () => {
  it("resolves the given ids to workflow names through an id:in: filter", async () => {
    const queries: (string | null)[] = [];
    server.use(
      http.get("http://localhost:8000/api/v1/workflows", ({ request }) => {
        queries.push(new URL(request.url).searchParams.get("q"));
        return envelope([
          workflow("wf-1", "Invoice intake"),
          workflow("wf-2", "Vendor onboarding"),
        ]);
      })
    );

    const { result } = renderHook(() => useWorkflowNames(["wf-1", "wf-2"]));

    await waitFor(() => expect(result.current.get("wf-1")).toBe("Invoice intake"));
    expect(result.current.get("wf-2")).toBe("Vendor onboarding");
    expect(queries).toEqual(["id:in:wf-1,wf-2"]);
  });

  it("filters out falsy ids and skips the request when none remain", () => {
    let called = false;
    server.use(
      http.get("http://localhost:8000/api/v1/workflows", () => {
        called = true;
        return envelope([]);
      })
    );

    const { result } = renderHook(() => useWorkflowNames([null, undefined, ""]));

    expect(result.current.size).toBe(0);
    expect(called).toBe(false);
  });

  it("issues one request for a repeated id, regardless of order", async () => {
    const queries: (string | null)[] = [];
    server.use(
      http.get("http://localhost:8000/api/v1/workflows", ({ request }) => {
        queries.push(new URL(request.url).searchParams.get("q"));
        return envelope([workflow("wf-1", "Invoice intake")]);
      })
    );

    const { result, rerender } = renderHook(({ ids }) => useWorkflowNames(ids), {
      initialProps: { ids: ["wf-1", "wf-1"] },
    });
    await waitFor(() => expect(result.current.get("wf-1")).toBe("Invoice intake"));

    // A table re-render with the same ids in a different order must not refetch.
    rerender({ ids: ["wf-1"] });
    expect(queries).toEqual(["id:in:wf-1"]);
  });

  it("keeps the previously resolved names when the lookup fails", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/workflows", () =>
        envelopeErr("internal_error", "boom", 500)
      )
    );

    const { result } = renderHook(() => useWorkflowNames(["wf-1"]));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(result.current.size).toBe(0);
  });
});
