import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import type { RunAgentInput } from "@ag-ui/client";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "@/test/msw/server";
import { createChatAgent } from "./api";
import { RENDER_APPROVAL_TOOL } from "./approvalTool";

/**
 * The client tools and context the backend attaches to the runs it starts
 * itself, where no browser is there to add them.
 *
 * The browser declares `render_approval` and, through the A2UI middleware,
 * `render_a2ui` plus the component catalog and the tool's usage guide. A run
 * the server drives has to offer the model exactly the same, or the agent
 * renders surfaces this frontend cannot draw. So the backend reads them from a
 * committed file, and this test checks that file against the request body a
 * real agent from `api.ts` sends. After changing the middleware config, the
 * catalog, or the approval tool, regenerate it with
 * `UPDATE_CLIENT_CONTRACT=1 pnpm vitest run src/lib/clientContract.test.ts`.
 */
// Resolved from the frontend package root, where vitest runs: under jsdom,
// `import.meta.url` is not a file URL.
const CONTRACT_PATH = resolve(process.cwd(), "../backend/infrastructure/client_contract.json");

/** A minimal SSE stream that ends the run straight away. */
const FINISHED_RUN = [
  { type: "RUN_STARTED", threadId: "t", runId: "r" },
  { type: "RUN_FINISHED", threadId: "t", runId: "r" },
]
  .map((event) => `data: ${JSON.stringify(event)}\n\n`)
  .join("");

describe("client contract", () => {
  it("matches the tools and context the frontend sends with every run", async () => {
    let sent: RunAgentInput | undefined;
    server.use(
      http.post("*/api/v1/agent", async ({ request }) => {
        sent = (await request.json()) as RunAgentInput;
        return new HttpResponse(FINISHED_RUN, {
          headers: { "Content-Type": "text/event-stream" },
        });
      })
    );

    await createChatAgent("t").runAgent({ tools: [RENDER_APPROVAL_TOOL] });

    expect(sent).toBeDefined();
    const contract = { tools: sent?.tools, context: sent?.context };
    const serialized = `${JSON.stringify(contract, null, 2)}\n`;
    if (process.env.UPDATE_CLIENT_CONTRACT) {
      writeFileSync(CONTRACT_PATH, serialized);
    }
    expect(readFileSync(CONTRACT_PATH, "utf8")).toBe(serialized);
  });
});
