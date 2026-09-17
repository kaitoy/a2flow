import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ADMIN, DEVELOPER, REQUESTER, SUPER_ADMIN } from "@/test/auth-state";
import { render } from "@/test/test-utils";
import AuditLayout from "./layout";

describe("AuditLayout", () => {
  it.each([
    ["an admin", ADMIN],
    ["a super_admin", SUPER_ADMIN],
  ])("renders children for %s", (_label, state) => {
    render(
      <AuditLayout>
        <div data-testid="panel">panel</div>
      </AuditLayout>,
      { preloadedState: state }
    );
    expect(screen.getByTestId("panel")).toBeInTheDocument();
  });

  it.each([
    ["a developer", DEVELOPER],
    ["a requester", REQUESTER],
  ])("shows an access-denied state instead of the children for %s", (_label, state) => {
    render(
      <AuditLayout>
        <div data-testid="panel">panel</div>
      </AuditLayout>,
      { preloadedState: state }
    );
    expect(screen.queryByTestId("panel")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });
});
