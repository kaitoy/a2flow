import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ToolOutputFormatPanel } from "./tool-output-format-panel";

describe("ToolOutputFormatPanel", () => {
  it("renders nothing when no tool is chosen", () => {
    const { container } = render(<ToolOutputFormatPanel toolName="" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the tool name, its description, and the schema, open by default", () => {
    render(
      <ToolOutputFormatPanel
        toolName="search_issues"
        description="Search Jira by JQL."
        outputSchema={{ type: "object", properties: { total: { type: "integer" } } }}
      />
    );
    expect(screen.getByRole("button", { name: /output format/i })).toHaveAttribute(
      "aria-expanded",
      "true"
    );
    expect(screen.getByText("search_issues")).toBeInTheDocument();
    expect(screen.getByText("Search Jira by JQL.")).toBeInTheDocument();
    expect(screen.getByText(/"total"/)).toBeInTheDocument();
  });

  it("collapses and re-expands on click", async () => {
    const user = userEvent.setup();
    render(<ToolOutputFormatPanel toolName="search_issues" outputSchema={{ type: "object" }} />);
    const toggle = screen.getByRole("button", { name: /output format/i });
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText(/"object"/)).not.toBeInTheDocument();
    await user.click(toggle);
    expect(screen.getByText(/"object"/)).toBeInTheDocument();
  });

  it("holds the space with a skeleton while the declaration is still loading", () => {
    render(<ToolOutputFormatPanel toolName="search_issues" loading />);
    expect(screen.getByText("search_issues")).toBeInTheDocument();
    expect(screen.getByRole("status", { name: /loading output format/i })).toBeInTheDocument();
    // Loading is not the same as "the tool answered and declares nothing".
    expect(screen.queryByText(/does not declare an output format/i)).not.toBeInTheDocument();
  });

  it("hides the skeleton when the panel is collapsed while loading", async () => {
    const user = userEvent.setup();
    render(<ToolOutputFormatPanel toolName="search_issues" loading />);
    await user.click(screen.getByRole("button", { name: /output format/i }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("says so when the tool declares no output format", () => {
    render(<ToolOutputFormatPanel toolName="ping" description="Ping the server." />);
    expect(screen.getByText(/does not declare an output format/i)).toBeInTheDocument();
  });
});
