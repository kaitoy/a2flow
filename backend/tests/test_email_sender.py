"""Tests for the SMTP adapter's message building and connection handling.

The adapter has no business rules, so the things worth pinning down are the
wire-level ones: which ``smtplib`` client a security mode selects, whether AUTH
is attempted, and that a transport failure becomes :class:`EmailSendError`
rather than leaking a raw ``smtplib`` exception into a caller's ``except``.
"""

import smtplib
from typing import Any

import pytest

from infrastructure.email_sender import (
    SmtpConfig,
    SmtpEmailSender,
    build_message,
    is_permanent_failure,
)
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

    #: Exceptions to raise from successive ``send_message`` calls across every
    #: instance; a ``None`` entry, or an index past the end, lets that call
    #: through. Used to script a relay that hangs up mid-batch.
    send_failures: list[Exception | None] = []
    #: How many ``send_message`` calls have been made, across every instance.
    attempts: int = 0

    def starttls(self) -> None:
        self.calls.append("starttls")

    def ehlo(self) -> None:
        self.calls.append("ehlo")

    def login(self, username: str, password: str) -> None:
        self.logged_in = (username, password)

    def send_message(self, message: Any) -> None:
        index = _FakeClient.attempts
        _FakeClient.attempts += 1
        if index < len(_FakeClient.send_failures):
            failure = _FakeClient.send_failures[index]
            if failure is not None:
                raise failure
        self.messages.append(message)

    def quit(self) -> None:
        self.calls.append("quit")

    def close(self) -> None:
        self.calls.append("close")


@pytest.fixture(autouse=True)
def _reset_instances() -> None:
    """Clear the recorded clients and any scripted failures between tests."""
    _FakeClient.instances = []
    _FakeClient.send_failures = []
    _FakeClient.attempts = 0


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


# ---------- connection reuse ----------


async def test_a_session_opens_one_connection_for_a_whole_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This is what makes draining the queue cheap: one handshake, many messages."""
    monkeypatch.setattr(smtplib, "SMTP", _FakeClient)
    sender = SmtpEmailSender()

    async with sender.session(_config()) as smtp:
        for _ in range(3):
            await smtp.send(to="x@example.com", subject="s", body="b")

    assert len(_FakeClient.instances) == 1
    assert len(_FakeClient.instances[0].messages) == 3


async def test_an_empty_session_never_connects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _FakeClient)

    async with SmtpEmailSender().session(_config()):
        pass

    assert _FakeClient.instances == []


async def test_a_session_closes_its_connection_on_the_way_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _FakeClient)

    async with SmtpEmailSender().session(_config()) as smtp:
        await smtp.send(to="x@example.com", subject="s", body="b")

    assert "quit" in _FakeClient.instances[0].calls


async def test_a_dropped_connection_is_reopened_and_the_message_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An idle relay hanging up is bookkeeping, not a delivery failure."""
    monkeypatch.setattr(smtplib, "SMTP", _FakeClient)
    _FakeClient.send_failures = [smtplib.SMTPServerDisconnected("closed")]

    async with SmtpEmailSender().session(_config()) as smtp:
        await smtp.send(to="x@example.com", subject="s", body="b")

    assert len(_FakeClient.instances) == 2
    assert len(_FakeClient.instances[1].messages) == 1


async def test_a_relay_that_keeps_hanging_up_surfaces_the_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _FakeClient)
    _FakeClient.send_failures = [
        smtplib.SMTPServerDisconnected("closed"),
        smtplib.SMTPServerDisconnected("closed again"),
    ]

    with pytest.raises(EmailSendError) as raised:
        async with SmtpEmailSender().session(_config()) as smtp:
            await smtp.send(to="x@example.com", subject="s", body="b")

    assert raised.value.permanent is False


# ---------- failure classification ----------


@pytest.mark.parametrize(
    ("failure", "permanent"),
    [
        (
            smtplib.SMTPRecipientsRefused({"x@example.com": (550, b"no such user")}),
            True,
        ),
        (
            smtplib.SMTPSenderRefused(550, b"sender rejected", "a2flow@example.com"),
            True,
        ),
        (smtplib.SMTPDataError(554, b"message rejected"), True),
        (smtplib.SMTPDataError(451, b"try again later"), False),
        (smtplib.SMTPAuthenticationError(535, b"bad credentials"), False),
        (smtplib.SMTPServerDisconnected("closed"), False),
        (smtplib.SMTPConnectError(421, b"unavailable"), False),
        (OSError("Connection refused"), False),
    ],
)
def test_only_hopeless_failures_are_classified_permanent(
    failure: Exception, permanent: bool
) -> None:
    """Bad credentials look like a 5xx but an admin can still fix them."""
    assert is_permanent_failure(failure) is permanent


async def test_the_permanence_verdict_reaches_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtplib, "SMTP", _FakeClient)
    _FakeClient.send_failures = [
        smtplib.SMTPRecipientsRefused({"x@example.com": (550, b"no such user")})
    ]

    with pytest.raises(EmailSendError) as raised:
        await SmtpEmailSender().send(
            _config(), to="x@example.com", subject="s", body="b"
        )

    assert raised.value.permanent is True
