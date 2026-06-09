"use client";

import { useCallback, useEffect } from "react";
import { listNotifications } from "@/lib/api";
import logger from "@/lib/logger";
import { useAppDispatch } from "@/store/hooks";
import {
  notificationsError,
  notificationsLoading,
  setNotifications,
} from "@/store/notificationsSlice";

/** How often (ms) to poll the backend for new notifications. */
const POLL_INTERVAL_MS = 30_000;

/**
 * Poll the notifications endpoint and keep the Redux notifications slice in sync.
 *
 * Fetches immediately on mount and then every {@link POLL_INTERVAL_MS}, clearing
 * the interval on unmount. Components that mount this hook (the toolbar bell) can
 * read the resulting `items` / `unreadCount` from the store. Returns a `refresh`
 * callback so callers can force an out-of-band reload (e.g. after marking an item
 * read).
 */
export function useNotifications(): { refresh: () => Promise<void> } {
  const dispatch = useAppDispatch();

  const refresh = useCallback(async () => {
    dispatch(notificationsLoading());
    try {
      const items = await listNotifications();
      dispatch(setNotifications(items));
    } catch (error) {
      logger.error({ error }, "failed to fetch notifications");
      dispatch(notificationsError());
    }
  }, [dispatch]);

  useEffect(() => {
    let active = true;
    const tick = () => {
      if (active) void refresh();
    };
    tick();
    const id = setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [refresh]);

  return { refresh };
}
