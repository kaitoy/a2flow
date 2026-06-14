/**
 * @module api-doc — Scalar API reference viewer.
 *
 * Renders an interactive OpenAPI reference at `/api-doc`. The spec is fetched
 * in-browser from `/openapi.json`, which `next.config.ts` rewrites to the
 * FastAPI backend's live spec. Access is gated by `proxy.ts` (login required).
 */
import { ApiReference } from "@scalar/nextjs-api-reference";

/** Scalar configuration pointing at the backend's live OpenAPI document. */
const config = {
  url: "/openapi.json",
  // Browser tab / document title for the reference page.
  pageTitle: "A2Flow API Reference",
  // Hide the "Ask AI" assistant (Scalar Agent).
  agent: {
    disabled: true,
  },
};

/** Route handler that serves the Scalar API reference HTML page. */
export const GET = ApiReference(config);
