import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AccessDeniedState } from "./access-denied-state";

const backMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ back: backMock }),
}));

describe("AccessDeniedState", () => {
  it("renders the default title and description", () => {
    render(<AccessDeniedState fill="screen" />);
    expect(screen.getByRole("heading", { name: "Access denied" })).toBeInTheDocument();
    expect(screen.getByText("You don't have permission to view this page.")).toBeInTheDocument();
  });

  it("renders a custom title and description", () => {
    render(
      <AccessDeniedState fill="full" title="No access" description="Ask an admin for permission." />
    );
    expect(screen.getByRole("heading", { name: "No access" })).toBeInTheDocument();
    expect(screen.getByText("Ask an admin for permission.")).toBeInTheDocument();
  });

  it("calls router.back() when 'Go back' is clicked", async () => {
    render(<AccessDeniedState fill="screen" />);
    await userEvent.click(screen.getByRole("button", { name: "Go back" }));
    expect(backMock).toHaveBeenCalledOnce();
  });
});
