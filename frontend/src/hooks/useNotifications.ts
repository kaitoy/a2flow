"use client";

import { useCallback, useEffect } from "react";
import { listNotifications, UNREAD_ONLY_FILTER } from "@/lib/api";
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
 * Poll the notifications endpoint for unread items and keep the Redux
 * notifications slice in sync.
 *
 * Fetches immediately on mount and then every {@link POLL_INTERVAL_MS}, clearing
 * the interval on unmount. Only unread notifications are requested, since the
 * bell and its dropdown exist to surface what still needs attention — the full
 * history, read items included, lives on the profile page instead. Components
 * that mount this hook (the toolbar bell) can read the resulting `items` /
 * `unreadCount` from the store. Returns a `refresh` callback so callers can
 * force an out-of-band reload (e.g. after marking an item read).
 *
 * Notifications are tenant-scoped, so a platform-scoped (super_admin) caller with
 * no tenant selected yet has nothing to fetch -- polling is held off until the
 * tenant switcher (`components/admin/tenant-switcher.tsx`) resolves a selection,
 * avoiding a spurious 403 on first login before its auto-select effect has run.
 *
 * The polling loop also resets and fetches immediately whenever the effective
 * user id changes -- notably when an admin starts or stops impersonating
 * another user (`ImpersonationIndicator`) -- so the unread badge reflects the
 * new effective user right away instead of waiting up to {@link POLL_INTERVAL_MS}.
 */
export function useNotifications(): { refresh: () => Promise<void> } {
  const dispatch = useAppDispatch();
  const user = useAppSelector((s) => s.auth.user);
  const selectedTenantId = useAppSelector((s) => s.auth.selectedTenantId);
  const tenantReady = user == null || user.tenantId != null || selectedTenantId != null;
  const userId = user?.id ?? null;

  const refresh = useCallback(async () => {
    dispatch(notificationsLoading());
    try {
      const items = await listNotifications({ filters: [UNREAD_ONLY_FILTER] });
      dispatch(setNotifications(items));
    } catch (err) {
      logger.error({ err }, "failed to fetch notifications");
      dispatch(notificationsError());
    }
  }, [dispatch]);

  // biome-ignore lint/correctness/useExhaustiveDependencies: userId re-triggers an immediate fetch when the effective user changes (e.g. impersonation start/stop)
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
  }, [refresh, tenantReady, userId]);

  return { refresh };
}
