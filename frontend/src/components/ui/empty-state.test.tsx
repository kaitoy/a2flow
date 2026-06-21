import { render, screen } from "@testing-library/react";
import { Inbox } from "lucide-react";
import { describe, expect, it } from "vitest";
import { EmptyState } from "./empty-state";

describe("EmptyState", () => {
  it("renders the icon, title, and description", () => {
    const { container } = render(
      <EmptyState icon={Inbox} title="Nothing here" description="Add something to get started." />
    );
    expect(container.querySelector("svg")).not.toBeNull();
    expect(screen.getByRole("heading", { name: "Nothing here" })).toBeInTheDocument();
    expect(screen.getByText("Add something to get started.")).toBeInTheDocument();
  });

  it("renders the description without a heading in compact mode", () => {
    render(<EmptyState icon={Inbox} description="No data." compact />);
    expect(screen.getByText("No data.")).toBeInTheDocument();
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
  });
});
