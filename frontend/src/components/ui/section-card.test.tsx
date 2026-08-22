import { UserRound } from "lucide-react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@/test/test-utils";
import { SectionCard } from "./section-card";

describe("SectionCard", () => {
  it("renders the title as an h2", () => {
    render(
      <SectionCard icon={UserRound} title="Account">
        <p>body</p>
      </SectionCard>
    );
    expect(screen.getByRole("heading", { level: 2, name: "Account" })).toBeInTheDocument();
  });

  it("renders its children below the heading", () => {
    render(
      <SectionCard icon={UserRound} title="Account">
        <p>body</p>
      </SectionCard>
    );
    expect(screen.getByText("body")).toBeInTheDocument();
  });

  it("keeps the icon decorative so the heading is the section's only accessible name", () => {
    const { container } = render(
      <SectionCard icon={UserRound} title="Account">
        <p>body</p>
      </SectionCard>
    );
    const icon = container.querySelector("svg");
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it("merges extra classes onto the card", () => {
    const { container } = render(
      <SectionCard icon={UserRound} title="Account" className="mt-4">
        <p>body</p>
      </SectionCard>
    );
    const card = container.querySelector("section");
    expect(card).toHaveClass("glass-panel-strong", "mt-4");
  });
});
