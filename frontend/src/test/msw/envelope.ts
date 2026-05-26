import { HttpResponse } from "msw";

const META = {
  requestId: "test-request-id",
  receivedAt: "2026-05-10T00:00:00.000Z",
  respondedAt: "2026-05-10T00:00:00.000Z",
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
