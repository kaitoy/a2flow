"""The one place a notification is both persisted and queued for email.

Notifications are produced from four places — the agent's task and approval
tools, the workflow-design job, and run-completion bookkeeping — and every one
of them used to call ``NotificationRepository.create`` directly. Adding email at
each site would have meant four copies of the same "resolve the recipient, look
up the relay, swallow every failure" logic, so this dispatcher sits in front of
the repository instead and all four now go through it.

**The email is queued, not sent.** This used to open an SMTP connection inline
and swallow whatever came back, which meant a relay that was down for a minute
lost the message for good. Now the dispatcher writes a row to
``outbound_emails`` and returns; :class:`services.email_queue_worker.
EmailQueueWorker` drains that queue, at a controlled rate, retrying what is
worth retrying.

**Both rows are written in one transaction.** That is why this service holds an
``AsyncSession`` — a deliberate exception to the convention that a service holds
only repositories. Writing the notification and its email in separate commits
would leave a window where a crash produces a notification whose email was never
queued, which is precisely the failure the queue exists to eliminate. Owning the
unit of work is the dispatcher's whole job here, so it owns the session:
:meth:`NotificationRepository.stage` and
:meth:`OutboundEmailRepository.stage` both add without committing, and the
single commit below decides that either both rows exist or neither does.

Queuing is still **best-effort and always second**. Everything about resolving
the recipient and the relay is wrapped in a blanket ``except Exception`` and
logged, so a misconfigured deployment degrades the feature back to in-app
notifications rather than breaking the workflow operation that triggered one.

:meth:`NotificationDispatcher.exists_for_session` is a pass-through to the
repository so the dispatcher drops straight into
:func:`services.workflow_execution_completion.evaluate_completion`, which needs
both that idempotency check and ``create``.
"""

import logging

from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.secret_cipher import get_secret_cipher
from models.notification import Notification, NotificationCreate, NotificationType
from models.outbound_email import OutboundEmailCreate
from models.user import SYSTEM_USER_ID, User
from repositories import (
    NotificationRepository,
    OutboundEmailRepository,
    SqlNotificationRepository,
    SqlOutboundEmailRepository,
    SqlSystemSettingsRepository,
    SqlUserRepository,
    UserRepository,
)
from repositories._integrity import commit_or_translate_user_fk
from services.system_settings import SystemSettingsService

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """Persists a notification and, in the same transaction, queues its email."""

    def __init__(
        self,
        db: AsyncSession,
        notifications: NotificationRepository,
        users: UserRepository,
        settings: SystemSettingsService,
        emails: OutboundEmailRepository,
    ) -> None:
        """Initialize the dispatcher.

        Args:
            db: The session both staged rows are committed through. See the
                module docstring for why the dispatcher owns the unit of work.
            notifications: Repository persisting the notification row.
            users: Repository used to resolve the recipient's email address.
            settings: Service supplying the resolved SMTP configuration.
            emails: Repository the outgoing message is queued on.
        """
        self._db = db
        self._notifications = notifications
        self._users = users
        self._settings = settings
        self._emails = emails

    async def create(self, data: NotificationCreate, *, user_id: str) -> Notification:
        """Persist a notification and queue its email, atomically.

        Args:
            data: The notification to create; ``user_id`` on it is the recipient.
            user_id: The acting user recorded in the audit fields.

        Returns:
            The persisted notification.
        """
        notification = self._notifications.stage(data, user_id=user_id)
        await self._try_enqueue(notification, user_id=user_id)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(notification)
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

    async def _try_enqueue(self, notification: Notification, *, user_id: str) -> None:
        """Stage the outgoing email, swallowing and logging every failure.

        The message is rendered here rather than by the worker: the recipient's
        address, their eligibility to receive mail, and the deployment's base
        URL are facts about the moment the notification was produced, and
        freezing them keeps the worker free of any notion of tenants, users, or
        notification kinds.

        Args:
            notification: The notification being announced, already staged.
            user_id: The acting user recorded in the queue row's audit fields.
        """
        try:
            if await self._settings.resolve_smtp() is None:
                return
            recipient = await self._resolve_recipient(notification.user_id)
            if recipient is None:
                return
            settings = await self._settings.get()
            self._emails.stage(
                OutboundEmailCreate(
                    notification_id=notification.id,
                    to_email=recipient,
                    subject=notification.title,
                    body=_build_body(notification, base_url=settings.app_base_url),
                ),
                user_id=user_id,
            )
        except Exception:
            logger.exception(
                "failed to queue email for %s notification %s",
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


def _deep_link(notification: Notification, *, base_url: str) -> str:
    """Build the URL that takes the recipient to what the notification is about.

    Args:
        notification: The notification being delivered.
        base_url: Base URL of the deployment, without a trailing slash.

    Returns:
        An absolute URL into the web UI, built from the notification's own
        ``link`` (resolved once at creation time by
        :func:`models.notification.build_notification_link`), or the
        notification centre when it has none.
    """
    root = base_url.rstrip("/")
    if notification.link:
        return f"{root}{notification.link}"
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
        db,
        SqlNotificationRepository(db, tenant_id=tenant_id),
        SqlUserRepository(db),
        SystemSettingsService(SqlSystemSettingsRepository(db), get_secret_cipher()),
        SqlOutboundEmailRepository(db, tenant_id=tenant_id),
    )
