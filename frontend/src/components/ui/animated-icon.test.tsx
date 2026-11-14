import { render } from "@testing-library/react";
import { Sparkles } from "lucide-react";
import { describe, expect, it } from "vitest";
import { AnimatedIcon } from "./animated-icon";

describe("AnimatedIcon", () => {
  it("renders the icon as a decorative (aria-hidden) svg", () => {
    const { container } = render(<AnimatedIcon icon={Sparkles} />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });

  it("applies the motion-safe animation class for the chosen animation", () => {
    const { container } = render(<AnimatedIcon icon={Sparkles} animation="wiggle" />);
    expect(container.querySelector("svg")?.getAttribute("class")).toContain(
      "motion-safe:animate-wiggle"
    );
  });

  it("is static by default", () => {
    const { container } = render(<AnimatedIcon icon={Sparkles} />);
    expect(container.querySelector("svg")?.getAttribute("class") ?? "").not.toContain("animate-");
  });

  it("omits the animation class when animation is none", () => {
    const { container } = render(
      <AnimatedIcon icon={Sparkles} animation="none" className="text-accent" />
    );
    const cls = container.querySelector("svg")?.getAttribute("class") ?? "";
    expect(cls).not.toContain("animate-");
    expect(cls).toContain("text-accent");
  });
});
