"""Tests for the super-admin-only system settings routes.

Cover the three things that are easy to get wrong here: the role gate (these
settings are platform infrastructure, so no ``admin`` carve-out), the write-only
handling of ``smtpPassword``, and the merged-result validation that stops
delivery from being switched on with nothing to send through.
"""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.bootstrap import seed_system_settings, seed_system_user
from infrastructure.email_sender import SmtpConfig
from models.system_settings import SYSTEM_SETTINGS_ID, SystemSettings
from models.user import SYSTEM_USER_ID
from tests._envelope import assert_err, assert_ok
from tests.conftest import _install_auth_overrides

_PATH = "/api/v1/system-settings"
_TEST_PATH = f"{_PATH}/smtp/test"

#: A complete, valid configuration used by the tests that need one stored.
_ENABLED_BODY = {
    "smtpEnabled": True,
    "smtpHost": "smtp.example.com",
    "smtpPort": 2525,
    "smtpSecurity": "starttls",
    "smtpFromEmail": "a2flow@example.com",
}


class _RecordingSender:
    """Stand-in for :class:`~infrastructure.email_sender.SmtpEmailSender`.

    Records every send instead of opening a socket, and can be told to fail so
    the 502 path is exercised without a real relay.
    """

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.error: Exception | None = None

    async def send(
        self, config: SmtpConfig, *, to: str, subject: str, body: str
    ) -> None:
        """Record the message, or raise the configured failure."""
        if self.error is not None:
            raise self.error
        self.sent.append({"config": config, "to": to, "subject": subject, "body": body})


@pytest.fixture()
def sender() -> _RecordingSender:
    """Return the recording sender installed by the ``settings_client`` fixture."""
    return _RecordingSender()


@pytest_asyncio.fixture()
async def settings_client(
    sender: _RecordingSender,
) -> AsyncGenerator[AsyncClient, None]:
    """Client bound to an in-memory database with the settings row seeded."""
    from dependencies.singletons import get_email_sender
    from infrastructure.database import get_session
    from main import app
    from models.system_settings import SystemSettings as _SystemSettings  # noqa: F401
    from models.user import User as _User  # noqa: F401 — registers model

    mem_engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @sa_event.listens_for(mem_engine.sync_engine, "connect")
    def _set_fk(dbapi_conn: Any, _: object) -> None:
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with mem_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with AsyncSession(mem_engine) as session:
        await seed_system_user(session)
        await seed_system_settings(session)

    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(mem_engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_email_sender] = lambda: sender
    _install_auth_overrides(app)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-User-Id": SYSTEM_USER_ID},
        ) as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()
        await mem_engine.dispose()


# ---------- authorization ----------


@pytest.mark.parametrize("role", ["admin", "developer", "requester", "approver", ""])
async def test_get_is_forbidden_without_super_admin(
    settings_client: AsyncClient, role: str
) -> None:
    assert_err(
        await settings_client.get(_PATH, headers={"X-User-Roles": role}),
        code="FORBIDDEN",
        status=403,
    )


@pytest.mark.parametrize("role", ["admin", "developer", "requester"])
async def test_patch_is_forbidden_without_super_admin(
    settings_client: AsyncClient, role: str
) -> None:
    assert_err(
        await settings_client.patch(
            _PATH, json={"smtpHost": "relay"}, headers={"X-User-Roles": role}
        ),
        code="FORBIDDEN",
        status=403,
    )


async def test_test_send_is_forbidden_without_super_admin(
    settings_client: AsyncClient,
) -> None:
    assert_err(
        await settings_client.post(_TEST_PATH, headers={"X-User-Roles": "admin"}),
        code="FORBIDDEN",
        status=403,
    )


async def test_get_works_for_a_platform_scoped_caller_without_a_tenant_header(
    settings_client: AsyncClient,
) -> None:
    """A super admin carries no tenant; these routes must not require one."""
    body = assert_ok(await settings_client.get(_PATH, headers={"X-User-Tenant-Id": ""}))
    assert body["smtpEnabled"] is False


# ---------- read ----------


async def test_get_returns_seeded_defaults(settings_client: AsyncClient) -> None:
    body = assert_ok(await settings_client.get(_PATH))
    assert body["smtpEnabled"] is False
    assert body["smtpPort"] == 587
    assert body["smtpSecurity"] == "starttls"
    assert body["smtpHost"] is None
    assert body["smtpPasswordSet"] is False


