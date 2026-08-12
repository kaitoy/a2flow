import { describe, expect, it } from "vitest";
import { render, screen } from "@/test/test-utils";
import { InheritedRoles, InheritedRolesField } from "./inherited-roles";

describe("InheritedRoles", () => {
  it("renders one chip per inherited role", () => {
    render(<InheritedRoles roles={["developer", "approver"]} />);
    expect(screen.getByText("Developer")).toBeInTheDocument();
    expect(screen.getByText("Approver")).toBeInTheDocument();
  });

  it("renders nothing when no role is inherited", () => {
    const { container } = render(<InheritedRoles roles={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("InheritedRolesField", () => {
  it("labels the section and explains where the roles come from", () => {
    render(<InheritedRolesField roles={["developer"]} />);
    expect(screen.getByText("Roles from groups")).toBeInTheDocument();
    expect(screen.getByText("Developer")).toBeInTheDocument();
    expect(screen.getByText(/Granted by group membership/)).toBeInTheDocument();
  });

  it("says so when the user belongs to no role-granting group", () => {
    render(<InheritedRolesField roles={[]} />);
    expect(
      screen.getByText("This user belongs to no group that grants a role.")
    ).toBeInTheDocument();
  });
});
