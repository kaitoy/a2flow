import { HttpResponse, http } from "msw";

const BASE = "http://localhost:8000";

export const handlers = [
  http.get(`${BASE}/sessions`, () =>
    HttpResponse.json([
      { session_id: "sess-1", user_id: "user", last_update_time: 1700000100 },
      { session_id: "sess-2", user_id: "user", last_update_time: 1700000000 },
    ])
  ),

  http.get(`${BASE}/sessions/:sessionId/messages`, () => HttpResponse.json([])),

  http.post(`${BASE}/sessions`, () =>
    HttpResponse.json({ session_id: "new-session-id" }, { status: 201 })
  ),
];
