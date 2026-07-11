import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { customChoicePicker } from "./choicePicker";
import { SurfaceResolvedContext } from "./surfaceResolvedContext";

interface TestChoicePickerProps {
  value?: string[];
  variant?: string;
  displayStyle?: string;
  options?: { label: string; value: string }[];
  setValue: (v: string[]) => void;
  filterable?: boolean;
  label?: string;
}

// See button.test.tsx for why `createComponentImplementation` is mocked to
// expose the render function directly instead of driving the full `@a2ui/web_core` binder.
vi.mock("@a2ui/react/v0_9", () => ({
  createComponentImplementation: (
    _api: unknown,
    RenderComponent: (p: {
      props: TestChoicePickerProps;
      context: { componentModel: { id: string } };
    }) => unknown
  ) => ({ render: RenderComponent }),
}));

const Render = customChoicePicker.render as unknown as (p: {
  props: TestChoicePickerProps;
  context: { componentModel: { id: string } };
}) => ReactNode;

const options = [
  { label: "Cat", value: "cat" },
  { label: "Dog", value: "dog" },
];

describe("customChoicePicker", () => {
  it("toggles a selection when the surface is not resolved", async () => {
    const setValue = vi.fn();
    render(
      <SurfaceResolvedContext.Provider value={false}>
        <Render
          props={{ value: [], variant: "mutuallyExclusive", options, setValue }}
          context={{ componentModel: { id: "cp1" } }}
        />
      </SurfaceResolvedContext.Provider>
    );
    const radio = screen.getByRole("radio", { name: "Cat" });
    expect(radio).not.toBeDisabled();
    await userEvent.click(radio);
    expect(setValue).toHaveBeenCalledWith(["cat"]);
  });

  it("is inert and never calls setValue when the surface is resolved", async () => {
    const setValue = vi.fn();
    render(
      <SurfaceResolvedContext.Provider value={true}>
        <Render
          props={{ value: [], variant: "mutuallyExclusive", options, setValue }}
          context={{ componentModel: { id: "cp1" } }}
        />
      </SurfaceResolvedContext.Provider>
    );
    const radio = screen.getByRole("radio", { name: "Cat" });
    expect(radio).toBeDisabled();
    await userEvent.click(radio);
    expect(setValue).not.toHaveBeenCalled();
  });

  it("disables chip-style options too", () => {
    render(
      <SurfaceResolvedContext.Provider value={true}>
        <Render
          props={{ value: [], displayStyle: "chips", options, setValue: vi.fn() }}
          context={{ componentModel: { id: "cp1" } }}
        />
      </SurfaceResolvedContext.Provider>
    );
    expect(screen.getByRole("button", { name: "Cat" })).toBeDisabled();
  });
});
