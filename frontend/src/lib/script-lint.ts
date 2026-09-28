/**
 * @module script-lint — Lint sources for a script MCP server's source editor.
 *
 * JavaScript is checked in the browser with acorn; Python goes to the
 * backend, which compiles it with the same interpreter that will run it. Both
 * report a syntax error first and, for a script that parses, the slips against
 * the runner conventions that would leave a tool missing or vaguely described.
 */
import type { Diagnostic } from "@codemirror/lint";
import type { Text } from "@codemirror/state";
import type { EditorView } from "@codemirror/view";
import { type ModuleDeclaration, type Node, parse, type Statement } from "acorn";
import { lintPythonScript } from "@/lib/api";

/** A public exported function: the tool name, the local binding, and where to mark it. */
interface ExportedFunction {
  exported: string;
  local: string;
  node: Node;
}

/** Warning spanning the first line, for a problem that belongs to no single spot. */
function wholeScriptWarning(doc: Text, message: string): Diagnostic {
  return { from: 0, to: doc.line(1).to, severity: "warning", message };
}

/**
 * Top-level functions declared as `function f` or `const f = () => …`, by name.
 *
 * @param body - The program's top-level statements.
 * @returns Each function's name mapped to its identifier node.
 */
function topLevelFunctions(body: (Statement | ModuleDeclaration)[]): Map<string, Node> {
  const found = new Map<string, Node>();
  for (const statement of body) {
    const declaration =
      statement.type === "ExportNamedDeclaration" ? statement.declaration : statement;
    if (declaration?.type === "FunctionDeclaration" && declaration.id) {
      found.set(declaration.id.name, declaration.id);
    } else if (declaration?.type === "VariableDeclaration") {
      for (const { id, init } of declaration.declarations) {
        if (
          id.type === "Identifier" &&
          (init?.type === "FunctionExpression" || init?.type === "ArrowFunctionExpression")
        ) {
          found.set(id.name, id);
        }
      }
    }
  }
  return found;
}

/**
 * Lint a JavaScript (ES module) script server's source.
 *
 * @param doc - The document to check.
 * @returns A syntax error alone, else a warning when no function is exported
 *   and, per exported function, a warning without `fn.description` and a note
 *   without `fn.inputSchema`.
 */
export function javaScriptDiagnostics(doc: Text): Diagnostic[] {
  const source = doc.toString();
  if (source.trim() === "") return [];
  let body: (Statement | ModuleDeclaration)[];
  try {
    body = parse(source, { ecmaVersion: "latest", sourceType: "module" }).body;
  } catch (error) {
    if (!(error instanceof SyntaxError)) throw error;
    const pos = (error as SyntaxError & { pos?: number }).pos ?? 0;
    return [
      {
        from: pos,
        to: Math.min(pos + 1, source.length),
        severity: "error",
        message: error.message.replace(/ \(\d+:\d+\)$/, ""),
      },
    ];
  }

  const functions = topLevelFunctions(body);
  const tools: ExportedFunction[] = [];
  const assigned = new Set<string>();
  for (const statement of body) {
    if (statement.type === "ExportNamedDeclaration") {
      if (statement.declaration) {
        for (const [name, node] of topLevelFunctions([statement.declaration])) {
          tools.push({ exported: name, local: name, node });
        }
      }
      for (const specifier of statement.specifiers) {
        const local = specifier.local.type === "Identifier" ? specifier.local.name : "";
        const exported =
          specifier.exported.type === "Identifier"
            ? specifier.exported.name
            : String(specifier.exported.value);
        if (!statement.source && functions.has(local)) {
          tools.push({ exported, local, node: specifier.exported });
        }
      }
    } else if (
      statement.type === "ExpressionStatement" &&
      statement.expression.type === "AssignmentExpression" &&
      statement.expression.left.type === "MemberExpression" &&
      statement.expression.left.object.type === "Identifier" &&
      statement.expression.left.property.type === "Identifier"
    ) {
      const { object, property } = statement.expression.left;
      assigned.add(`${object.name}.${property.name}`);
    }
  }

  const publicTools = tools.filter((tool) => !tool.exported.startsWith("_"));
  if (publicTools.length === 0) {
    return [wholeScriptWarning(doc, "No exported function: this server exposes no tools.")];
  }
  const diagnostics: Diagnostic[] = [];
  for (const { exported, local, node } of publicTools) {
    const at = { from: node.start, to: node.end };
    if (!assigned.has(`${local}.description`)) {
      diagnostics.push({
        ...at,
        severity: "warning",
        message: `'${exported}' has no description: set ${local}.description to tell the agent what the tool does.`,
      });
    }
    if (!assigned.has(`${local}.inputSchema`)) {
      diagnostics.push({
        ...at,
        severity: "info",
        message: `'${exported}' has no inputSchema: the tool will accept any arguments object.`,
      });
    }
  }
  return diagnostics;
}

/** {@link javaScriptDiagnostics} as a CodeMirror lint source. */
export function lintJavaScript(view: EditorView): Diagnostic[] {
  return javaScriptDiagnostics(view.state.doc);
}

/**
 * Lint a Python script server's source through the backend.
 *
 * The backend reports 1-based lines and 0-based character columns; they are
 * clamped into the document, which may have been edited meanwhile (CodeMirror
 * then discards the stale result anyway). A failed request yields no marks
 * rather than blocking the editor.
 *
 * @param view - The editor to lint.
 * @param packages - The server's declared packages; any at all lifts the
 *   standard-library-only import warning.
 * @returns The diagnostics for the editor's document.
 */
export async function lintPython(view: EditorView, packages: string[] = []): Promise<Diagnostic[]> {
  const doc = view.state.doc;
  const source = doc.toString();
  if (source.trim() === "") return [];
  let found: Awaited<ReturnType<typeof lintPythonScript>>;
  try {
    found = await lintPythonScript(source, packages);
  } catch {
    return [];
  }
  const offset = (line: number, column: number) => {
    const at = doc.line(Math.min(Math.max(line, 1), doc.lines));
    return at.from + Math.min(Math.max(column, 0), at.length);
  };
  return found.map((diagnostic) => {
    const from = offset(diagnostic.line, diagnostic.column);
    return {
      from,
      to: Math.max(from, offset(diagnostic.endLine, diagnostic.endColumn)),
      severity: diagnostic.severity,
      message: diagnostic.message,
    };
  });
}
