import { zodResolver } from "@hookform/resolvers/zod";
import { render, screen } from "@testing-library/react";
import { useForm } from "react-hook-form";
import { describe, expect, it } from "vitest";
import type { McpServer } from "@/lib/api";
import {
  emptyMcpServerFormValues,
  McpServerFields,
  type McpServerFormValues,
  mcpServerEndpoint,
  mcpServerFormSchema,
  mcpTransportLabel,
  toMcpServerBody,
} from "./mcp-server-fields";

/** Host that wires the shared fields to a real form, as both pages do. */
function Host({ defaults }: { defaults?: Partial<McpServerFormValues> }) {
  const {
    register,
    control,
    watch,
    formState: { errors },
  } = useForm<McpServerFormValues>({
    resolver: zodResolver(mcpServerFormSchema),
    defaultValues: { ...emptyMcpServerFormValues(), ...defaults },
  });
  return (
    <McpServerFields
      register={register}
      control={control}
      errors={errors}
      transport={watch("transport")}
    />
  );
}

describe("McpServerFields", () => {
  it("shows url and header fields for the streamable_http transport", () => {
    render(<Host />);
    expect(screen.getByLabelText("URL *")).toBeInTheDocument();
    expect(screen.getByText("HTTP Headers")).toBeInTheDocument();
    expect(screen.queryByText("Arguments")).not.toBeInTheDocument();
  });

  it("shows a description field", () => {
    render(<Host />);
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
  });

  it("shows command, args, and env fields for the stdio transport", () => {
    render(<Host defaults={{ transport: "stdio" }} />);
    expect(screen.getByRole("tablist", { name: "Command" })).toBeInTheDocument();
    expect(screen.getByText("Arguments")).toBeInTheDocument();
    expect(screen.getByText("Environment Variables")).toBeInTheDocument();
    expect(screen.queryByText("HTTP Headers")).not.toBeInTheDocument();
  });

  it("marks the active transport on the segmented control", () => {
    render(<Host defaults={{ transport: "stdio" }} />);
    expect(screen.getByRole("tab", { name: "stdio" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "Streamable HTTP" })).toHaveAttribute(
      "aria-selected",
      "false"
    );
  });

  it("marks the default command on the segmented control", () => {
    render(<Host defaults={{ transport: "stdio" }} />);
    expect(screen.getByRole("tab", { name: "npx" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: "uvx" })).toHaveAttribute("aria-selected", "false");
  });

  it("shows a hint that arguments may reference the server's own env vars", () => {
    render(<Host defaults={{ transport: "stdio" }} />);
    expect(screen.getByText(/\$\{env:NAME\}/)).toBeInTheDocument();
  });

  it("shows a hint that a header may mint a Google access token from a secret", () => {
    render(<Host />);
    expect(screen.getByText(/\$\{gcp-token:name\/key\}/)).toBeInTheDocument();
  });

  it("shows language, source, and env fields for the script transport", () => {
    render(<Host defaults={{ transport: "script" }} />);
    expect(screen.getByRole("tab", { name: "Python" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByLabelText("Source *")).toHaveAttribute("role", "textbox");
    expect(screen.getByText("Environment Variables")).toBeInTheDocument();
    expect(screen.queryByRole("tablist", { name: "Command" })).not.toBeInTheDocument();
    expect(screen.queryByText("Arguments")).not.toBeInTheDocument();
    expect(screen.queryByText("HTTP Headers")).not.toBeInTheDocument();
  });

  it("describes the tool convention of the selected script language", () => {
    render(<Host defaults={{ transport: "script", language: "javascript" }} />);
    expect(screen.getByText(/fn\.inputSchema/)).toBeInTheDocument();
    expect(screen.queryByText(/docstring/)).not.toBeInTheDocument();
  });

  describe("readOnly", () => {
    it("renders a remote server's url and headers as values", () => {
      render(
        <McpServerFields
          readOnly
          values={{
            ...emptyMcpServerFormValues(),
            name: "web-search",
            url: "https://mcp.example.com/mcp",
            headers: [{ key: "Authorization", value: "Bearer x" }],
          }}
        />
      );
      expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
      expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
      expect(screen.getByText("web-search")).toBeInTheDocument();
      expect(screen.getByText("Streamable HTTP")).toBeInTheDocument();
      expect(screen.getByText("https://mcp.example.com/mcp")).toBeInTheDocument();
      expect(screen.getByText("Authorization: Bearer x")).toBeInTheDocument();
    });

    it("renders a stdio server's command, arguments, and environment as values", () => {
      render(
        <McpServerFields
          readOnly
          values={{
            ...emptyMcpServerFormValues(),
            name: "local-files",
            transport: "stdio",
            command: "uvx",
            args: ["-y", "", "files-mcp"],
            env: [{ key: "API_KEY", value: "x" }],
          }}
        />
      );
      expect(screen.getByText("stdio")).toBeInTheDocument();
      expect(screen.getByText("uvx")).toBeInTheDocument();
      // One argument per line; getByText's normalizer collapses the newline,
      // and the blank row is dropped.
      expect(screen.getByText("-y files-mcp")).toBeInTheDocument();
      expect(screen.getByText("API_KEY: x")).toBeInTheDocument();
      expect(screen.queryByText("HTTP Headers")).not.toBeInTheDocument();
    });

    it("renders a script server's language and source as values", () => {
      render(
        <McpServerFields
          readOnly
          values={{
            ...emptyMcpServerFormValues(),
            name: "calc",
            transport: "script",
            language: "javascript",
            source: "export function add() {}",
            env: [{ key: "API_KEY", value: "x" }],
          }}
        />
      );
      expect(screen.getByText("Script")).toBeInTheDocument();
      expect(screen.getByText("JavaScript")).toBeInTheDocument();
      expect(screen.getByLabelText("Source *")).toHaveTextContent("export function add() {}");
      expect(screen.getByLabelText("Source *")).toHaveAttribute("contenteditable", "false");
      expect(screen.getByText("API_KEY: x")).toBeInTheDocument();
      expect(screen.queryByText("Command")).not.toBeInTheDocument();
    });

    it("drops the authoring hints", () => {
      render(
        <McpServerFields readOnly values={{ ...emptyMcpServerFormValues(), transport: "stdio" }} />
      );
      expect(screen.queryByText(/\$\{env:NAME\}/)).not.toBeInTheDocument();
      expect(screen.queryByText(/\$\{secret:name\/key\}/)).not.toBeInTheDocument();
      expect(screen.queryByText(/child process of the backend/i)).not.toBeInTheDocument();
    });

    it("falls back to a placeholder for empty pair and list fields", () => {
      render(<McpServerFields readOnly values={{ ...emptyMcpServerFormValues(), name: "srv" }} />);
      // Description, URL, and HTTP Headers are all empty for a freshly blank remote server.
      expect(screen.getAllByText("—")).toHaveLength(3);
    });

    it("renders a set description as text", () => {
      render(
        <McpServerFields
          readOnly
          values={{ ...emptyMcpServerFormValues(), name: "srv", description: "Handles web search" }}
        />
      );
      expect(screen.getByText("Handles web search")).toBeInTheDocument();
    });
  });
});

describe("mcpServerFormSchema", () => {
  it("requires a url for the streamable_http transport", () => {
    const result = mcpServerFormSchema.safeParse({
      ...emptyMcpServerFormValues(),
      name: "srv",
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]).toMatchObject({
      path: ["url"],
      message: "URL is required",
    });
  });

  it("rejects a url that is not http(s)", () => {
    const result = mcpServerFormSchema.safeParse({
      ...emptyMcpServerFormValues(),
      name: "srv",
      url: "ftp://example.com",
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0].path).toEqual(["url"]);
  });

  it("does not require a url when the transport is stdio", () => {
    const result = mcpServerFormSchema.safeParse({
      ...emptyMcpServerFormValues(),
      name: "srv",
      transport: "stdio",
      command: "npx",
    });
    expect(result.success).toBe(true);
  });

  it("requires a source for the script transport", () => {
    const result = mcpServerFormSchema.safeParse({
      ...emptyMcpServerFormValues(),
      name: "srv",
      transport: "script",
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]).toMatchObject({
      path: ["source"],
      message: "Source is required",
    });
  });
});

describe("mcpServerEndpoint", () => {
  const base = { id: "s", name: "srv", tenantId: "t", createdBy: "u", updatedBy: "u" } as const;

  it("summarizes each transport's endpoint", () => {
    expect(mcpServerEndpoint({ ...base, url: "https://mcp.example.com/mcp" } as McpServer)).toBe(
      "https://mcp.example.com/mcp"
    );
    expect(
      mcpServerEndpoint({
        ...base,
        transport: "stdio",
        command: "npx",
        args: ["-y", "pkg"],
      } as McpServer)
    ).toBe("npx -y pkg");
    expect(
      mcpServerEndpoint({ ...base, transport: "script", language: "javascript" } as McpServer)
    ).toBe("JavaScript script");
  });
});

describe("mcpTransportLabel", () => {
  it("labels each transport", () => {
    expect(mcpTransportLabel("streamable_http")).toBe("HTTP");
    expect(mcpTransportLabel("stdio")).toBe("stdio");
    expect(mcpTransportLabel("script")).toBe("Script");
  });
});

describe("toMcpServerBody", () => {
  it("emits url and headers, and no stdio fields, for a remote server", () => {
    expect(
      toMcpServerBody({
        ...emptyMcpServerFormValues(),
        name: "srv",
        url: "https://mcp.example.com/mcp",
        headers: [
          { key: "Authorization", value: "Bearer x" },
          { key: "", value: "dropped" },
        ],
        command: "uvx",
        args: ["leftover"],
      })
    ).toEqual({
      name: "srv",
      description: null,
      transport: "streamable_http",
      url: "https://mcp.example.com/mcp",
      headers: { Authorization: "Bearer x" },
    });
  });

  it("emits command, args, and env, and no remote fields, for a stdio server", () => {
    expect(
      toMcpServerBody({
        ...emptyMcpServerFormValues(),
        name: "srv",
        transport: "stdio",
        url: "https://leftover.example.com",
        headers: [{ key: "Authorization", value: "leftover" }],
        command: "npx",
        args: ["-y", "", "pkg"],
        env: [{ key: "API_KEY", value: "x" }],
      })
    ).toEqual({
      name: "srv",
      description: null,
      transport: "stdio",
      command: "npx",
      args: ["-y", "pkg"],
      env: { API_KEY: "x" },
    });
  });

  it("emits language, source, packages, and env, and no other transport's fields, for a script", () => {
    expect(
      toMcpServerBody({
        ...emptyMcpServerFormValues(),
        name: "srv",
        transport: "script",
        url: "https://leftover.example.com",
        command: "npx",
        args: ["leftover"],
        language: "python",
        source: "def f(): ...",
        packages: ["boto3", ""],
        env: [{ key: "API_KEY", value: "x" }],
      })
    ).toEqual({
      name: "srv",
      description: null,
      transport: "script",
      language: "python",
      source: "def f(): ...",
      packages: ["boto3"],
      env: { API_KEY: "x" },
    });
  });

  it("includes a set description", () => {
    expect(
      toMcpServerBody({
        ...emptyMcpServerFormValues(),
        name: "srv",
        description: "Handles web search",
        url: "https://mcp.example.com/mcp",
      })
    ).toMatchObject({ description: "Handles web search" });
  });
});
