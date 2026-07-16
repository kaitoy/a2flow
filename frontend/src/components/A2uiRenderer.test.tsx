import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { A2uiRenderer } from "./A2uiRenderer";

// The real dependency chain (catalog + markdown + surface binder) is mocked at
// the `A2uiRenderer` boundary, per frontend-patterns.md. `processMessages` is
// driven by `processImpl`, so each test decides whether the payload processes
// cleanly or throws the way `MessageProcessor` does on invalid A2UI.
const { processImpl } = vi.hoisted(() => ({
  processImpl: vi.fn<(payload: unknown, emit: (surface: unknown) => void) => void>(),
}));

vi.mock("@a2ui/web_core/v0_9", () => ({
  MessageProcessor: class {
    private emit: (surface: unknown) => void = () => {};
    onSurfaceCreated(cb: (surface: unknown) => void) {
      this.emit = cb;
      return { unsubscribe: () => {} };
    }
    processMessages(payload: unknown) {
      processImpl(payload, this.emit);
    }
  },
}));

vi.mock("@a2ui/react/v0_9", () => ({
  A2uiSurface: ({ surface }: { surface: { id: string } }) => (
    <div data-testid="a2ui-surface" data-surface-id={surface.id} />
  ),
  MarkdownContext: { Provider: ({ children }: { children: React.ReactNode }) => children },
}));

vi.mock("@a2ui/markdown-it", () => ({ renderMarkdown: (s: string) => s }));
vi.mock("./a2uiCatalog", () => ({ tailwindCatalog: { id: "test-catalog" } }));

/** A surface the mocked processor hands to `onSurfaceCreated`. */
const makeSurface = (id: string) => ({
  id,
  onAction: { subscribe: () => ({ unsubscribe: () => {} }) },
  dataModel: { get: () => ({}) },
});

describe("A2uiRenderer", () => {
  beforeEach(() => {
    processImpl.mockReset();
  });

  it("renders a surface for a payload that processes cleanly", () => {
    processImpl.mockImplementation((_payload, emit) => {
      emit(makeSurface("s1"));
    });
    render(<A2uiRenderer payload={[{ version: "v0.9" }]} />);
    expect(screen.getByTestId("a2ui-surface")).toHaveAttribute("data-surface-id", "s1");
  });

  it("renders nothing for a nullish payload", () => {
    render(<A2uiRenderer payload={null} />);
    expect(screen.queryByTestId("a2ui-surface")).not.toBeInTheDocument();
    expect(processImpl).not.toHaveBeenCalled();
  });

  it("renders nothing when the payload is invalid A2UI, instead of throwing", () => {
    // What MessageProcessor does with an agent-authored payload whose component
    // has no type: the surface is created, then the components op throws. The
    // half-built surface must not survive, and the throw must not escape into
    // the surrounding message list.
    processImpl.mockImplementation((_payload, emit) => {
      emit(makeSurface("s1"));
      throw new Error("Cannot create component root without a type.");
    });
    expect(() => render(<A2uiRenderer payload={[{ version: "v0.9" }]} />)).not.toThrow();
    expect(screen.queryByTestId("a2ui-surface")).not.toBeInTheDocument();
  });
});
