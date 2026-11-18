"""Tests for self-service sign-up (``POST /auth/signup`` and ``/auth/signup/complete``)."""

import re
from collections.abc import AsyncGenerator, Iterator
from dataclasses import dataclass, field
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, Response

from config import get_settings
from dependencies.auth import SESSION_COOKIE_NAME
from dependencies.service import get_system_settings_service
from dependencies.singletons import get_email_sender
from infrastructure.email_sender import SmtpConfig
from main import app
from models.system_settings import SmtpSecurity
from repositories.exceptions import EmailSendError
from repositories.tenant import SqlTenantRepository
from services.signup import tenant_name_for
from tests._envelope import assert_err, assert_ok

FORM = {
    "email": "new@example.com",
    "username": "New.User",
    "firstName": "New",
    "lastName": "User",
    "password": "a-long-password-1",
}

SMTP = SmtpConfig(
    host="smtp.example.com",
    port=25,
    security=SmtpSecurity.none,
    username=None,
    password=None,
    from_email="a2flow@example.com",
    from_name=None,
)


@dataclass
class FakeMail:
    """Stands in for the SMTP relay and the System Settings it is read from."""

    smtp: SmtpConfig | None = SMTP
    fail: bool = False
    sent: list[tuple[str, str]] = field(default_factory=list)

    async def resolve_smtp(self) -> SmtpConfig | None:
        """Return the configured relay, or ``None`` when delivery is off."""
        return self.smtp

    async def send(
        self, config: SmtpConfig, *, to: str, subject: str, body: str
    ) -> None:
        """Record the message, or fail like an unreachable relay."""
        if self.fail:
            raise EmailSendError("relay down")
        self.sent.append((to, body))

    def token(self) -> str:
        """Return the token from the last confirmation link sent."""
        match = re.search(r"http://a2\.test/signup/verify#(\S+)", self.sent[-1][1])
        assert match, self.sent[-1][1]
        return match.group(1)