async def test_get_never_returns_the_password(settings_client: AsyncClient) -> None:
    assert_ok(
        await settings_client.patch(
            _PATH, json={**_ENABLED_BODY, "smtpPassword": "hunter2hunter2"}
        )
    )
    body = assert_ok(await settings_client.get(_PATH))
    assert "smtpPassword" not in body
    assert body["smtpPasswordSet"] is True


# ---------- update ----------


async def test_patch_applies_the_submitted_fields(settings_client: AsyncClient) -> None:
    body = assert_ok(await settings_client.patch(_PATH, json=_ENABLED_BODY))
    assert body["smtpEnabled"] is True
    assert body["smtpHost"] == "smtp.example.com"
    assert body["smtpPort"] == 2525
    assert body["smtpFromEmail"] == "a2flow@example.com"


async def test_patch_leaves_unset_fields_untouched(
    settings_client: AsyncClient,
) -> None:
    assert_ok(await settings_client.patch(_PATH, json=_ENABLED_BODY))
    body = assert_ok(await settings_client.patch(_PATH, json={"smtpPort": 465}))
    assert body["smtpPort"] == 465
    assert body["smtpHost"] == "smtp.example.com"


async def test_password_is_stored_encrypted(settings_client: AsyncClient) -> None:
    """The plaintext must never reach the column -- only Fernet ciphertext."""
    from dependencies.singletons import get_secret_cipher
    from infrastructure.database import get_session
    from main import app

    assert_ok(
        await settings_client.patch(
            _PATH, json={**_ENABLED_BODY, "smtpPassword": "hunter2hunter2"}
        )
    )
    session_factory = app.dependency_overrides[get_session]
    async for session in session_factory():
        stored = await session.get(SystemSettings, SYSTEM_SETTINGS_ID)
        assert stored is not None
        assert stored.smtp_password is not None
        assert stored.smtp_password != "hunter2hunter2"
        assert get_secret_cipher().decrypt(stored.smtp_password) == "hunter2hunter2"
        break


async def test_empty_password_keeps_the_stored_one(
    settings_client: AsyncClient,
) -> None:
    """A blank field in the admin form must not wipe the saved password."""
    assert_ok(
        await settings_client.patch(
            _PATH, json={**_ENABLED_BODY, "smtpPassword": "hunter2hunter2"}
        )
    )
    body = assert_ok(
        await settings_client.patch(_PATH, json={"smtpPassword": "", "smtpPort": 25})
    )
    assert body["smtpPasswordSet"] is True
    assert body["smtpPort"] == 25


async def test_omitted_password_keeps_the_stored_one(
    settings_client: AsyncClient,
) -> None:
    assert_ok(
        await settings_client.patch(
            _PATH, json={**_ENABLED_BODY, "smtpPassword": "hunter2hunter2"}
        )
    )
    body = assert_ok(await settings_client.patch(_PATH, json={"smtpPort": 25}))
    assert body["smtpPasswordSet"] is True


async def test_explicit_null_password_clears_the_stored_password(
    settings_client: AsyncClient,
) -> None:
    """Unlike an empty string, an explicit ``null`` wipes the stored password."""
    from infrastructure.database import get_session
    from main import app

    assert_ok(
        await settings_client.patch(
            _PATH, json={**_ENABLED_BODY, "smtpPassword": "hunter2hunter2"}
        )
    )
    body = assert_ok(
        await settings_client.patch(
            _PATH, json={"smtpEnabled": False, "smtpPassword": None}
        )
    )
    assert body["smtpPasswordSet"] is False

    session_factory = app.dependency_overrides[get_session]
    async for session in session_factory():
        stored = await session.get(SystemSettings, SYSTEM_SETTINGS_ID)
        assert stored is not None
        assert stored.smtp_password is None
        break


async def test_clearing_all_smtp_settings_returns_to_seeded_defaults(
    settings_client: AsyncClient,
) -> None:
    """The bulk-clear PATCH the admin UI sends fully un-configures delivery."""
    assert_ok(
        await settings_client.patch(
            _PATH,
            json={
                **_ENABLED_BODY,
                "smtpUsername": "mailer",
                "smtpPassword": "hunter2hunter2",
            },
        )
    )
    cleared_body = {
        "smtpEnabled": False,
        "smtpHost": None,
        "smtpPort": 587,
        "smtpSecurity": "starttls",
        "smtpUsername": None,
        "smtpPassword": None,
        "smtpFromEmail": None,
        "smtpFromName": None,
    }
    body = assert_ok(await settings_client.patch(_PATH, json=cleared_body))
    assert body["smtpEnabled"] is False
    assert body["smtpHost"] is None
    assert body["smtpPort"] == 587
    assert body["smtpSecurity"] == "starttls"
    assert body["smtpUsername"] is None
    assert body["smtpFromEmail"] is None
    assert body["smtpFromName"] is None
    assert body["smtpPasswordSet"] is False


