import { HttpResponse, http } from "msw";

const BASE = "http://localhost:8000";

const SKILL_1 = {
  id: "skill-1",
  name: "My Skill",
  repo_url: "https://github.com/example/repo",
  repo_path: "",
  description: null,
  created_at: "2026-01-01T00:00:00+00:00",
  updated_at: "2026-01-01T00:00:00+00:00",
  created_by: "",
  updated_by: "",
};

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

  http.get(`${BASE}/agent-skills`, () => HttpResponse.json([SKILL_1])),

  http.get(`${BASE}/agent-skills/:skillId`, () => HttpResponse.json(SKILL_1)),

  http.post(`${BASE}/agent-skills`, () =>
    HttpResponse.json({ ...SKILL_1, id: "new-skill-id" }, { status: 201 })
  ),

  http.patch(`${BASE}/agent-skills/:skillId`, () => HttpResponse.json(SKILL_1)),

  http.delete(`${BASE}/agent-skills/:skillId`, () => new HttpResponse(null, { status: 204 })),
];
