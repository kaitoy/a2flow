import { http } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { store } from "@/store";
import { clearUser, setSelectedTenantId } from "@/store/authSlice";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { listAgentSkills } from "./api";

const BASE = "http://localhost:8000";

afterEach(() => {
  store.dispatch(clearUser());
});

describe("X-Tenant-Id header", () => {
  it("attaches the selected tenant to every request", async () => {
    store.dispatch(setSelectedTenantId("tenant-x"));
    let captured: string | null = null;
    server.use(
      http.get(`${BASE}/api/v1/agent-skills`, ({ request }) => {
        captured = request.headers.get("x-tenant-id");
        return envelope([]);
      })
    );
    await listAgentSkills();
    expect(captured).toBe("tenant-x");
  });

  it("omits the header when no tenant is selected", async () => {
    store.dispatch(setSelectedTenantId(null));
    let captured: string | null = "preset";
    server.use(
      http.get(`${BASE}/api/v1/agent-skills`, ({ request }) => {
        captured = request.headers.get("x-tenant-id");
        return envelope([]);
      })
    );
    await listAgentSkills();
    expect(captured).toBeNull();
  });
});
