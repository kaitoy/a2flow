"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Lifecycle stage of an async action, used to drive a button's label. */
export type AsyncStatus = "idle" | "pending" | "done";

/** Default delay before a slow action surfaces its `pending` stage. */
const DEFAULT_PENDING_DELAY_MS = 200;
/** Default duration the `done` stage stays visible before reverting to `idle`. */
const DEFAULT_DONE_DURATION_MS = 2000;

/** Options for {@link useAsyncAction}. */
export interface UseAsyncActionOptions {
  /**
   * Delay in ms before switching to the `pending` stage. Responses faster than
   * this skip `pending` entirely (optimistic UI). Defaults to 200.
   */
  pendingDelayMs?: number;
  /** How long the `done` stage stays visible before reverting to `idle`. Defaults to 2000. */
  doneDurationMs?: number;
  /**
   * Whether to surface a `done` stage on success. When false the status goes
   * straight back to `idle` after the action resolves. Defaults to true.
   */
  showDone?: boolean;
}

/** Return value of {@link useAsyncAction}. */
export interface UseAsyncAction {
  /** Current lifecycle stage for label rendering. */
  status: AsyncStatus;
  /** True from the moment the action starts until it settles; use for `disabled`. */
  inFlight: boolean;
  /** Wraps an async action, managing the status lifecycle. Resolves/throws like the action. */
  run: <T>(action: () => Promise<T>) => Promise<T>;
}

/**
 * Drives the three-stage lifecycle of a server-submitting button
 * (`idle → pending → done → idle`) with optimistic UI and double-submit guards.
 *
 * On {@link UseAsyncAction.run}, the button is marked {@link UseAsyncAction.inFlight}
 * immediately (disable it to prevent double clicks). The `pending` stage only
 * appears if the action takes longer than {@link UseAsyncActionOptions.pendingDelayMs},
 * so fast responses never flash a "Saving…" label. On success the status becomes
 * `done` for {@link UseAsyncActionOptions.doneDurationMs} (unless `showDone` is
 * false) and then reverts to `idle`; on failure it reverts to `idle` and the
 * error is re-thrown so callers can surface it. All timers are cleared and state
 * updates are guarded after unmount.
 */
export function useAsyncAction(options: UseAsyncActionOptions = {}): UseAsyncAction {
  const {
    pendingDelayMs = DEFAULT_PENDING_DELAY_MS,
    doneDurationMs = DEFAULT_DONE_DURATION_MS,
    showDone = true,
  } = options;

  const [status, setStatus] = useState<AsyncStatus>("idle");
  const [inFlight, setInFlight] = useState(false);

  // Synchronous guard against re-entry before the `inFlight` state has flushed.
  const runningRef = useRef(false);
  const mountedRef = useRef(true);
  const pendingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const doneTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const clearTimers = useCallback(() => {
    if (pendingTimer.current) {
      clearTimeout(pendingTimer.current);
      pendingTimer.current = null;
    }
    if (doneTimer.current) {
      clearTimeout(doneTimer.current);
      doneTimer.current = null;
    }
  }, []);

  useEffect(() => {
    // Re-assert on every mount: React StrictMode (and Fast Refresh) mounts,
    // unmounts, then remounts in development, and the cleanup below flips this
    // to false. Without resetting it here the ref would stay false after the
    // remount, so every post-await state update (status, inFlight) would be
    // silently skipped and the button would hang disabled.
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearTimers();
    };
  }, [clearTimers]);

  const run = useCallback(
    async <T>(action: () => Promise<T>): Promise<T> => {
      if (runningRef.current) {
        return Promise.reject(new Error("Action already in progress"));
      }
      runningRef.current = true;
      clearTimers();
      setInFlight(true);
      setStatus("idle");
      pendingTimer.current = setTimeout(() => {
        if (mountedRef.current) setStatus("pending");
      }, pendingDelayMs);

      try {
        const result = await action();
        clearTimers();
        if (mountedRef.current) {
          if (showDone) {
            setStatus("done");
            doneTimer.current = setTimeout(() => {
              if (mountedRef.current) setStatus("idle");
            }, doneDurationMs);
          } else {
            setStatus("idle");
          }
        }
        return result;
      } catch (err) {
        clearTimers();
        if (mountedRef.current) setStatus("idle");
        throw err;
      } finally {
        runningRef.current = false;
        if (mountedRef.current) setInFlight(false);
      }
    },
    [clearTimers, pendingDelayMs, doneDurationMs, showDone]
  );

  return { status, inFlight, run };
}
