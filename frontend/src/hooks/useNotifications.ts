"use client";

import { useCallback, useEffect } from "react";
import { listNotifications } from "@/lib/api";
import logger from "@/lib/logger";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
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
 *
 * Notifications are tenant-scoped, so a platform-scoped (super_admin) caller with
 * no tenant selected yet has nothing to fetch -- polling is held off until the
 * tenant switcher (`components/admin/tenant-switcher.tsx`) resolves a selection,
 * avoiding a spurious 403 on first login before its auto-select effect has run.
 */
export function useNotifications(): { refresh: () => Promise<void> } {
  const dispatch = useAppDispatch();
  const user = useAppSelector((s) => s.auth.user);
  const selectedTenantId = useAppSelector((s) => s.auth.selectedTenantId);
  const tenantReady = user == null || user.tenantId != null || selectedTenantId != null;

  const refresh = useCallback(async () => {
    dispatch(notificationsLoading());
    try {
      const items = await listNotifications();
      dispatch(setNotifications(items));
    } catch (err) {
      logger.error({ err }, "failed to fetch notifications");
      dispatch(notificationsError());
    }
  }, [dispatch]);

  useEffect(() => {
    if (!tenantReady) return;
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
  }, [refresh, tenantReady]);

  return { refresh };
}
