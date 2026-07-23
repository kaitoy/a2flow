import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { store } from "@/store";
import { envelope, envelopeErr } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { listAgentSkills } from "./api";

const BASE = "http://localhost:8000";
const URL = `${BASE}/api/v1/agent-skills`;

const assignMock = vi.fn();

beforeEach(() => {
  assignMock.mockClear();
  Object.defineProperty(window, "location", {
    value: { ...window.location, assign: assignMock, pathname: "/admin/agent-skills" },
    writable: true,
    configurable: true,
  });
});

afterEach(() => {
  Object.defineProperty(window, "location", {
    value: { ...window.location, pathname: "/" },
    writable: true,
    configurable: true,
  });
});

function lastToast() {
  return store.getState().toast.items.at(-1);
}

describe("global API error toast", () => {
  it("shows the backend's message for a non-2xx envelope error", async () => {
    server.use(http.get(URL, () => envelopeErr("NOT_FOUND", "AgentSkill not found", 404)));

    await expect(listAgentSkills()).rejects.toThrow();

    expect(lastToast()).toMatchObject({ message: "AgentSkill not found", variant: "error" });
  });

  it("shows the backend's message for a 2xx response with a populated error envelope", async () => {
    server.use(http.get(URL, () => envelopeErr("CONFLICT_UNIQUE", "Name already in use", 200)));

    await expect(listAgentSkills()).rejects.toThrow();

    expect(lastToast()).toMatchObject({ message: "Name already in use", variant: "error" });
  });

  it("falls back to a network-error message when there is no response at all", async () => {
    server.use(http.get(URL, () => HttpResponse.error()));

    await expect(listAgentSkills()).rejects.toThrow();

    expect(lastToast()).toMatchObject({
      message: "Unable to reach the server. Please check your connection and try again.",
      variant: "error",
    });
  });

  it("does not show a toast when a 401 triggers the session-expiry redirect", async () => {
    server.use(http.get(URL, () => envelopeErr("UNAUTHENTICATED", "Session expired", 401)));
    const beforeCount = store.getState().toast.items.length;

    await expect(listAgentSkills()).rejects.toThrow();

    expect(assignMock).toHaveBeenCalledWith("/login");
    expect(store.getState().toast.items.length).toBe(beforeCount);
  });

  it("does not show a toast on success", async () => {
    server.use(http.get(URL, () => envelope([])));
    const beforeCount = store.getState().toast.items.length;

    await listAgentSkills();

    expect(store.getState().toast.items.length).toBe(beforeCount);
  });
});
