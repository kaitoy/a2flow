import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SessionFileCard } from "./SessionFileCard";

const FILE = {
  fileId: "file-1",
  workflowExecutionId: "exec-1",
  name: "error-summary.csv",
  sizeBytes: 2048,
};

describe("SessionFileCard", () => {
  it("names the file and its size", () => {
    render(<SessionFileCard content={FILE} />);
    expect(screen.getByText("error-summary.csv")).toBeInTheDocument();
    expect(screen.getByText("2.0 KB")).toBeInTheDocument();
  });

  it("links to the file's download endpoint", () => {
    render(<SessionFileCard content={FILE} />);
    const link = screen.getByRole("link", { name: "Download error-summary.csv" });
    expect(link).toHaveAttribute(
      "href",
      "http://localhost:8000/api/v1/workflow-executions/exec-1/files/file-1/content"
    );
    expect(link).toHaveAttribute("download", "error-summary.csv");
  });

  it("builds the link from the card's own content, not from the surrounding chat", () => {
    // The run id travels in the tool result, which is what lets a reloaded
    // session rebuild a working link from the transcript alone.
    render(<SessionFileCard content={{ ...FILE, workflowExecutionId: "other-run" }} />);
    expect(screen.getByRole("link", { name: /Download/ })).toHaveAttribute(
      "href",
      expect.stringContaining("/workflow-executions/other-run/")
    );
  });
});
