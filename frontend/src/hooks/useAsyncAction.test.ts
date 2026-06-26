import { act, renderHook } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAsyncAction } from "./useAsyncAction";

/** A promise plus its resolver/rejector, for driving an action to settle on demand. */
function deferred<T = void>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("useAsyncAction", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("skips the pending stage when the action resolves within the delay", async () => {
    const { result } = renderHook(() => useAsyncAction());
    const d = deferred();

    let runPromise: Promise<void>;
    act(() => {
      runPromise = result.current.run(() => d.promise);
    });

    // In flight immediately, but the pending label has not appeared yet.
    expect(result.current.inFlight).toBe(true);
    expect(result.current.status).toBe("idle");

    // Resolve before the 200ms pending delay elapses.
    await act(async () => {
      d.resolve();
      await runPromise;
    });

    expect(result.current.status).toBe("done");
    expect(result.current.inFlight).toBe(false);

    // The done stage reverts to idle after its duration.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(result.current.status).toBe("idle");
  });

  it("shows the pending stage when the action is slower than the delay", async () => {
    const { result } = renderHook(() => useAsyncAction());
    const d = deferred();

    let runPromise: Promise<void>;
    act(() => {
      runPromise = result.current.run(() => d.promise);
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });
    expect(result.current.status).toBe("pending");

    await act(async () => {
      d.resolve();
      await runPromise;
    });
    expect(result.current.status).toBe("done");
  });

  it("goes straight back to idle on success when showDone is false", async () => {
    const { result } = renderHook(() => useAsyncAction({ showDone: false }));
    const d = deferred();

    let runPromise: Promise<void>;
    act(() => {
      runPromise = result.current.run(() => d.promise);
    });
    await act(async () => {
      d.resolve();
      await runPromise;
    });

    expect(result.current.status).toBe("idle");
    expect(result.current.inFlight).toBe(false);
  });

  it("reverts to idle and rethrows when the action fails", async () => {
    const { result } = renderHook(() => useAsyncAction());

    await act(async () => {
      await expect(result.current.run(() => Promise.reject(new Error("boom")))).rejects.toThrow(
        "boom"
      );
    });

    expect(result.current.status).toBe("idle");
    expect(result.current.inFlight).toBe(false);
  });

  it("ignores a concurrent run while one is already in flight", async () => {
    const { result } = renderHook(() => useAsyncAction());
    const d = deferred();
    const second = vi.fn(() => Promise.resolve());

    let firstRun: Promise<void>;
    act(() => {
      firstRun = result.current.run(() => d.promise);
    });

    await act(async () => {
      await expect(result.current.run(second)).rejects.toThrow();
    });
    expect(second).not.toHaveBeenCalled();

    await act(async () => {
      d.resolve();
      await firstRun;
    });
  });

  it("still settles under StrictMode's mount/unmount/remount cycle", async () => {
    // StrictMode remounts the hook in development; the mountedRef must be
    // re-asserted on remount or every post-await state update is skipped and the
    // action hangs (status stuck idle, inFlight stuck true).
    const { result } = renderHook(() => useAsyncAction(), { wrapper: StrictMode });
    const d = deferred();

    let runPromise: Promise<void>;
    act(() => {
      runPromise = result.current.run(() => d.promise);
    });

    await act(async () => {
      d.resolve();
      await runPromise;
    });

    expect(result.current.status).toBe("done");
    expect(result.current.inFlight).toBe(false);
  });

  it("does not update state after unmount", async () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const { result, unmount } = renderHook(() => useAsyncAction());
    const d = deferred();

    let runPromise: Promise<void>;
    act(() => {
      runPromise = result.current.run(() => d.promise);
    });

    unmount();

    await act(async () => {
      d.resolve();
      await runPromise;
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});
