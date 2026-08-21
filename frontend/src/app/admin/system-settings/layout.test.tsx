import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ADMIN, DEVELOPER, SUPER_ADMIN } from "@/test/auth-state";
import { render } from "@/test/test-utils";
import SystemSettingsLayout from "./layout";

describe("SystemSettingsLayout", () => {
  it("renders children for a super_admin", () => {
    render(
      <SystemSettingsLayout>
        <div data-testid="panel">panel</div>
      </SystemSettingsLayout>,
      { preloadedState: SUPER_ADMIN }
    );
    expect(screen.getByTestId("panel")).toBeInTheDocument();
  });

  it.each([
    ["an admin", ADMIN],
    ["a developer", DEVELOPER],
  ])("shows an access-denied state instead of the children for %s", (_label, state) => {
    render(
      <SystemSettingsLayout>
        <div data-testid="panel">panel</div>
      </SystemSettingsLayout>,
      { preloadedState: state }
    );
    expect(screen.queryByTestId("panel")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });
});
