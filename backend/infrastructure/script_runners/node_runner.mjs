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
import { execFileSync } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { existsSync, mkdirSync, renameSync, rmSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { createInterface } from "node:readline";
import { pathToFileURL } from "node:url";

console.log = console.info = console.debug = console.error;

const source = process.env.A2FLOW_SCRIPT_SOURCE ?? "";
delete process.env.A2FLOW_SCRIPT_SOURCE;
const packages = JSON.parse(process.env.A2FLOW_SCRIPT_PACKAGES ?? "[]");
delete process.env.A2FLOW_SCRIPT_PACKAGES;

/**
 * Install `pkgs` into a directory shared by every script that declares the
 * same set on the same Node ABI, keyed by their hash, and return it. A missing directory is built
 * under a temporary name and renamed into place, so a concurrent launch never
 * sees a half-installed one; losing that race just discards the duplicate.
 * npm's output never reaches stdout, which carries the protocol; when the
 * install fails its error output becomes the thrown error's message.
 * @param {string[]} pkgs - npm package specs.
 * @returns {string} The directory whose `node_modules` holds them.
 */
function installPackages(pkgs) {
  // Keyed by Node's module ABI too: a native addon built for one will not load in another.
  const key = createHash("sha256")
    .update(JSON.stringify([process.versions.modules, [...pkgs].sort()]))
    .digest("hex");
  // ponytail: cache directories are never pruned; add a cleanup when disk use matters.
  const dir = join(homedir(), ".cache", "a2flow-script-packages", "javascript", key);
  if (existsSync(dir)) return dir;
  const tmp = `${dir}.tmp-${process.pid}`;
  mkdirSync(tmp, { recursive: true });
  try {
    // npm ships beside node: next to it on Windows, under ../lib elsewhere.
    const npmCli = [
      join(dirname(process.execPath), "node_modules", "npm", "bin", "npm-cli.js"),
      join(dirname(process.execPath), "..", "lib", "node_modules", "npm", "bin", "npm-cli.js"),
    ].find(existsSync);
    if (!npmCli) throw new Error("npm was not found next to node");
    try {
      execFileSync(
        process.execPath,
        [npmCli, "install", "--no-save", "--no-package-lock", "--no-audit", "--no-fund", "--prefix", tmp, "--", ...pkgs],
        { stdio: ["ignore", 2, "pipe"], encoding: "utf-8" }
      );
    } catch (error) {
      throw new Error(`npm install failed:\n${String(error.stderr ?? "").trim()}`);
    }
    renameSync(tmp, dir);
  } catch (error) {
    rmSync(tmp, { recursive: true, force: true });
    if (!existsSync(dir)) throw error;
  }
  return dir;
}

/**
 * Why the script failed to load, or `undefined` when it loaded. A script that
 * fails -- a package that will not install, a syntax error, a throw at its top
 * level -- is still served, so the handshake completes and the client sees
 * this text instead of a closed connection: `tools/list` answers with it as an
 * error, `tools/call` as an `isError` result.
 */
let loadError;
let script = {};
// Without packages the script is imported from a data: URL; with them it must
// be a file inside their directory, since a data: URL cannot resolve a bare
// `import "pkg"`. The file is removed once imported.
let scriptUrl = `data:text/javascript;base64,${Buffer.from(source).toString("base64")}`;
let scriptFile;
try {
  if (packages.length > 0) {
    scriptFile = join(installPackages(packages), `script-${randomUUID()}.mjs`);
    writeFileSync(scriptFile, source);
    scriptUrl = pathToFileURL(scriptFile).href;
  }
  script = await import(scriptUrl);
} catch (error) {
  // Keep only the script's own frames, named `<script>` rather than by its
  // data: URL; the runner's and Node's frames mean nothing to its author.
  loadError = String(error?.stack ?? error)
    .split("\n")
    .filter((line) => !line.trimStart().startsWith("at ") || line.includes(scriptUrl))
    .map((line) => line.replaceAll(scriptUrl, "<script>"))
    .join("\n");
  console.error(loadError);
} finally {
  if (scriptFile) rmSync(scriptFile, { force: true });
}

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
      if (loadError) return { error: { code: -32603, message: loadError } };
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
      if (loadError) return { result: { content: [{ type: "text", text: loadError }], isError: true } };
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
