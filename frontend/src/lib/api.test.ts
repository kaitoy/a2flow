import { HttpAgent } from "@ag-ui/client";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/msw/server";
import { createChatAgent, createSession, getSessionMessages, listSessions } from "./api";

const BASE = "http://localhost:8000";

describe("listSessions", () => {
  it("returns parsed session list", async () => {
    const result = await listSessions("user");
    expect(result).toHaveLength(2);
    expect(result[0].session_id).toBe("sess-1");
  });

  it("throws on server error", async () => {
    server.use(http.get(`${BASE}/sessions`, () => HttpResponse.json(null, { status: 500 })));
    await expect(listSessions("user")).rejects.toThrow("500");
  });
});

describe("getSessionMessages", () => {
  it("returns messages array", async () => {
    const result = await getSessionMessages("sess-1", "user");
    expect(Array.isArray(result)).toBe(true);
  });

  it("calls the correct URL", async () => {
    let calledUrl = "";
    server.use(
      http.get(`${BASE}/sessions/:sessionId/messages`, ({ request }) => {
        calledUrl = request.url;
        return HttpResponse.json([]);
      })
    );
    await getSessionMessages("my-session", "user");
    expect(calledUrl).toContain("/sessions/my-session/messages");
    expect(calledUrl).toContain("user_id=user");
  });

  it("throws on 404", async () => {
    server.use(
      http.get(`${BASE}/sessions/:sessionId/messages`, () =>
        HttpResponse.json(null, { status: 404 })
      )
    );
    await expect(getSessionMessages("missing", "user")).rejects.toThrow("404");
  });
});

describe("createSession", () => {
  it("returns session_id string", async () => {
    const id = await createSession("user");
    expect(id).toBe("new-session-id");
  });

  it("POSTs with correct JSON body", async () => {
    let body: unknown;
    server.use(
      http.post(`${BASE}/sessions`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ session_id: "x" }, { status: 201 });
      })
    );
    await createSession("test-user");
    expect(body).toEqual({ user_id: "test-user" });
  });

  it("throws on 400", async () => {
    server.use(http.post(`${BASE}/sessions`, () => HttpResponse.json(null, { status: 400 })));
    await expect(createSession("user")).rejects.toThrow("400");
  });
});

describe("createChatAgent", () => {
  it("returns an HttpAgent with correct url and threadId", () => {
    const agent = createChatAgent("my-session");
    expect(agent).toBeInstanceOf(HttpAgent);
    expect((agent as unknown as { url: string }).url).toBe(`${BASE}/agent`);
    expect((agent as unknown as { threadId: string }).threadId).toBe("my-session");
  });
});
