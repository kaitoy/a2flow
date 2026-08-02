import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FormField } from "./form-field";

describe("FormField", () => {
  it("labels the control it wraps", () => {
    render(
      <FormField htmlFor="name" label="Name">
        <input id="name" />
      </FormField>
    );

    expect(screen.getByLabelText(/Name/)).toBe(screen.getByRole("textbox"));
  });

  it("marks a required field with an asterisk", () => {
    render(
      <FormField htmlFor="name" label="Name" required>
        <input id="name" />
      </FormField>
    );

    expect(screen.getByText("*")).toHaveClass("text-accent");
  });

  it("omits the asterisk when the field is optional", () => {
    render(
      <FormField htmlFor="name" label="Name">
        <input id="name" />
      </FormField>
    );

    expect(screen.queryByText("*")).not.toBeInTheDocument();
  });

  it("renders inline error text below the control", () => {
    render(
      <FormField htmlFor="name" label="Name" error="Name is required">
        <input id="name" />
      </FormField>
    );

    expect(screen.getByText("Name is required")).toHaveClass("text-error");
  });

  it("renders an action alongside the label", () => {
    render(
      <FormField
        htmlFor="name"
        label="Name"
        action={
          <button type="button" aria-label="Show diff">
            diff
          </button>
        }
      >
        <input id="name" />
      </FormField>
    );

    expect(screen.getByRole("button", { name: "Show diff" })).toBeInTheDocument();
  });

  it("renders no action slot by default", () => {
    render(
      <FormField htmlFor="name" label="Name">
        <input id="name" />
      </FormField>
    );

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
