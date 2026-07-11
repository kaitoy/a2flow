import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { customButton } from "./button";
import { SurfaceResolvedContext } from "./surfaceResolvedContext";

// `customButton` is a `ReactComponentImplementation` whose `.render` is built by
// `@a2ui/web_core`'s generic prop binder from a `ComponentContext`; mocking
// `createComponentImplementation` to hand back the render function we passed in
// (mirroring how the project already mocks `@a2ui/react`/`@a2ui/web_core` at the
// `A2uiRenderer` boundary — see frontend-patterns.md) lets it be exercised
// directly with hand-built props instead of the full binder machinery.
vi.mock("@a2ui/react/v0_9", () => ({
  createComponentImplementation: (
    _api: unknown,
    RenderComponent: (p: {
      props: { variant?: string; action?: () => void; isValid?: boolean; child?: string | null };
      buildChild: (id: string) => ReactNode;
      context: unknown;
    }) => ReactNode
  ) => ({ render: RenderComponent }),
}));

const Render = customButton.render as unknown as (p: {
  props: { variant?: string; action?: () => void; isValid?: boolean; child?: string | null };
  buildChild: (id: string) => ReactNode;
  context: unknown;
}) => ReactNode;

describe("customButton", () => {
  it("is interactive and fires action when the surface is not resolved", async () => {
    const action = vi.fn();
    render(
      <SurfaceResolvedContext.Provider value={false}>
        <Render
          props={{ variant: "primary", action, isValid: true, child: null }}
          buildChild={vi.fn()}
          context={{}}
        />
      </SurfaceResolvedContext.Provider>
    );
    const button = screen.getByRole("button");
    expect(button).not.toBeDisabled();
    await userEvent.click(button);
    expect(action).toHaveBeenCalled();
  });

  it("is disabled when the surface is resolved, even though the action would otherwise be valid", () => {
    render(
      <SurfaceResolvedContext.Provider value={true}>
        <Render
          props={{ variant: "primary", action: vi.fn(), isValid: true, child: null }}
          buildChild={vi.fn()}
          context={{}}
        />
      </SurfaceResolvedContext.Provider>
    );
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("stays disabled for an invalid form regardless of resolved state", () => {
    render(
      <SurfaceResolvedContext.Provider value={false}>
        <Render
          props={{ variant: "primary", action: vi.fn(), isValid: false, child: null }}
          buildChild={vi.fn()}
          context={{}}
        />
      </SurfaceResolvedContext.Provider>
    );
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
