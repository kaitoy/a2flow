import { http } from "msw";
import { describe, expect, it } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { render, screen } from "@/test/test-utils";
import {
  emptyMcpToolMockFormValues,
  McpToolMockFields,
  type McpToolMockFormValues,
  mcpToolMockFormSchema,
  responseToFormValue,
  toMcpToolMockBody,
} from "./mcp-tool-mock-fields";

function values(overrides: Partial<McpToolMockFormValues> = {}): McpToolMockFormValues {
  return { ...emptyMcpToolMockFormValues(), ...overrides };
}

describe("mcpToolMockFormSchema", () => {
  it("requires a server and a tool name for an MCP mock", () => {
    const result = mcpToolMockFormSchema.safeParse(values({ name: "m", target: "mcp" }));
    expect(result.success).toBe(false);
    const paths = result.success ? [] : result.error.issues.map((i) => i.path.join("."));
    expect(paths).toContain("mcpServerId");
    expect(paths).toContain("toolName");
  });

  it("needs neither for a built-in mock", () => {
    expect(mcpToolMockFormSchema.safeParse(values({ name: "m", target: "builtin" })).success).toBe(
      true
    );
  });

  it("rejects an empty response list", () => {
    const result = mcpToolMockFormSchema.safeParse(
      values({ name: "m", target: "builtin", responses: [] })
    );
    expect(result.success).toBe(false);
  });

  it("requires a non-empty value for a text response", () => {
    const result = mcpToolMockFormSchema.safeParse(
      values({ name: "m", target: "builtin", responses: [{ kind: "text", value: "" }] })
    );
    expect(result.success).toBe(false);
  });
});

describe("responseToFormValue", () => {
  it("pretty-prints a stored JSON object for editing", () => {
    expect(responseToFormValue({ kind: "structured", value: { a: 1 } })).toEqual({
      kind: "structured",
      value: '{\n  "a": 1\n}',
    });
  });

  it("keeps a text value as plain text", () => {
    expect(responseToFormValue({ kind: "text", value: "hello" })).toEqual({
      kind: "text",
      value: "hello",
    });
  });
});

describe("toMcpToolMockBody", () => {
  it("parses a structured response's JSON text", () => {
    const body = toMcpToolMockBody(
      values({
        name: "m",
        target: "mcp",
        mcpServerId: "mcp-1",
        toolName: "search",
        responses: [{ kind: "structured", value: '{"hits": 0}' }],
      })
    );
    expect(body.responses).toEqual([{ kind: "structured", value: { hits: 0 } }]);
  });

  it("sends a null server id and the built-in tool name for a built-in mock", () => {
    const body = toMcpToolMockBody(
      values({ name: "m", target: "builtin", toolName: "ignored-by-the-form" })
    );
    expect(body.mcpServerId).toBeNull();
    expect(body.toolName).toBe("request_approval");
  });

  it("sends a blank description as null rather than an empty string", () => {
    const body = toMcpToolMockBody(values({ name: "m", target: "builtin" }));
    expect(body.description).toBeNull();
  });
});

describe("McpToolMockFields read-only mode", () => {
  it("shows every value as text, naming the selected server", async () => {
    render(
      <McpToolMockFields
        readOnly
        values={values({
          name: "no hits",
          target: "mcp",
          mcpServerId: "mcp-1",
          toolName: "search",
          responses: [{ kind: "text", value: "nothing found" }],
        })}
      />
    );
    expect(screen.getByText("no hits")).toBeInTheDocument();
    // The name is resolved from the MCP server registry, read on mount.
    expect(await screen.findByText("my-mcp-server")).toBeInTheDocument();
    expect(screen.getByText("search")).toBeInTheDocument();
    expect(screen.getByText(/#1 \(text\)/)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("never lists a server's tools, so it makes no MCP connection", async () => {
    let listed = false;
    server.use(
      http.get("http://localhost:8000/api/v1/mcp-servers/:serverId/tools", () => {
        listed = true;
        return envelope([]);
      })
    );

    render(
      <McpToolMockFields
        readOnly
        values={values({
          name: "no hits",
          target: "mcp",
          mcpServerId: "mcp-1",
          toolName: "search",
        })}
      />
    );

    // The registry read still happens — it names the server — so wait for it
    // before concluding the tool listing did not.
    expect(await screen.findByText("my-mcp-server")).toBeInTheDocument();
    expect(listed).toBe(false);
    expect(screen.queryByRole("button", { name: /output format/i })).not.toBeInTheDocument();
  });

  it("omits the server field for a built-in mock", () => {
    render(
      <McpToolMockFields
        readOnly
        values={values({ name: "auto approve", target: "builtin", toolName: "request_approval" })}
      />
    );
    expect(screen.queryByText("MCP Server")).not.toBeInTheDocument();
    expect(screen.getByText("request_approval")).toBeInTheDocument();
  });
});
