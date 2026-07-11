import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { SurfaceResolvedContext } from "./surfaceResolvedContext";
import { customTextField } from "./textField";

// See button.test.tsx for why `createComponentImplementation` is mocked to
// expose the render function directly instead of driving the full `@a2ui/web_core` binder.
vi.mock("@a2ui/react/v0_9", () => ({
  createComponentImplementation: (
    _api: unknown,
    RenderComponent: (p: {
      props: {
        variant?: string;
        value?: string;
        setValue?: (v: string) => void;
        validationErrors?: string[];
        label?: string;
      };
    }) => unknown
  ) => ({ render: RenderComponent }),
}));

const Render = customTextField.render as unknown as (p: {
  props: {
    variant?: string;
    value?: string;
    setValue?: (v: string) => void;
    validationErrors?: string[];
    label?: string;
  };
}) => ReactNode;

describe("customTextField", () => {
  it("is editable when the surface is not resolved", () => {
    render(
      <SurfaceResolvedContext.Provider value={false}>
        <Render props={{ value: "hi", setValue: vi.fn(), label: "Name" }} />
      </SurfaceResolvedContext.Provider>
    );
    expect(screen.getByLabelText("Name")).not.toBeDisabled();
  });

  it("is disabled when the surface is resolved", () => {
    render(
      <SurfaceResolvedContext.Provider value={true}>
        <Render props={{ value: "hi", setValue: vi.fn(), label: "Name" }} />
      </SurfaceResolvedContext.Provider>
    );
    expect(screen.getByLabelText("Name")).toBeDisabled();
  });

  it("disables the multi-line Textarea variant too", () => {
    render(
      <SurfaceResolvedContext.Provider value={true}>
        <Render props={{ variant: "longText", value: "hi", setValue: vi.fn(), label: "Notes" }} />
      </SurfaceResolvedContext.Provider>
    );
    expect(screen.getByLabelText("Notes")).toBeDisabled();
  });
});
