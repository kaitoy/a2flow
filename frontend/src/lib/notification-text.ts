/** @module notification-text — A notification's title and body in the language on screen. */
import type { Translator } from "@/i18n/translate";
import type { Notification } from "@/lib/api";

/** What {@link notificationText} produces. */
export interface NotificationText {
  title: string;
  body: string | null | undefined;
}

/**
 * Translate the fixed wording of a notification's type, filling it from `params`.
 *
 * The backend stores English, which email carries. What has no fixed wording stays
 * as stored: an approval's agent-written title and description, a failure reason.
 * A notification written before `params` existed has no values to fill, so wording
 * that needs one stays as stored too.
 *
 * @param notification - The notification.
 * @param t - The translator for the language on screen.
 * @returns The title and body to show.
 */
export function notificationText(notification: Notification, t: Translator): NotificationText {
  const { title, body } = notification;
  const params = (notification.params ?? {}) as Record<string, string | number>;
  switch (notification.type) {
    case "workflow_draft_ready":
      return {
        title: t("notifications.workflow_draft_ready.title"),
        body: t("notifications.workflow_draft_ready.body"),
      };
    case "workflow_generation_failed":
      return { title: t("notifications.workflow_generation_failed.title"), body };
    case "execution_completed":
      return {
        title: t("notifications.execution_completed.title"),
        body:
          params.count === undefined ? body : t("notifications.execution_completed.body", params),
      };
    case "elicitation_request":
      return {
        title:
          params.taskTitle === undefined
            ? title
            : t("notifications.elicitation_request.title", params),
        body: t("notifications.elicitation_request.body"),
      };
    default:
      return { title, body };
  }
}
