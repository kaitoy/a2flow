import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useMediaQuery } from "./useMediaQuery";

/** Renders the hook's current value so assertions can read it from the DOM. */
function Probe({ query }: { query: string }) {
  const matches = useMediaQuery(query);
  return <span data-testid="result">{String(matches)}</span>;
}

/** Replace `window.matchMedia` with a stub whose `matches` is fixed. */
function stubMatchMedia(matches: boolean) {
  return vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({
        matches,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }) as unknown as MediaQueryList
  );
}

describe("useMediaQuery", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns true when the query matches", () => {
    stubMatchMedia(true);
    render(<Probe query="(pointer: coarse)" />);
    expect(screen.getByTestId("result")).toHaveTextContent("true");
  });

  it("returns false when the query does not match", () => {
    stubMatchMedia(false);
    render(<Probe query="(pointer: coarse)" />);
    expect(screen.getByTestId("result")).toHaveTextContent("false");
  });
});
