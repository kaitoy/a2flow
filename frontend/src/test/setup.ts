import "@testing-library/jest-dom/vitest";
import { configure } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";
import { store } from "@/store";
import { dismissToast } from "@/store/toastSlice";
import { server } from "./msw/server";

// Testing Library's 1000ms default for `findBy*` / `waitFor` is too tight for a
// page that fetches on mount: the `pre-commit` hook runs this suite alongside
// backend-pytest, and under that load the MSW round-trip plus re-render has
// missed the deadline while the component was still showing its skeleton. The
// budget only bounds a failure, so a generous one costs nothing on the passing
// path. Vitest's own `testTimeout` (vitest.config.ts) is raised past this so a
// genuine timeout reports as the failed assertion rather than a killed test.
configure({ asyncUtilTimeout: 5_000 });

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

// `useColumnVisibility` persists the viewer's column choices, and the DOM
// environment (with its localStorage) is shared by every test in a file — so a
// test that opens the column picker would otherwise decide which columns the
// next test's table renders. Only the column keys are cleared: tests around the
// theme and the selected tenant manage their own keys.
afterEach(() => {
  for (const key of Object.keys(window.localStorage)) {
    if (key.startsWith("a2flow.columns.")) window.localStorage.removeItem(key);
  }
});

// happy-dom's scrollIntoView is a no-op anyway; a spy lets tests assert that a
// component scrolled its target into view.
Element.prototype.scrollIntoView = vi.fn();

// NOTE: `matchMedia`, `ResizeObserver`, and `IntersectionObserver` used to be
// stubbed here because jsdom implements none of them. happy-dom ships all
// three, so the stubs are gone. What happy-dom still lacks is a layout engine —
// every measurement (`offsetWidth`, `getBoundingClientRect`, …) reads back
// zero — so tests that depend on real sizes stub those per file.

vi.mock("@/lib/logger", () => ({
  default: {
    info: vi.fn(),
    error: vi.fn(),
    debug: vi.fn(),
    warn: vi.fn(),
  },
}));
