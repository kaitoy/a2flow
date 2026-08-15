import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ADMIN, SUPER_ADMIN } from "@/test/auth-state";
import { render } from "@/test/test-utils";
import TenantsLayout from "./layout";

describe("TenantsLayout", () => {
  it("renders children for a super_admin", () => {
    render(
      <TenantsLayout>
        <div data-testid="panel">panel</div>
      </TenantsLayout>,
      { preloadedState: SUPER_ADMIN }
    );
    expect(screen.getByTestId("panel")).toBeInTheDocument();
  });

  it("shows an access-denied state instead of the children for a non-super_admin", () => {
    render(
      <TenantsLayout>
        <div data-testid="panel">panel</div>
      </TenantsLayout>,
      { preloadedState: ADMIN }
    );
    expect(screen.queryByTestId("panel")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Access denied" })).toBeInTheDocument();
  });
});
