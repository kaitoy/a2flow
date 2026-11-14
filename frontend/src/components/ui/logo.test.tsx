import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Logo } from "./logo";

describe("Logo", () => {
  it("renders the mark as a labelled image in the accent color", () => {
    render(<Logo />);
    const logo = screen.getByRole("img", { name: "A2Flow logo" });
    expect(logo).toHaveClass("text-accent");
    expect(logo.querySelector("path")).toHaveAttribute("d");
  });

  it("applies the sizing classes it is given", () => {
    render(<Logo className="size-10" />);
    expect(screen.getByRole("img", { name: "A2Flow logo" })).toHaveClass("size-10", "text-accent");
  });
});
