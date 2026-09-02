"""Tests for the notification dispatcher's email side effect.

The dispatcher's contract is narrow but load-bearing: the notification row and
the queued email are written in one transaction, the message is rendered from
what was true when the notification was produced, recipients who cannot or
should not receive mail are skipped before anything is queued, and a failure on
the email side never costs the notification.
"""

from collections.abc import AsyncGenerator, Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.bootstrap import seed_system_settings, seed_system_user
from infrastructure.secret_cipher import get_secret_cipher
from models.notification import (
    Notification,
    NotificationCreate,
    NotificationType,
    build_notification_link,
)
from models.outbound_email import (
    OutboundEmail,
    OutboundEmailCreate,
    OutboundEmailRead,
    OutboundEmailStatus,
)
from models.system_settings import (
    SYSTEM_SETTINGS_ID,
    SmtpSecurity,
    SystemSettings,
)
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID, User
from models.workflow_execution import WorkflowExecution
from repositories import (
    SqlNotificationRepository,
    SqlSystemSettingsRepository,
    SqlUserRepository,
)
from repositories.query import FilterSpec, SortSpec
from services.notification_dispatch import (
    NotificationDispatcher,
    _deep_link,
    build_notification_dispatcher,
)
from services.system_settings import SystemSettingsService
from tests._engine import make_test_engine

_TENANT_ID = "tenant-dispatch"
_RECIPIENT_ID = "recipient"


