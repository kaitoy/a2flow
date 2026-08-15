import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Radio } from "./radio";

describe("Radio", () => {
  it("renders with its label as the accessible name", () => {
    render(<Radio label="Local" />);
    expect(screen.getByRole("radio", { name: "Local" })).toBeInTheDocument();
  });

  it("reflects the checked prop", () => {
    render(<Radio label="Local" checked readOnly />);
    expect(screen.getByRole("radio", { name: "Local" })).toBeChecked();
  });

  it("fires onChange when picked", async () => {
    const onChange = vi.fn();
    render(<Radio label="Local" onChange={onChange} />);
    await userEvent.click(screen.getByRole("radio", { name: "Local" }));
    expect(onChange).toHaveBeenCalledOnce();
  });

  it("can be disabled", () => {
    render(<Radio label="Local" disabled />);
    expect(screen.getByRole("radio", { name: "Local" })).toBeDisabled();
  });

  it("keeps the label as the accessible name while hiding it visually", () => {
    render(<Radio label="github-token" labelHidden />);
    expect(screen.getByRole("radio", { name: "github-token" })).toBeInTheDocument();
    expect(screen.getByText("github-token")).toHaveClass("sr-only");
  });

  it("drops the row padding and hover chrome when the label is hidden", () => {
    render(<Radio label="github-token" labelHidden />);
    const wrapper = screen.getByRole("radio", { name: "github-token" }).closest("label");
    expect(wrapper).toHaveClass("inline-flex");
    expect(wrapper).not.toHaveClass("px-3");
  });

  it("keeps the row padding and hover chrome by default", () => {
    render(<Radio label="github-token" />);
    const wrapper = screen.getByRole("radio", { name: "github-token" }).closest("label");
    expect(wrapper).toHaveClass("px-3");
  });

  it("lets only one radio of a shared name be checked at a time", async () => {
    render(
      <>
        <Radio label="Local" name="kind" />
        <Radio label="Vault" name="kind" />
      </>
    );
    await userEvent.click(screen.getByRole("radio", { name: "Local" }));
    expect(screen.getByRole("radio", { name: "Local" })).toBeChecked();

    await userEvent.click(screen.getByRole("radio", { name: "Vault" }));
    expect(screen.getByRole("radio", { name: "Vault" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Local" })).not.toBeChecked();
  });
});
