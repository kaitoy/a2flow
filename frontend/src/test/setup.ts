import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { store } from "@/store";
import { dismissToast } from "@/store/toastSlice";
import { server } from "./msw/server";

beforeAll(() => server.listen({ onUnhandledRequest: "warn" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// `api.ts` dispatches error toasts to the real singleton store (not the
// isolated per-test store `test-utils.tsx` creates), so clear it after every
// test or a toast from one test leaks into the next.
afterEach(() => {
  for (const toast of store.getState().toast.items) {
    store.dispatch(dismissToast(toast.id));
  }
});

Element.prototype.scrollIntoView = vi.fn();

// jsdom doesn't implement matchMedia. React Spring's useReducedMotion
// (via @react-spring/shared) calls it on mount, so provide a minimal stub.
if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}

// jsdom doesn't implement ResizeObserver. SlidingIndicator uses it to track
// layout changes for the active-item bar, so stub it with no-ops.
if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

// jsdom doesn't implement IntersectionObserver. MessageList uses it for the
// workflow scroll-spy, so stub it with no-ops (it never fires under jsdom).
if (!window.IntersectionObserver) {
  window.IntersectionObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  } as unknown as typeof IntersectionObserver;
}

vi.mock("@/lib/logger", () => ({
  default: {
    info: vi.fn(),
    error: vi.fn(),
    debug: vi.fn(),
    warn: vi.fn(),
  },
}));
