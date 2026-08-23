import { describe, expect, it } from "vitest";
import { render, screen } from "@/test/test-utils";
import { StatusCard } from "./status-card";

describe("StatusCard", () => {
  it("renders as a labelled region containing its children", () => {
    render(
      <StatusCard ariaLabel="Widget status">
        <span>ready</span>
      </StatusCard>
    );
    const region = screen.getByRole("region", { name: "Widget status" });
    expect(region).toBeInTheDocument();
    expect(screen.getByText("ready")).toBeInTheDocument();
  });

  it("omits the actions wrapper when no actions are given", () => {
    render(
      <StatusCard ariaLabel="Widget status">
        <span>ready</span>
      </StatusCard>
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("renders actions when given", () => {
    render(
      <StatusCard ariaLabel="Widget status" actions={<button type="button">Pull</button>}>
        <span>ready</span>
      </StatusCard>
    );
    expect(screen.getByRole("button", { name: "Pull" })).toBeInTheDocument();
  });

  it("omits the error line when no error is given", () => {
    render(
      <StatusCard ariaLabel="Widget status">
        <span>ready</span>
      </StatusCard>
    );
    expect(screen.queryByText(/failed/i)).not.toBeInTheDocument();
  });

  it("shows the error line when given", () => {
    render(
      <StatusCard ariaLabel="Widget status" error="clone failed: not found">
        <span>ready</span>
      </StatusCard>
    );
    expect(screen.getByText("clone failed: not found")).toBeInTheDocument();
  });

  it("is not lit by default", () => {
    render(
      <StatusCard ariaLabel="Widget status">
        <span>ready</span>
      </StatusCard>
    );
    expect(screen.getByRole("region", { name: "Widget status" })).not.toHaveClass("live-edge");
  });

  it("lights up when live", () => {
    render(
      <StatusCard ariaLabel="Widget status" live>
        <span>ready</span>
      </StatusCard>
    );
    expect(screen.getByRole("region", { name: "Widget status" })).toHaveClass("live-edge");
  });
});
