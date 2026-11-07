import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ja } from "@/i18n/messages/ja";
import { createTranslator, defaultTranslator } from "@/i18n/translate";
import type { ApprovedCall } from "@/lib/api";
import { ApprovedCallList, describeConstraint } from "./ApprovedCallList";

const call = (overrides: Partial<ApprovedCall> = {}): ApprovedCall => ({
  mcpServerId: "srv-1",
  toolName: "run_instances",
  arguments: {},
  ...overrides,
});

describe("describeConstraint", () => {
  const t = defaultTranslator;

  it("phrases each operator rather than showing raw JSON", () => {
    expect(describeConstraint({ eq: "ap-northeast-1" }, t)).toBe('is "ap-northeast-1"');
    expect(describeConstraint({ in: ["t3.micro"] }, t)).toBe('is one of ["t3.micro"]');
    expect(describeConstraint({ lte: 2 }, t)).toBe("is at most 2");
    expect(describeConstraint({ gte: 8 }, t)).toBe("is at least 8");
    expect(describeConstraint({ matches: "^dev-" }, t)).toBe('matches "^dev-"');
  });

  it("marks an argument the call may omit", () => {
    expect(describeConstraint({ eq: "dev", optional: true }, t)).toBe('is "dev", optional');
  });

  it("falls back to raw JSON for an operator this build does not know", () => {
    // A newer backend may declare one; showing it verbatim beats showing nothing.
    expect(describeConstraint({ startsWith: "dev" }, t)).toBe('{"startsWith":"dev"}');
  });

  it("phrases the bounds in the viewer's language", () => {
    const jaT = createTranslator("ja", ja);
    expect(describeConstraint({ lte: 2, optional: true }, jaT)).toBe("2 以下(任意)");
  });

  it("does not expand placeholder-like text inside a bound", () => {
    expect(describeConstraint({ eq: "{constraint}", optional: true }, t)).toBe(
      'is "{constraint}", optional'
    );
  });
});

describe("ApprovedCallList", () => {
  it("renders nothing when the approval carries no declaration", () => {
    // Approvals predating argument constraints: an empty panel would imply the
    // decision bounded something when it did not.
    const { container } = render(<ApprovedCallList calls={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("lists each declared call with its argument bounds", () => {
    render(
      <ApprovedCallList
        calls={[
          call({
            arguments: {
              region: { eq: "ap-northeast-1" },
              count: { lte: 2 },
            },
          }),
        ]}
      />
    );

    expect(screen.getByText("This authorizes")).toBeInTheDocument();
    expect(screen.getByText("srv-1: run_instances")).toBeInTheDocument();
    expect(screen.getByText("region")).toBeInTheDocument();
    expect(screen.getByText('is "ap-northeast-1"')).toBeInTheDocument();
    expect(screen.getByText("count")).toBeInTheDocument();
    expect(screen.getByText("is at most 2")).toBeInTheDocument();
  });

  it("resolves a server id to the name of a server the viewer can see", async () => {
    // MSW's server list carries "mcp-1"; "srv-1" is absent, as a hidden one is.
    render(<ApprovedCallList calls={[call({ mcpServerId: "mcp-1" }), call()]} />);
    expect(await screen.findByText("my-mcp-server: run_instances")).toBeInTheDocument();
    expect(screen.getByText("srv-1: run_instances")).toBeInTheDocument();
  });

  it("shows a declared call that constrains no arguments", () => {
    render(<ApprovedCallList calls={[call({ toolName: "list_regions" })]} />);
    expect(screen.getByText("srv-1: list_regions")).toBeInTheDocument();
  });

  it("says so when a call was exempted from input approval", () => {
    // Left unlabelled this is indistinguishable from the case above, which
    // permits no input at all — the opposite decision.
    render(
      <ApprovedCallList
        calls={[call({ toolName: "list_regions", unconstrainedArguments: true })]}
      />
    );
    expect(screen.getByText(/Any input/)).toBeInTheDocument();
  });

  it("labels only the exempted call in a mixed declaration", () => {
    render(
      <ApprovedCallList
        calls={[
          call({ arguments: { region: { eq: "ap-northeast-1" } } }),
          call({ toolName: "list_regions", unconstrainedArguments: true }),
        ]}
      />
    );
    expect(screen.getAllByText(/Any input/)).toHaveLength(1);
    expect(screen.getByText('is "ap-northeast-1"')).toBeInTheDocument();
  });
});
