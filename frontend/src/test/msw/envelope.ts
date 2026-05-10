import { HttpResponse } from "msw";

const META = {
  request_id: "test-request-id",
  received_at: "2026-05-10T00:00:00.000Z",
  responded_at: "2026-05-10T00:00:00.000Z",
};

export function envelope<T>(data: T, status = 200) {
  return HttpResponse.json({ meta: META, data, error: null }, { status });
}

export function envelopeErr(
  code: string,
  message: string,
  status: number,
  details: Record<string, unknown> | null = null
) {
  return HttpResponse.json(
    { meta: META, data: null, error: { code, message, details } },
    { status }
  );
}
