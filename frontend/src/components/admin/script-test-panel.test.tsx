import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { useForm } from "react-hook-form";
import { describe, expect, it } from "vitest";
import {
  emptyMcpServerFormValues,
  type McpServerFormValues,
} from "@/components/admin/mcp-server-fields";
import { argumentsTemplate, ScriptTestPanel } from "@/components/admin/script-test-panel";
import { envelope } from "@/test/msw/envelope";
import { server } from "@/test/msw/server";

const BASE = "http://localhost:8000";
const TOOLS_URL = `${BASE}/api/v1/mcp-servers/script-tools`;
const CALL_URL = `${BASE}/api/v1/mcp-servers/script-call`;

const ADD_TOOL = {
  name: "add",
  description: "Add two integers.",
  inputSchema: { type: "object", properties: { a: {}, b: {} } },
};

/** Renders the panel over a form holding a script server's values. */
function Harness({ source = "def add(a: int, b: int) -> int: ..." }: { source?: string }) {
  const { control } = useForm<McpServerFormValues>({
    defaultValues: {
      ...emptyMcpServerFormValues(),
      transport: "script",
      source,
      env: [{ key: "TOKEN", value: "t" }],
    },
  });
  return <ScriptTestPanel control={control} />;
}

describe("argumentsTemplate", () => {
  it("nulls out every declared property", () => {
    expect(JSON.parse(argumentsTemplate(ADD_TOOL))).toEqual({ a: null, b: null });
  });

  it("is an empty object without properties", () => {
    expect(argumentsTemplate(undefined)).toBe("{}");
  });
});

describe("ScriptTestPanel", () => {
  it("disables Load tools while the source is empty", () => {
    render(<Harness source="" />);
    expect(screen.getByRole("button", { name: /load tools/i })).toBeDisabled();
  });

  it("sends the form's script and lists its tools with an arguments skeleton", async () => {
    let body: unknown;
    server.use(
      http.post(TOOLS_URL, async ({ request }) => {
        body = await request.json();
        return envelope({ tools: [ADD_TOOL], error: null });
      })
    );
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: /load tools/i }));

    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "Tool" })).toHaveTextContent("add")
    );
    expect(body).toEqual({
      language: "python",
      source: "def add(a: int, b: int) -> int: ...",
      env: { TOKEN: "t" },
    });
    expect(JSON.parse((screen.getByLabelText("Arguments") as HTMLTextAreaElement).value)).toEqual({
      a: null,
      b: null,
    });
  });

  it("shows the traceback when the script cannot load", async () => {
    server.use(
      http.post(TOOLS_URL, () =>
        envelope({ tools: [], error: "Traceback ...\nSyntaxError: invalid syntax" })
      )
    );
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: /load tools/i }));

    await waitFor(() =>
      expect(screen.getByText(/SyntaxError: invalid syntax/)).toBeInTheDocument()
    );
    expect(screen.queryByRole("combobox", { name: "Tool" })).not.toBeInTheDocument();
  });

  it("runs the selected tool with the parsed arguments and shows its output", async () => {
    let body: unknown;
    server.use(
      http.post(TOOLS_URL, () => envelope({ tools: [ADD_TOOL], error: null })),
      http.post(CALL_URL, async ({ request }) => {
        body = await request.json();
        return envelope({ isError: false, content: ["5"], structured: null });
      })
    );
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: /load tools/i }));
    const args = await screen.findByLabelText("Arguments");

    await user.clear(args);
    await user.type(args, '{{"a": 2, "b": 3}');
    await user.click(screen.getByRole("button", { name: /^run$/i }));

    await waitFor(() => expect(screen.getByText("5")).toBeInTheDocument());
    expect(body).toMatchObject({ toolName: "add", arguments: { a: 2, b: 3 } });
  });

  it("rejects invalid JSON arguments without sending a request", async () => {
    let called = false;
    server.use(
      http.post(TOOLS_URL, () => envelope({ tools: [ADD_TOOL], error: null })),
      http.post(CALL_URL, () => {
        called = true;
        return HttpResponse.json({});
      })
    );
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: /load tools/i }));
    const args = await screen.findByLabelText("Arguments");

    await user.clear(args);
    await user.type(args, "[[1]");
    await user.click(screen.getByRole("button", { name: /^run$/i }));

    expect(await screen.findByText("Arguments must be a JSON object.")).toBeInTheDocument();
    expect(called).toBe(false);
  });
});
