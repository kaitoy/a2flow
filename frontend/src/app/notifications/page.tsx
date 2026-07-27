/** @module NotificationsPage — Dedicated page for the signed-in user's full notification history. */
import { NotificationList } from "@/components/notifications/NotificationList";

/**
 * Notifications page for the signed-in user, reachable from the account menu
 * (`UserMenu`'s "Notifications" item). Renders the full read+unread
 * notification history via {@link NotificationList}.
 *
 * Unlike `ProfilePage`, this page needs no local auth guard: `NotificationList`
 * takes no props and reads nothing from the auth slice, and the surrounding
 * `NotificationsLayout` already gates rendering on authentication via
 * `AuthProvider` before this component ever mounts.
 */
export default function NotificationsPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 p-4 sm:p-8">
      <h1 className="font-display text-3xl font-semibold tracking-tight text-gradient-accent">
        Notifications
      </h1>
      <NotificationList />
    </div>
  );
}