@pytest_asyncio.fixture()
async def mail(
    auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[FakeMail, None]:
    """Turn sign-up on, behind a fake relay; ``auth_client`` clears the overrides."""
    monkeypatch.setenv("SIGNUP_ENABLED", "true")
    monkeypatch.setenv("APP_BASE_URL", "http://a2.test")
    get_settings.cache_clear()
    fake = FakeMail()
    app.dependency_overrides[get_system_settings_service] = lambda: fake
    app.dependency_overrides[get_email_sender] = lambda: fake
    yield fake


async def _complete(client: AsyncClient, token: str) -> Response:
    return await client.post("/api/v1/auth/signup/complete", json={"token": token})


def test_tenant_name_is_a_slug_of_the_username() -> None:
    assert tenant_name_for("John.Doe_").rsplit("-", 1)[0] == "john-doe"
    assert tenant_name_for("...").startswith("tenant-")
    assert len(tenant_name_for("a" * 64)) == 57


@pytest.mark.asyncio
async def test_signup_mails_a_link_that_creates_the_tenant_and_signs_in(
    auth_client: AsyncClient, mail: FakeMail
) -> None:
    resp = await auth_client.post("/api/v1/auth/signup", json=FORM)
    assert assert_ok(resp) is None
    assert SESSION_COOKIE_NAME not in resp.cookies
    assert [to for to, _ in mail.sent] == ["new@example.com"]

    resp = await _complete(auth_client, mail.token())
    data = assert_ok(resp)
    assert SESSION_COOKIE_NAME in resp.cookies
    name = data["tenantName"]
    assert name.startswith("new-user-")
    assert data["tenantUrl"] == f"http://{name}.a2.test"
    assert data["user"]["roles"] == ["admin"]
    assert data["user"]["emailVerified"] is True

    me = assert_ok(await auth_client.get("/api/v1/auth/me"))["user"]
    assert me["username"] == "New.User"

    auth_client.cookies.clear()
    login = await auth_client.post(
        "/api/v1/auth/login",
        json={"username": "New.User", "password": FORM["password"], "tenantName": name},
    )
    assert assert_ok(login)["id"] == data["user"]["id"]


@pytest.mark.asyncio
async def test_a_link_works_once(auth_client: AsyncClient, mail: FakeMail) -> None:
    assert_ok(await auth_client.post("/api/v1/auth/signup", json=FORM))
    token = mail.token()
    assert_ok(await _complete(auth_client, token))
    assert_err(await _complete(auth_client, token), "INVALID_SIGNUP_LINK", 422)


@pytest.mark.asyncio
@pytest.mark.usefixtures("mail")
async def test_an_unknown_link_is_refused(auth_client: AsyncClient) -> None:
    assert_err(await _complete(auth_client, "nope"), "INVALID_SIGNUP_LINK", 422)


@pytest.mark.asyncio
async def test_an_expired_link_is_refused(
    auth_client: AsyncClient, mail: FakeMail, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("services.signup.CONFIRMATION_TTL", timedelta(seconds=-1))
    assert_ok(await auth_client.post("/api/v1/auth/signup", json=FORM))
    assert_err(await _complete(auth_client, mail.token()), "INVALID_SIGNUP_LINK", 422)


@pytest.mark.asyncio
async def test_one_address_gets_one_mail_a_minute(
    auth_client: AsyncClient, mail: FakeMail
) -> None:
    assert_ok(await auth_client.post("/api/v1/auth/signup", json=FORM))
    again = await auth_client.post("/api/v1/auth/signup", json=FORM)
    assert_err(again, "TOO_MANY_SIGNUP_REQUESTS", 429)
    other = {**FORM, "email": "other@example.com"}
    assert_ok(await auth_client.post("/api/v1/auth/signup", json=other))
    assert len(mail.sent) == 2


@pytest.mark.asyncio
async def test_a_failed_send_stores_nothing(
    auth_client: AsyncClient, mail: FakeMail
) -> None:
    mail.fail = True
    resp = await auth_client.post("/api/v1/auth/signup", json=FORM)
    assert_err(resp, "EMAIL_SEND_FAILED", 502)
    mail.fail = False
    # Not throttled: the failed attempt left no pending sign-up behind.
    assert_ok(await auth_client.post("/api/v1/auth/signup", json=FORM))


@pytest.mark.asyncio
async def test_signup_is_refused_while_disabled(auth_client: AsyncClient) -> None:
    resp = await auth_client.post("/api/v1/auth/signup", json=FORM)
    assert_err(resp, "FORBIDDEN", 403)


@pytest.mark.asyncio
async def test_signup_is_refused_without_email_delivery(
    auth_client: AsyncClient, mail: FakeMail
) -> None:
    mail.smtp = None
    resp = await auth_client.post("/api/v1/auth/signup", json=FORM)
    assert_err(resp, "FORBIDDEN", 403)
    assert mail.sent == []


@pytest.mark.asyncio
@pytest.mark.usefixtures("mail")
@pytest.mark.parametrize(
    "override", [{"password": "short"}, {"username": "me@example.com"}]
)
async def test_signup_validates_the_form(
    auth_client: AsyncClient, override: dict[str, str]
) -> None:
    resp = await auth_client.post("/api/v1/auth/signup", json={**FORM, **override})
    assert_err(resp, "VALIDATION_ERROR", 422)


@pytest.mark.asyncio
async def test_signup_retries_a_taken_tenant_name(
    auth_client: AsyncClient, mail: FakeMail, monkeypatch: pytest.MonkeyPatch
) -> None:
    suffixes: Iterator[str] = iter(["aaaaaa", "aaaaaa", "bbbbbb"])
    monkeypatch.setattr("services.signup.secrets.token_hex", lambda _n: next(suffixes))
    tokens = []
    for email in ("a@example.com", "b@example.com"):
        assert_ok(
            await auth_client.post("/api/v1/auth/signup", json={**FORM, "email": email})
        )
        tokens.append(mail.token())
    first = assert_ok(await _complete(auth_client, tokens[0]))
    second = assert_ok(await _complete(auth_client, tokens[1]))
    assert first["tenantName"] == "new-user-aaaaaa"
    assert second["tenantName"] == "new-user-bbbbbb"


@pytest.fixture()
def tenants_full(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every tenant-limit check report the deployment as full."""

    async def full(_self: SqlTenantRepository) -> bool:
        return True

    monkeypatch.setattr(SqlTenantRepository, "at_capacity", full)


@pytest.mark.asyncio
@pytest.mark.usefixtures("tenants_full")
async def test_signup_is_refused_at_the_tenant_limit(
    auth_client: AsyncClient, mail: FakeMail
) -> None:
    resp = await auth_client.post("/api/v1/auth/signup", json=FORM)
    assert_err(resp, "TENANT_LIMIT_REACHED", 409)
    assert mail.sent == []


@pytest.mark.asyncio
async def test_a_link_is_refused_once_the_limit_is_reached_and_works_after_it_is_lifted(
    auth_client: AsyncClient, mail: FakeMail, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert_ok(await auth_client.post("/api/v1/auth/signup", json=FORM))
    token = mail.token()
    with monkeypatch.context() as m:

        async def full(_self: SqlTenantRepository) -> bool:
            return True

        m.setattr(SqlTenantRepository, "at_capacity", full)
        assert_err(await _complete(auth_client, token), "TENANT_LIMIT_REACHED", 409)
    # The pending sign-up was kept, so the same link works once there is room.
    assert_ok(await _complete(auth_client, token))


@pytest.mark.asyncio
@pytest.mark.usefixtures("mail", "tenants_full")
async def test_login_options_hide_signup_at_the_tenant_limit(
    auth_client: AsyncClient,
) -> None:
    resp = await auth_client.get(
        "/api/v1/auth/login-options", params={"host": "a2.test"}
    )
    assert assert_ok(resp)["signup"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("host", "smtp", "expected"),
    [("a2.test", SMTP, True), ("acme.a2.test", SMTP, False), ("a2.test", None, False)],
)
async def test_login_options_offer_signup_only_where_it_works(
    auth_client: AsyncClient,
    mail: FakeMail,
    host: str,
    smtp: SmtpConfig | None,
    expected: bool,
) -> None:
    mail.smtp = smtp
    resp = await auth_client.get("/api/v1/auth/login-options", params={"host": host})
    assert assert_ok(resp)["signup"] is expected
