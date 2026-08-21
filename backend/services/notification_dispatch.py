"""The one place a notification is both persisted and delivered by email.

Notifications are produced from four places — the agent's task and approval
tools, the workflow-design job, and run-completion bookkeeping — and every one
of them used to call ``NotificationRepository.create`` directly. Adding email at
each site would have meant four copies of the same "resolve the recipient, look
up the relay, swallow every failure" logic, so this dispatcher sits in front of
the repository instead and all four now go through it.

Email is **strictly best-effort and always second**. The row is written first
and its failure propagates as before; the send that follows is wrapped in a
blanket ``except Exception`` and logged, so a misconfigured relay degrades the
feature back to in-app notifications rather than breaking the workflow
operation that triggered one. That matches the convention every calling site
already applies to notification creation itself.

:meth:`NotificationDispatcher.exists_for_session` is a pass-through to the
repository so the dispatcher drops straight into
:func:`services.workflow_execution_completion.evaluate_completion`, which needs
both that idempotency check and ``create``.
"""

import logging

from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.email_sender import SmtpEmailSender, get_email_sender
from infrastructure.secret_cipher import get_secret_cipher
from models.notification import Notification, NotificationCreate, NotificationType
from models.user import SYSTEM_USER_ID, User
from repositories import (
    NotificationRepository,
    SqlNotificationRepository,
    SqlSystemSettingsRepository,
    SqlUserRepository,
    UserRepository,
)
from services.system_settings import SystemSettingsService

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Persists a notification and then tries to deliver it by email."""

    def __init__(
        self,
        notifications: NotificationRepository,
        users: UserRepository,
        settings: SystemSettingsService,
        sender: SmtpEmailSender,
    ) -> None:
        """Initialize the dispatcher.

        Args:
            notifications: Repository persisting the notification row.
            users: Repository used to resolve the recipient's email address.
            settings: Service supplying the resolved SMTP configuration.
            sender: Adapter that talks to the SMTP relay.
        """
        self._notifications = notifications
        self._users = users
        self._settings = settings
        self._sender = sender

    async def create(self, data: NotificationCreate, *, user_id: str) -> Notification:
        """Persist a notification, then email the recipient if delivery is configured.

        Args:
            data: The notification to create; ``user_id`` on it is the recipient.
            user_id: The acting user recorded in the audit fields.

        Returns:
            The persisted notification.
        """
        notification = await self._notifications.create(data, user_id=user_id)
        await self._try_email(notification)
        return notification

    async def exists_for_session(
        self, workflow_execution_id: str, notification_type: NotificationType
    ) -> bool:
        """Return whether a notification of this type already exists for the run.

        Pass-through to the repository, so callers that need both the idempotency
        check and ``create`` can hold the dispatcher alone.

        Args:
            workflow_execution_id: The run to check.
            notification_type: The one-shot event kind to look for.

        Returns:
            ``True`` if such a notification already exists.
        """
        return await self._notifications.exists_for_session(
            workflow_execution_id, notification_type
        )

    async def _try_email(self, notification: Notification) -> None:
        """Send the notification by email, swallowing and logging every failure.

        Args:
            notification: The already-persisted notification to deliver.
        """
        try:
            config = await self._settings.resolve_smtp()
            if config is None:
                return
            recipient = await self._resolve_recipient(notification.user_id)
            if recipient is None:
                return
            settings = await self._settings.get()
            body = _build_body(notification, base_url=settings.app_base_url)
            await self._sender.send(
                config,
                to=recipient,
                subject=notification.title,
                body=body,
            )
        except Exception:
            logger.exception(
                "failed to email %s notification %s",
                notification.type,
                notification.id,
            )

    async def _resolve_recipient(self, user_id: str) -> str | None:
        """Return the address to email, or ``None`` when there is nobody to reach.

        Args:
            user_id: The notification's recipient.

        Returns:
            The recipient's email address, or ``None`` if the recipient is the
            seeded system user, has been disabled or soft-deleted, has not
            verified their email address, or carries no address.
        """
        if user_id == SYSTEM_USER_ID:
            return None
        user: User | None = await self._users.get(user_id)
        if (
            user is None
            or not user.enabled
            or user.deleted_at is not None
            or not user.email_verified
        ):
            return None
        return user.email or None


#: Route each notification kind deep-links to, relative to the configured base
#: URL. Run-scoped kinds point at the execution; workflow-scoped ones at the
#: workflow. Anything else falls back to the notification centre.
_EXECUTION_KINDS = frozenset(
    {NotificationType.approval_request, NotificationType.execution_completed}
)
_WORKFLOW_KINDS = frozenset(
    {
        NotificationType.workflow_draft_ready,
        NotificationType.workflow_generation_failed,
    }
)


def _deep_link(notification: Notification, *, base_url: str) -> str:
    """Build the URL that takes the recipient to what the notification is about.

    Args:
        notification: The notification being delivered.
        base_url: Base URL of the deployment, without a trailing slash.

    Returns:
        An absolute URL into the web UI.
    """
    root = base_url.rstrip("/")
    if notification.type in _EXECUTION_KINDS and notification.workflow_execution_id:
        return f"{root}/admin/workflow-executions/{notification.workflow_execution_id}"
    if notification.type in _WORKFLOW_KINDS and notification.workflow_id:
        return f"{root}/admin/workflows/{notification.workflow_id}"
    return f"{root}/notifications"


def _build_body(notification: Notification, *, base_url: str | None) -> str:
    """Compose the plain-text message body for a notification.

    Args:
        notification: The notification being delivered.
        base_url: Base URL of the deployment, or ``None`` when unconfigured — in
            which case the message carries no link rather than a broken one.

    Returns:
        The message body.
    """
    lines = [notification.title]
    if notification.body:
        lines.extend(["", notification.body])
    if base_url:
        lines.extend(["", _deep_link(notification, base_url=base_url)])
    return "\n".join(lines) + "\n"


def build_notification_dispatcher(
    db: AsyncSession, *, tenant_id: str
) -> NotificationDispatcher:
    """Assemble a dispatcher for a caller that builds its own repositories.

    The agent tools and background jobs run outside FastAPI's request scope on a
    session of their own, so they cannot use the ``Depends``-wired
    ``NotificationDispatcherDep``. This factory gives them the same object in one
    line.

    Args:
        db: The session the caller already opened.
        tenant_id: Tenant the notification belongs to, already resolved by the
            caller.

    Returns:
        A dispatcher bound to that session and tenant.
    """
    return NotificationDispatcher(
        SqlNotificationRepository(db, tenant_id=tenant_id),
        SqlUserRepository(db),
        SystemSettingsService(SqlSystemSettingsRepository(db), get_secret_cipher()),
        get_email_sender(),
    )
