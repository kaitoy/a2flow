/**
 * Serve a JavaScript (ES module) script's exported functions as MCP tools over stdio.
 *
 * Run as `node node_runner.mjs` with the source in the A2FLOW_SCRIPT_SOURCE
 * environment variable. Every exported function whose name does not start with
 * `_` becomes a tool (the default export is skipped). A function may carry
 * `description` and `inputSchema` properties; without them the tool has no
 * description and accepts any arguments object.
 *
 * Speaks just the slice of MCP a tool server needs -- `initialize`, `ping`,
 * `tools/list`, `tools/call` -- as newline-delimited JSON-RPC, with no
 * dependencies, since the script may use only Node's built-in modules anyway.
 * stdout carries the protocol, so `console.log` and friends are pointed at
 * stderr before the script runs.
 */
import { createInterface } from "node:readline";

console.log = console.info = console.debug = console.error;

const source = process.env.A2FLOW_SCRIPT_SOURCE ?? "";
delete process.env.A2FLOW_SCRIPT_SOURCE;
const script = await import(
  `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`
);

/** Public exported functions, by tool name. */
const tools = new Map(
  Object.entries(script).filter(
    ([name, fn]) => typeof fn === "function" && name !== "default" && !name.startsWith("_")
  )
);

/**
 * Write one JSON-RPC message to stdout.
 * @param {object} message - The message to send.
 */
function send(message) {
  process.stdout.write(`${JSON.stringify({ jsonrpc: "2.0", ...message })}\n`);
}

/**
 * Invoke a tool and wrap its outcome as an MCP `tools/call` result.
 * @param {Function} fn - The exported function.
 * @param {object} args - The call's arguments object.
 * @returns {Promise<object>} The result: its value as text, or the error with `isError` set.
 */
async function callTool(fn, args) {
  try {
    const value = await fn(args ?? {});
    const text = typeof value === "string" ? value : JSON.stringify(value ?? null);
    return { content: [{ type: "text", text }] };
  } catch (error) {
    return { content: [{ type: "text", text: String(error?.message ?? error) }], isError: true };
  }
}

/**
 * Answer one JSON-RPC request.
 * @param {object} request - The parsed request.
 * @returns {Promise<object>} Either `{ result }` or `{ error }`.
 */
async function handle({ method, params }) {
  switch (method) {
    case "initialize":
      return {
        result: {
          protocolVersion: params?.protocolVersion,
          capabilities: { tools: {} },
          serverInfo: { name: "script", version: "1.0.0" },
        },
      };
    case "ping":
      return { result: {} };
    case "tools/list":
      return {
        result: {
          tools: [...tools].map(([name, fn]) => ({
            name,
            description: typeof fn.description === "string" ? fn.description : undefined,
            inputSchema: fn.inputSchema ?? { type: "object" },
          })),
        },
      };
    case "tools/call": {
      const fn = tools.get(params?.name);
      if (!fn) return { error: { code: -32602, message: `Unknown tool: ${params?.name}` } };
      return { result: await callTool(fn, params.arguments) };
    }
    default:
      return { error: { code: -32601, message: `Method not found: ${method}` } };
  }
}

for await (const line of createInterface({ input: process.stdin })) {
  if (!line.trim()) continue;
  let request;
  try {
    request = JSON.parse(line);
  } catch {
    send({ id: null, error: { code: -32700, message: "Parse error" } });
    continue;
  }
  // A message without an id is a notification (e.g. notifications/initialized): no reply.
  if (request.id === undefined || request.id === null) continue;
  send({ id: request.id, ...(await handle(request)) });
}
