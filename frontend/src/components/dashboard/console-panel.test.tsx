import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConsoleFrame, ConsolePanel } from "./console-panel";

describe("ConsolePanel", () => {
  it("is a region named by its title, with the hint and aside beside it", () => {
    render(
      <ConsolePanel title="Lead time" hint="Average per day" aside={<span>2h</span>}>
        <p>chart</p>
      </ConsolePanel>
    );
    const panel = screen.getByRole("region", { name: "Lead time" });
    expect(panel).toHaveClass("console-panel");
    expect(panel).toHaveTextContent("Average per day");
    expect(panel).toHaveTextContent("2h");
    expect(panel).toHaveTextContent("chart");
  });
});

describe("ConsoleFrame", () => {
  it("follows the app theme in the standard look, which is the default", () => {
    const { container } = render(
      <ConsoleFrame>
        <p>body</p>
      </ConsoleFrame>
    );
    const root = container.firstElementChild;
    expect(root).toHaveClass("dashboard");
    expect(root).not.toHaveClass("console");
    expect(root).not.toHaveAttribute("data-theme");
  });

  it("pins the dark theme on the console root whatever the app theme is", () => {
    const { container } = render(
      <ConsoleFrame look="console">
        <p>body</p>
      </ConsoleFrame>
    );
    const root = container.firstElementChild;
    expect(root).toHaveClass("dashboard", "console");
    expect(root).toHaveAttribute("data-theme", "dark");
  });
});
