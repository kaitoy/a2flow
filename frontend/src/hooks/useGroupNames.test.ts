import { renderHook, waitFor } from "@testing-library/react";
import { http } from "msw";
import { describe, expect, it } from "vitest";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { useGroupNames } from "./useGroupNames";

/** Build the minimal user-group shape the hook reads out of the list response. */
function group(id: string, name: string) {
  return {
    id,
    name,
    tenantId: "tenant-1",
    description: null,
    roles: [],
    memberIds: [],
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    createdBy: "",
    updatedBy: "",
  };
}

describe("useGroupNames", () => {
  it("resolves the given ids to group names through an id:in: filter", async () => {
    const queries: (string | null)[] = [];
    server.use(
      http.get("http://localhost:8000/api/v1/user-groups", ({ request }) => {
        queries.push(new URL(request.url).searchParams.get("q"));
        return envelope([group("group-1", "Approvers"), group("group-2", "Reviewers")]);
      })
    );

    const { result } = renderHook(() => useGroupNames(["group-1", "group-2"]));

    await waitFor(() => expect(result.current.get("group-1")).toBe("Approvers"));
    expect(result.current.get("group-2")).toBe("Reviewers");
    expect(queries).toEqual(["id:in:group-1,group-2"]);
  });

  it("filters out falsy ids and skips the request when none remain", () => {
    let called = false;
    server.use(
      http.get("http://localhost:8000/api/v1/user-groups", () => {
        called = true;
        return envelope([]);
      })
    );

    const { result } = renderHook(() => useGroupNames([null, undefined, ""]));

    expect(result.current.size).toBe(0);
    expect(called).toBe(false);
  });

  it("issues one request for a repeated id, regardless of order", async () => {
    const queries: (string | null)[] = [];
    server.use(
      http.get("http://localhost:8000/api/v1/user-groups", ({ request }) => {
        queries.push(new URL(request.url).searchParams.get("q"));
        return envelope([group("group-1", "Approvers")]);
      })
    );

    const { result, rerender } = renderHook(({ ids }) => useGroupNames(ids), {
      initialProps: { ids: ["group-1", "group-1"] },
    });
    await waitFor(() => expect(result.current.get("group-1")).toBe("Approvers"));

    // A table re-render with the same ids in a different order must not refetch.
    rerender({ ids: ["group-1"] });
    expect(queries).toEqual(["id:in:group-1"]);
  });

  it("keeps the previously resolved names when the lookup fails", async () => {
    server.use(
      http.get("http://localhost:8000/api/v1/user-groups", () =>
        envelopeErr("internal_error", "boom", 500)
      )
    );

    const { result } = renderHook(() => useGroupNames(["group-1"]));

    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(result.current.size).toBe(0);
  });
});