async def _seed(session: AsyncSession, **user_overrides: Any) -> None:
    """Seed the baseline rows every dispatch test needs."""
    await seed_system_user(session)
    await seed_system_settings(session)
    session.add(
        Tenant(
            id=_TENANT_ID,
            display_name="Dispatch Tenant",
            name=_TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
    )
    await session.commit()
    fields: dict[str, Any] = {
        "id": _RECIPIENT_ID,
        "username": _RECIPIENT_ID,
        "first_name": "Recipient",
        "last_name": "Test",
        "password": "testpassword",
        "email": "recipient@example.com",
        "email_verified": True,
        "tenant_id": _TENANT_ID,
        "created_by": SYSTEM_USER_ID,
        "updated_by": SYSTEM_USER_ID,
    }
    fields.update(user_overrides)
    session.add(User(**fields))
    await session.commit()


async def _seed_execution(session: AsyncSession, *, execution_id: str = "run-1") -> str:
    """Insert a WorkflowExecution owned by the seeded recipient and return its id."""
    execution = WorkflowExecution(
        id=execution_id,
        session_id=f"session-for-{execution_id}",
        name="wf",
        workflow_prompt="do it",
        agent_skill_id="skill-1",
        agent_skill_name="skill",
        agent_skill_repo_url="https://example.com/repo",
        agent_skill_repo_path=".",
        skill_dir="/tmp/skill",
        initiator_id=_RECIPIENT_ID,
        tenant_id=_TENANT_ID,
        created_by=_RECIPIENT_ID,
        updated_by=_RECIPIENT_ID,
    )
    session.add(execution)
    await session.commit()
    await session.refresh(execution)
    return execution.id


async def _enable_smtp(session: AsyncSession, **overrides: Any) -> None:
    """Switch email delivery on with a complete configuration."""
    settings = await session.get(SystemSettings, SYSTEM_SETTINGS_ID)
    assert settings is not None
    settings.smtp_enabled = True
    settings.smtp_host = "smtp.example.com"
    settings.smtp_port = 2525
    settings.smtp_security = SmtpSecurity.none
    settings.smtp_from_email = "a2flow@example.com"
    settings.app_base_url = "http://localhost:3000"
    for key, value in overrides.items():
        setattr(settings, key, value)
    session.add(settings)
    await session.commit()


@pytest_asyncio.fixture()
async def session() -> AsyncGenerator[AsyncSession, None]:
    """A throwaway database session with the schema created."""
    mem_engine = await make_test_engine()
    async with AsyncSession(mem_engine) as db:
        yield db
    await mem_engine.dispose()


def _dispatcher(db: AsyncSession) -> NotificationDispatcher:
    """Build a dispatcher wired to the test session."""
    return build_notification_dispatcher(db, tenant_id=_TENANT_ID)


async def _queued(session: AsyncSession) -> list[OutboundEmail]:
    """Return every message sitting in the outgoing queue, oldest first."""
    result = await session.exec(
        select(OutboundEmail).order_by(col(OutboundEmail.created_at))
    )
    return list(result.all())


def _payload(**overrides: Any) -> NotificationCreate:
    """Build a notification payload addressed to the seeded recipient."""
    fields: dict[str, Any] = {
        "user_id": _RECIPIENT_ID,
        "type": NotificationType.approval_request,
        "title": "Approval requested",
        "body": "Please review the deployment plan.",
    }
    fields.update(overrides)
    return NotificationCreate(**fields)


async def test_email_is_queued_when_smtp_is_configured(session: AsyncSession) -> None:
    await _seed(session)
    await _enable_smtp(session)
    notification = await _dispatcher(session).create(_payload(), user_id=_RECIPIENT_ID)

    queued = await _queued(session)

    assert len(queued) == 1
    assert queued[0].to_email == "recipient@example.com"
    assert queued[0].subject == "Approval requested"
    assert queued[0].notification_id == notification.id
    assert queued[0].tenant_id == _TENANT_ID


async def test_nothing_is_sent_inline(session: AsyncSession) -> None:
    """The whole point of the queue: `create` must not touch a relay itself."""
    await _seed(session)
    await _enable_smtp(session)

    await _dispatcher(session).create(_payload(), user_id=_RECIPIENT_ID)

    assert (await _queued(session))[0].sent_at is None


async def test_the_notification_and_its_email_commit_together(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Neither row may survive alone; that window is what the queue exists to close."""
    await _seed(session)
    await _enable_smtp(session)

    async def _boom(*_: Any, **__: Any) -> None:
        raise RuntimeError("commit failed")

    monkeypatch.setattr(
        "services.notification_dispatch.commit_or_translate_user_fk", _boom
    )
    with pytest.raises(RuntimeError):
        await _dispatcher(session).create(_payload(), user_id=_RECIPIENT_ID)
    await session.rollback()

    assert await _queued(session) == []
    result = await session.exec(select(Notification))
    assert result.all() == []


async def test_body_carries_the_notification_text(session: AsyncSession) -> None:
    await _seed(session)
    await _enable_smtp(session)
    await _dispatcher(session).create(_payload(), user_id=_RECIPIENT_ID)
    assert "Please review the deployment plan." in (await _queued(session))[0].body


async def test_body_deep_links_to_the_notification_centre_without_a_target(
    session: AsyncSession,
) -> None:
    await _seed(session)
    await _enable_smtp(session)
    await _dispatcher(session).create(_payload(), user_id=_RECIPIENT_ID)
    assert "http://localhost:3000/notifications" in (await _queued(session))[0].body


async def test_body_deep_links_an_approval_request_to_the_session_chat(
    session: AsyncSession,
) -> None:
    """The email link for a run-scoped notification is the chat, not the admin record."""
    await _seed(session)
    await _enable_smtp(session)
    execution_id = await _seed_execution(session)
    notification = await _dispatcher(session).create(
        _payload(workflow_execution_id=execution_id), user_id=_RECIPIENT_ID
    )
    assert notification.link == f"/workflow-executions/{execution_id}/session"
    assert (
        f"http://localhost:3000/workflow-executions/{execution_id}/session"
        in (await _queued(session))[0].body
    )


@pytest.mark.parametrize(
    ("notification_type", "field", "expected"),
    [
        (
            NotificationType.approval_request,
            "workflow_execution_id",
            "/workflow-executions/run-1/session",
        ),
        (
            NotificationType.execution_completed,
            "workflow_execution_id",
            "/workflow-executions/run-1/session",
        ),
        (
            NotificationType.workflow_draft_ready,
            "workflow_id",
            "/admin/workflows/wf-1",
        ),
        (
            NotificationType.workflow_generation_failed,
            "workflow_id",
            "/admin/workflows/wf-1",
        ),
    ],
)
def test_build_notification_link_routes_each_kind_to_what_it_is_about(
    notification_type: NotificationType, field: str, expected: str
) -> None:
    link = build_notification_link(
        notification_type,
        workflow_execution_id="run-1" if field == "workflow_execution_id" else None,
        workflow_id="wf-1" if field == "workflow_id" else None,
    )
    assert link == expected


def test_build_notification_link_is_none_without_the_relevant_id() -> None:
    assert (
        build_notification_link(
            NotificationType.approval_request,
            workflow_execution_id=None,
            workflow_id=None,
        )
        is None
    )


def test_deep_link_prefixes_the_stored_link_with_the_base_url() -> None:
    """Checked on the model directly: `_deep_link` only concatenates, it no longer branches."""
    notification = Notification.model_construct(
        id="n-1", type=NotificationType.approval_request, title="t", link="/foo/bar"
    )
    assert (
        _deep_link(notification, base_url="http://localhost:3000/")
        == "http://localhost:3000/foo/bar"
    )


def test_deep_link_falls_back_to_the_notification_centre_without_a_link() -> None:
    notification = Notification.model_construct(
        id="n-1", type=NotificationType.approval_request, title="t", link=None
    )
    assert (
        _deep_link(notification, base_url="http://localhost:3000/")
        == "http://localhost:3000/notifications"
    )


async def test_body_omits_the_link_when_no_base_url_is_configured(
    session: AsyncSession,
) -> None:
    await _seed(session)
    await _enable_smtp(session, app_base_url=None)
    await _dispatcher(session).create(_payload(), user_id=_RECIPIENT_ID)
    assert "http" not in (await _queued(session))[0].body


async def test_nothing_is_queued_when_delivery_is_disabled(
    session: AsyncSession,
) -> None:
    """Delivery off means no rows accumulate, not a queue nobody drains."""
    await _seed(session)
    await _dispatcher(session).create(_payload(), user_id=_RECIPIENT_ID)
    assert await _queued(session) == []


async def test_nothing_is_queued_for_the_system_user(session: AsyncSession) -> None:
    await _seed(session)
    await _enable_smtp(session)
    await _dispatcher(session).create(
        _payload(user_id=SYSTEM_USER_ID), user_id=_RECIPIENT_ID
    )
    assert await _queued(session) == []


async def test_nothing_is_queued_for_a_disabled_recipient(
    session: AsyncSession,
) -> None:
    await _seed(session, enabled=False)
    await _enable_smtp(session)
    await _dispatcher(session).create(_payload(), user_id=_RECIPIENT_ID)
    assert await _queued(session) == []


async def test_nothing_is_queued_for_a_soft_deleted_recipient(
    session: AsyncSession,
) -> None:
    await _seed(session, deleted_at=datetime.now(UTC))
    await _enable_smtp(session)
    await _dispatcher(session).create(_payload(), user_id=_RECIPIENT_ID)
    assert await _queued(session) == []


async def test_nothing_is_queued_for_an_unverified_recipient(
    session: AsyncSession,
) -> None:
    await _seed(session, email_verified=False)
    await _enable_smtp(session)
    await _dispatcher(session).create(_payload(), user_id=_RECIPIENT_ID)
    assert await _queued(session) == []


async def test_notification_survives_a_failure_on_the_email_side(
    session: AsyncSession,
) -> None:
    """Queuing is best-effort; a broken email path never costs the notification."""

    class _ExplodingEmails:
        """An OutboundEmailRepository whose only job is to fail on stage."""

        def stage(self, data: OutboundEmailCreate, *, user_id: str) -> OutboundEmail:
            raise RuntimeError("cannot render")

        async def counts_by_status(self) -> dict[OutboundEmailStatus, int]:
            raise AssertionError("the dispatcher never reports on the queue")

        async def oldest_pending_age_seconds(self, *, now: datetime) -> float | None:
            raise AssertionError("the dispatcher never reports on the queue")

        async def get(self, email_id: str) -> OutboundEmailRead | None:
            raise AssertionError("the dispatcher never reads a single row")

        async def list(
            self,
            *,
            limit: int,
            offset: int,
            sort: Sequence[SortSpec] = (),
            filters: Sequence[FilterSpec] = (),
        ) -> list[OutboundEmailRead]:
            raise AssertionError("the dispatcher never lists the queue")

        async def delete(self, email_id: str) -> None:
            raise AssertionError("the dispatcher never deletes a row")

    await _seed(session)
    await _enable_smtp(session)
    dispatcher = NotificationDispatcher(
        session,
        SqlNotificationRepository(session, tenant_id=_TENANT_ID),
        SqlUserRepository(session),
        SystemSettingsService(
            SqlSystemSettingsRepository(session), get_secret_cipher()
        ),
        _ExplodingEmails(),
    )

    notification = await dispatcher.create(_payload(), user_id=_RECIPIENT_ID)

    repo = SqlNotificationRepository(session, tenant_id=_TENANT_ID)
    assert await repo.get(notification.id) is not None
    assert await _queued(session) == []


async def test_an_undecryptable_password_disables_delivery(
    session: AsyncSession,
) -> None:
    """A password encrypted under a different Fernet key must not be sent as-is."""
    await _seed(session)
    await _enable_smtp(session, smtp_username="mailer", smtp_password="not-a-token")
    await _dispatcher(session).create(_payload(), user_id=_RECIPIENT_ID)
    assert await _queued(session) == []


async def test_stored_password_is_decrypted_before_sending(
    session: AsyncSession,
) -> None:
    await _seed(session)
    await _enable_smtp(
        session,
        smtp_username="mailer",
        smtp_password=get_secret_cipher().encrypt("hunter2hunter2"),
    )
    settings_service = SystemSettingsService(
        SqlSystemSettingsRepository(session), get_secret_cipher()
    )
    config = await settings_service.resolve_smtp()
    assert config is not None
    assert config.password == "hunter2hunter2"


async def test_exists_for_session_passes_through(session: AsyncSession) -> None:
    """The pass-through is what lets the dispatcher stand in for the repository."""
    await _seed(session)
    dispatcher = _dispatcher(session)
    assert not await dispatcher.exists_for_session(
        "run-1", NotificationType.execution_completed
    )
