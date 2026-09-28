import { EditorState, Text } from "@codemirror/state";
import type { EditorView } from "@codemirror/view";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";
import { javaScriptDiagnostics, lintPython } from "./script-lint";

const LINT_URL = "http://localhost:8000/api/v1/mcp-servers/python-lint";

function lintJs(source: string) {
  return javaScriptDiagnostics(Text.of(source.split("\n")));
}

/** Just enough of an EditorView for a lint source: its state. */
function viewOf(source: string): EditorView {
  return { state: EditorState.create({ doc: source }) } as EditorView;
}

describe("javaScriptDiagnostics", () => {
  it("reports nothing for a blank or fully described script", () => {
    expect(lintJs("  \n")).toEqual([]);
    expect(
      lintJs(
        [
          "export async function add({ a, b }) { return a + b; }",
          'add.description = "Add.";',
          'add.inputSchema = { type: "object" };',
        ].join("\n")
      )
    ).toEqual([]);
  });

  it("reports a syntax error alone, at its position, without acorn's (line:col)", () => {
    const [diagnostic, ...rest] = lintJs("export function f() {\n  return (1;\n}");
    expect(rest).toEqual([]);
    expect(diagnostic).toMatchObject({ severity: "error", from: 33, to: 34 });
    expect(diagnostic.message).toBe("Unexpected token");
  });

  it("warns when nothing public is exported", () => {
    expect(lintJs("function f() {}\nexport function _hidden() {}")).toEqual([
      {
        from: 0,
        to: 15,
        severity: "warning",
        message: "No exported function: this server exposes no tools.",
      },
    ]);
  });

  it("flags a missing description and inputSchema at the function's name", () => {
    // biome-ignore lint/suspicious/noTemplateCurlyInString: source under test is a template literal, not a mistaken plain string
    const diagnostics = lintJs("export const greet = (args) => `hi ${args.name}`;");
    expect(diagnostics.map((d) => [d.severity, d.from, d.to])).toEqual([
      ["warning", 13, 18],
      ["info", 13, 18],
    ]);
    expect(diagnostics[0].message).toMatch(/set greet\.description/);
  });

  it("follows export specifiers back to their local function", () => {
    const diagnostics = lintJs(
      ["function inner() {}", 'inner.description = "x";', "export { inner as outer };"].join("\n")
    );
    expect(diagnostics).toHaveLength(1);
    expect(diagnostics[0]).toMatchObject({ severity: "info" });
    expect(diagnostics[0].message).toMatch(/^'outer' has no inputSchema/);
  });
});

describe("lintPython", () => {
  it("maps the backend's line and column to document offsets, clamped", async () => {
    server.use(
      http.post(LINT_URL, () =>
        envelope([
          {
            line: 2,
            column: 4,
            endLine: 2,
            endColumn: 99,
            severity: "warning",
            message: "no hint",
          },
        ])
      )
    );
    expect(await lintPython(viewOf("x = 1\ndef f(a):\n"))).toEqual([
      { from: 10, to: 15, severity: "warning", message: "no hint" },
    ]);
  });

  it("sends the source with the declared packages", async () => {
    let body: unknown;
    server.use(
      http.post(LINT_URL, async ({ request }) => {
        body = await request.json();
        return envelope([]);
      })
    );
    await lintPython(viewOf("import yaml"), ["pyyaml"]);
    expect(body).toEqual({ source: "import yaml", packages: ["pyyaml"] });
  });

  it("skips a blank document and swallows a failed request", async () => {
    expect(await lintPython(viewOf("\n"))).toEqual([]);
    server.use(http.post(LINT_URL, () => HttpResponse.json({}, { status: 500 })));
    expect(await lintPython(viewOf("x = 1"))).toEqual([]);
  });
});