# ---------- validation ----------


async def test_enabling_without_a_host_is_rejected(
    settings_client: AsyncClient,
) -> None:
    err = assert_err(
        await settings_client.patch(
            _PATH, json={"smtpEnabled": True, "smtpFromEmail": "a@example.com"}
        ),
        code="INVALID_SYSTEM_SETTINGS",
        status=422,
    )
    assert "smtpHost" in err["details"]["reason"]


async def test_enabling_without_a_sender_address_is_rejected(
    settings_client: AsyncClient,
) -> None:
    err = assert_err(
        await settings_client.patch(
            _PATH, json={"smtpEnabled": True, "smtpHost": "smtp.example.com"}
        ),
        code="INVALID_SYSTEM_SETTINGS",
        status=422,
    )
    assert "smtpFromEmail" in err["details"]["reason"]


async def test_username_without_a_password_is_rejected(
    settings_client: AsyncClient,
) -> None:
    err = assert_err(
        await settings_client.patch(
            _PATH, json={**_ENABLED_BODY, "smtpUsername": "mailer"}
        ),
        code="INVALID_SYSTEM_SETTINGS",
        status=422,
    )
    assert "smtpPassword" in err["details"]["reason"]


async def test_disabled_settings_may_be_saved_incomplete(
    settings_client: AsyncClient,
) -> None:
    """Half-finished configuration is fine while delivery is switched off."""
    body = assert_ok(
        await settings_client.patch(_PATH, json={"smtpHost": "smtp.example.com"})
    )
    assert body["smtpEnabled"] is False
    assert body["smtpHost"] == "smtp.example.com"


async def test_out_of_range_port_is_rejected(settings_client: AsyncClient) -> None:
    assert_err(
        await settings_client.patch(_PATH, json={"smtpPort": 70000}),
        code="VALIDATION_ERROR",
        status=422,
    )


async def test_a_private_app_base_url_is_accepted(settings_client: AsyncClient) -> None:
    """The app's own address is often loopback; the SSRF guard must not apply."""
    body = assert_ok(
        await settings_client.patch(_PATH, json={"appBaseUrl": "http://localhost:3000"})
    )
    assert body["appBaseUrl"] == "http://localhost:3000"


# ---------- test send ----------


async def test_test_send_uses_the_stored_configuration(
    settings_client: AsyncClient, sender: _RecordingSender
) -> None:
    assert_ok(
        await settings_client.patch(
            _PATH, json={**_ENABLED_BODY, "smtpPassword": "hunter2hunter2"}
        )
    )
    assert_ok(await settings_client.post(_TEST_PATH))
    assert len(sender.sent) == 1
    config = sender.sent[0]["config"]
    assert config.host == "smtp.example.com"
    assert config.port == 2525
    # Decrypted on the way out, not handed to the relay as ciphertext.
    assert config.password == "hunter2hunter2"


async def test_test_send_targets_the_callers_own_address(
    settings_client: AsyncClient, sender: _RecordingSender
) -> None:
    assert_ok(await settings_client.patch(_PATH, json=_ENABLED_BODY))
    assert_ok(
        await settings_client.post(
            _TEST_PATH, headers={"X-User-Email": "root@example.com"}
        )
    )
    assert sender.sent[0]["to"] == "root@example.com"


async def test_test_send_is_rejected_while_delivery_is_disabled(
    settings_client: AsyncClient, sender: _RecordingSender
) -> None:
    assert_err(
        await settings_client.post(_TEST_PATH),
        code="INVALID_SYSTEM_SETTINGS",
        status=422,
    )
    assert sender.sent == []


async def test_test_send_maps_a_relay_failure_to_502(
    settings_client: AsyncClient, sender: _RecordingSender
) -> None:
    from repositories.exceptions import EmailSendError

    assert_ok(await settings_client.patch(_PATH, json=_ENABLED_BODY))
    sender.error = EmailSendError("Connection refused by smtp.example.com")
    err = assert_err(
        await settings_client.post(_TEST_PATH),
        code="EMAIL_SEND_FAILED",
        status=502,
    )
    # The raw reason stays server-side: it can quote relay banners and the
    # configured AUTH username back at the caller.
    assert "Connection refused" not in str(err)
