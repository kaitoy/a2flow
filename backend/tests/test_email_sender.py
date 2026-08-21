"""Tests for the SMTP adapter's message building and connection handling.

The adapter has no business rules, so the things worth pinning down are the
wire-level ones: which ``smtplib`` client a security mode selects, whether AUTH
is attempted, and that a transport failure becomes :class:`EmailSendError`
rather than leaking a raw ``smtplib`` exception into a caller's ``except``.
"""

import smtplib
from typing import Any

import pytest

from infrastructure.email_sender import SmtpConfig, SmtpEmailSender, build_message
from models.system_settings import SmtpSecurity
from repositories.exceptions import EmailSendError


def _config(**overrides: Any) -> SmtpConfig:
    """Build a configuration with sensible defaults for the tests."""
    fields: dict[str, Any] = {
        "host": "smtp.example.com",
        "port": 2525,
        "security": SmtpSecurity.none,
        "username": None,
        "password": None,
        "from_email": "a2flow@example.com",
        "from_name": None,
    }
    fields.update(overrides)
    return SmtpConfig(**fields)


class _FakeClient:
    """Stand-in for ``smtplib.SMTP`` recording the calls the sender makes."""

    instances: list["_FakeClient"] = []

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.calls: list[str] = []
        self.logged_in: tuple[str, str] | None = None
        self.messages: list[Any] = []
        _FakeClient.instances.append(self)

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.calls.append("quit")

    def starttls(self) -> None:
        self.calls.append("starttls")

    def ehlo(self) -> None:
        self.calls.append("ehlo")

    def login(self, username: str, password: str) -> None:
        self.logged_in = (username, password)

    def send_message(self, message: Any) -> None:
        self.messages.append(message)


@pytest.fixture(autouse=True)
def _reset_instances() -> None:
    """Clear the recorded clients between tests."""
    _FakeClient.instances = []


# ---------- message building ----------


def test_message_carries_the_bare_address_without_a_display_name() -> None:
    message = build_message(_config(), to="x@example.com", subject="s", body="b")
    assert message["From"] == "a2flow@example.com"
    assert message["To"] == "x@example.com"
    assert message["Subject"] == "s"


def test_message_pairs_the_display_name_with_the_address() -> None:
    message = build_message(
        _config(from_name="A2Flow"), to="x@example.com", subject="s", body="b"
    )
    assert message["From"] == "A2Flow <a2flow@example.com>"


def test_message_body_is_plain_text() -> None:
    message = build_message(_config(), to="x@example.com", subject="s", body="hello")
    assert message.get_content_type() == "text/plain"
    assert message.get_content().strip() == "hello"


# ---------- connection handling ----------


async def test_plain_security_skips_starttls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _FakeClient)
    await SmtpEmailSender().send(_config(), to="x@example.com", subject="s", body="b")
    client = _FakeClient.instances[0]
    assert "starttls" not in client.calls
    assert len(client.messages) == 1


async def test_starttls_upgrades_and_re_greets(monkeypatch: pytest.MonkeyPatch) -> None:
    """EHLO must be repeated after STARTTLS: the upgrade resets the session."""
    monkeypatch.setattr(smtplib, "SMTP", _FakeClient)
    await SmtpEmailSender().send(
        _config(security=SmtpSecurity.starttls),
        to="x@example.com",
        subject="s",
        body="b",
    )
    assert _FakeClient.instances[0].calls[:2] == ["starttls", "ehlo"]


async def test_ssl_security_uses_the_implicit_tls_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtplib, "SMTP_SSL", _FakeClient)
    monkeypatch.setattr(smtplib, "SMTP", _unusable_client)
    await SmtpEmailSender().send(
        _config(security=SmtpSecurity.ssl), to="x@example.com", subject="s", body="b"
    )
    assert _FakeClient.instances[0].port == 2525


async def test_no_login_without_a_username(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _FakeClient)
    await SmtpEmailSender().send(_config(), to="x@example.com", subject="s", body="b")
    assert _FakeClient.instances[0].logged_in is None


async def test_login_is_attempted_with_a_username(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _FakeClient)
    await SmtpEmailSender().send(
        _config(username="mailer", password="hunter2"),
        to="x@example.com",
        subject="s",
        body="b",
    )
    assert _FakeClient.instances[0].logged_in == ("mailer", "hunter2")


@pytest.mark.parametrize(
    "failure",
    [smtplib.SMTPAuthenticationError(535, b"nope"), OSError("Connection refused")],
)
async def test_transport_failures_become_email_send_error(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def _raise(*_: object, **__: object) -> None:
        raise failure

    monkeypatch.setattr(smtplib, "SMTP", _raise)
    with pytest.raises(EmailSendError):
        await SmtpEmailSender().send(
            _config(), to="x@example.com", subject="s", body="b"
        )


def _unusable_client(*_: object, **__: object) -> None:
    """Fail loudly if the plain client is selected where TLS was configured."""
    raise AssertionError("plain SMTP client used for an ssl-secured configuration")
