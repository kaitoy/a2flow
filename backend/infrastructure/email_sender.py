"""SMTP adapter for outgoing notification email.

An infrastructure adapter in the same sense as :mod:`infrastructure.mcp_client`
and :mod:`infrastructure.vault_client`: it talks to an external system and
holds no business rules. Who receives a message, and whether one should be sent
at all, is decided a layer up in
:mod:`services.notification_dispatch`.

Deliberately built on the standard library's :mod:`smtplib` rather than an
async SMTP package. ``smtplib`` is blocking, so every call is pushed onto a
worker thread with :func:`asyncio.to_thread`; that keeps the event loop free
without adding a dependency for the handful of messages a notification
generates. A deployment that grows into high-volume mail should reach for a
queue before it reaches for a different client library.
"""

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from functools import lru_cache

from models.system_settings import SmtpSecurity
from repositories.exceptions import EmailSendError

logger = logging.getLogger(__name__)

#: Per-operation socket timeout, in seconds, applied to the whole SMTP
#: conversation. Bounds how long a hung relay can keep a worker thread — and,
#: for the test-send endpoint, an HTTP request — waiting.
DEFAULT_SMTP_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class SmtpConfig:
    """A fully resolved SMTP connection, ready to send with.

    Built by :meth:`services.system_settings.SystemSettingsService.resolve_smtp`
    from the stored settings row, with ``password`` already decrypted. Frozen so
    a resolved configuration cannot be mutated while a send is in flight on
    another task.

    Attributes:
        host: Hostname or IP literal of the relay.
        port: TCP port to connect to.
        security: How the connection is secured.
        username: SMTP AUTH username, or ``None`` for an unauthenticated relay.
        password: SMTP AUTH password, or ``None`` when ``username`` is unset.
        from_email: Envelope and header sender address.
        from_name: Optional display name paired with ``from_email``.
        timeout: Socket timeout in seconds.
    """

    host: str
    port: int
    security: SmtpSecurity
    username: str | None
    password: str | None
    from_email: str
    from_name: str | None
    timeout: float = DEFAULT_SMTP_TIMEOUT_SECONDS


def build_message(
    config: SmtpConfig, *, to: str, subject: str, body: str
) -> EmailMessage:
    """Build the plain-text message to hand to the relay.

    Args:
        config: The resolved SMTP configuration supplying the sender.
        to: Recipient address.
        subject: Message subject line.
        body: Plain-text message body.

    Returns:
        The assembled message.
    """
    message = EmailMessage()
    message["From"] = (
        formataddr((config.from_name, config.from_email))
        if config.from_name
        else config.from_email
    )
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    return message


def _send_blocking(config: SmtpConfig, message: EmailMessage) -> None:
    """Open a connection, authenticate if configured, and send one message.

    Runs on a worker thread; see the module docstring.

    Args:
        config: The resolved SMTP configuration.
        message: The message to send.
    """
    client: smtplib.SMTP
    if config.security is SmtpSecurity.ssl:
        client = smtplib.SMTP_SSL(config.host, config.port, timeout=config.timeout)
    else:
        client = smtplib.SMTP(config.host, config.port, timeout=config.timeout)
    with client:
        if config.security is SmtpSecurity.starttls:
            client.starttls()
            # STARTTLS resets the session, so the relay's capability list has to
            # be re-read before AUTH is attempted on the upgraded connection.
            client.ehlo()
        if config.username:
            client.login(config.username, config.password or "")
        client.send_message(message)


class SmtpEmailSender:
    """Sends plain-text email through a configured SMTP relay."""

    async def send(
        self, config: SmtpConfig, *, to: str, subject: str, body: str
    ) -> None:
        """Send one message, translating every transport failure into one error.

        Args:
            config: The resolved SMTP configuration.
            to: Recipient address.
            subject: Message subject line.
            body: Plain-text message body.

        Raises:
            EmailSendError: If the relay could not be reached, rejected the
                credentials, or refused the message. The underlying reason is
                logged here and carried on the exception for the HTTP layer to
                log — never to return to a client.
        """
        message = build_message(config, to=to, subject=subject, body=body)
        try:
            await asyncio.to_thread(_send_blocking, config, message)
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning(
                "SMTP delivery to %s via %s:%s failed: %s",
                to,
                config.host,
                config.port,
                exc,
            )
            raise EmailSendError(str(exc)) from exc


@lru_cache(maxsize=1)
def get_email_sender() -> SmtpEmailSender:
    """Return the process-wide SmtpEmailSender singleton.

    The sender holds no per-connection state — every call takes its
    :class:`SmtpConfig` as an argument — so one instance serves every caller.
    """
    return SmtpEmailSender()
