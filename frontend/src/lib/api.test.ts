import { HttpAgent } from "@ag-ui/client";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import {
  createChatAgent,
  getSessionMessages,
  getWorkflowSessionMessages,
  listSessions,
} from "./api";

const BASE = "http://localhost:8000";

describe("listSessions", () => {
  it("returns parsed session list", async () => {
    const result = await listSessions();
    expect(result).toHaveLength(2);
    expect(result[0].id).toBe("sess-1");
  });

  it("throws on server error", async () => {
    server.use(http.get(`${BASE}/api/v1/sessions`, () => HttpResponse.json(null, { status: 500 })));
    await expect(listSessions()).rejects.toThrow("500");
  });
});

describe("getSessionMessages", () => {
  it("returns messages array", async () => {
    const result = await getSessionMessages("sess-1");
    expect(Array.isArray(result)).toBe(true);
  });

  it("calls the correct URL", async () => {
    let calledUrl = "";
    server.use(
      http.get(`${BASE}/api/v1/sessions/:sessionId/messages`, ({ request }) => {
        calledUrl = request.url;
        return envelope([]);
      })
    );
    await getSessionMessages("my-session");
    expect(calledUrl).toContain("/sessions/my-session/messages");
  });

  it("throws on 404", async () => {
    server.use(
      http.get(`${BASE}/api/v1/sessions/:sessionId/messages`, () =>
        HttpResponse.json(null, { status: 404 })
      )
    );
    await expect(getSessionMessages("missing")).rejects.toThrow("404");
  });
});

describe("getWorkflowSessionMessages", () => {
  it("fetches the workflow-session-scoped messages URL", async () => {
    let calledUrl = "";
    server.use(
      http.get(`${BASE}/api/v1/workflow-sessions/:wsId/messages`, ({ request }) => {
        calledUrl = request.url;
        return envelope([]);
      })
    );
    const result = await getWorkflowSessionMessages("ws-1");
    expect(Array.isArray(result)).toBe(true);
    expect(calledUrl).toContain("/workflow-sessions/ws-1/messages");
  });
});

describe("createChatAgent", () => {
  it("returns an HttpAgent with correct url and threadId", () => {
    const agent = createChatAgent("my-session");
    expect(agent).toBeInstanceOf(HttpAgent);
    expect((agent as unknown as { url: string }).url).toBe(`${BASE}/api/v1/agent`);
    expect((agent as unknown as { threadId: string }).threadId).toBe("my-session");
  });
});
