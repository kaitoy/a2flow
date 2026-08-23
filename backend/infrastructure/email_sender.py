"""SMTP adapter for outgoing notification email.

An infrastructure adapter in the same sense as :mod:`infrastructure.mcp_client`
and :mod:`infrastructure.vault_client`: it talks to an external system and
holds no business rules. Who receives a message, and whether one should be sent
at all, is decided a layer up in
:mod:`services.notification_dispatch`; when to send it, and what to do when a
send fails, in :mod:`services.email_queue_worker`.

Deliberately built on the standard library's :mod:`smtplib` rather than an
async SMTP package. ``smtplib`` is blocking, so every call is pushed onto a
worker thread with :func:`asyncio.to_thread`; that keeps the event loop free
without adding a dependency.

**Connections are reusable.** :meth:`SmtpEmailSender.session` opens one
conversation and lets a caller push a whole batch of messages through it, which
is what makes draining a queue cheap: the TCP handshake, the TLS negotiation and
the AUTH exchange happen once instead of once per message. :meth:`SmtpEmailSender
.send` is the one-shot form, for the settings page's test send.

A session is **not** safe to use from two tasks at once — one ``smtplib.SMTP``
object is shared across successive :func:`asyncio.to_thread` calls, which is
only sound because those calls are awaited one after another. The queue worker
sends strictly sequentially for exactly this reason.
"""

import asyncio
import logging
import smtplib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
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


def is_permanent_failure(exc: Exception) -> bool:
    """Return whether retrying this failure could never succeed.

    The distinction is what keeps the queue honest: a relay that is down, or
    rejecting with a 4xx, deserves another attempt; a recipient the relay refuses
    outright does not, and retrying it for hours only delays the dead letter.

    ``SMTPAuthenticationError`` is deliberately **not** permanent even though it
    carries a 5xx code. Bad credentials are a configuration mistake an admin can
    correct, and the message is still perfectly deliverable once they do.

    Args:
        exc: The exception raised while talking to the relay.

    Returns:
        ``True`` when the message should be written off rather than retried.
    """
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return False
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return True
    if isinstance(exc, smtplib.SMTPResponseException):
        return exc.smtp_code >= 500
    return False


def _open_blocking(config: SmtpConfig) -> smtplib.SMTP:
    """Open, secure, and authenticate a connection to the relay.

    Runs on a worker thread; see the module docstring.

    Args:
        config: The resolved SMTP configuration.

    Returns:
        The connected client, ready to send.
    """
    client: smtplib.SMTP
    if config.security is SmtpSecurity.ssl:
        client = smtplib.SMTP_SSL(config.host, config.port, timeout=config.timeout)
    else:
        client = smtplib.SMTP(config.host, config.port, timeout=config.timeout)
    try:
        if config.security is SmtpSecurity.starttls:
            client.starttls()
            # STARTTLS resets the session, so the relay's capability list has to
            # be re-read before AUTH is attempted on the upgraded connection.
            client.ehlo()
        if config.username:
            client.login(config.username, config.password or "")
    except Exception:
        client.close()
        raise
    return client


class SmtpSession:
    """One open SMTP conversation that a batch of messages can be pushed through.

    Obtained from :meth:`SmtpEmailSender.session`, which also closes it. See the
    module docstring for the single-task constraint.
    """

    def __init__(self, config: SmtpConfig) -> None:
        """Store the configuration this session will connect with.

        The connection itself is opened lazily on the first send, so entering a
        session costs nothing when the batch turns out to be empty.

        Args:
            config: The resolved SMTP configuration.
        """
        self._config = config
        self._client: smtplib.SMTP | None = None

    async def send(self, *, to: str, subject: str, body: str) -> None:
        """Send one message, translating every transport failure into one error.

        A relay that dropped an idle connection is reconnected to and the message
        retried once, in-line: that is a bookkeeping detail of connection reuse,
        not a delivery failure the queue should have to schedule around.

        Args:
            to: Recipient address.
            subject: Message subject line.
            body: Plain-text message body.

        Raises:
            EmailSendError: If the relay could not be reached, rejected the
                credentials, or refused the message. ``permanent`` says whether
                another attempt could ever help. The underlying reason is logged
                here and carried on the exception for the HTTP layer to log —
                never to return to a client.
        """
        message = build_message(self._config, to=to, subject=subject, body=body)
        try:
            try:
                await self._send_once(message)
            except smtplib.SMTPServerDisconnected:
                await self.aclose()
                await self._send_once(message)
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning(
                "SMTP delivery to %s via %s:%s failed: %s",
                to,
                self._config.host,
                self._config.port,
                exc,
            )
            raise EmailSendError(str(exc), permanent=is_permanent_failure(exc)) from exc

    async def _send_once(self, message: EmailMessage) -> None:
        """Hand one message to the relay, opening the connection if needed."""
        if self._client is None:
            self._client = await asyncio.to_thread(_open_blocking, self._config)
        client = self._client
        await asyncio.to_thread(client.send_message, message)

    async def aclose(self) -> None:
        """Close the connection, ignoring a relay that has already hung up."""
        client, self._client = self._client, None
        if client is None:
            return
        try:
            await asyncio.to_thread(client.quit)
        except (smtplib.SMTPException, OSError):
            # QUIT is a courtesy. A relay that dropped the connection first has
            # nothing left to tell us, and the socket is closed either way.
            await asyncio.to_thread(client.close)


class SmtpEmailSender:
    """Sends plain-text email through a configured SMTP relay."""

    @asynccontextmanager
    async def session(self, config: SmtpConfig) -> AsyncIterator[SmtpSession]:
        """Open a reusable conversation with the relay for the body's duration.

        Args:
            config: The resolved SMTP configuration.

        Yields:
            The session to push messages through.
        """
        smtp = SmtpSession(config)
        try:
            yield smtp
        finally:
            await smtp.aclose()

    async def send(
        self, config: SmtpConfig, *, to: str, subject: str, body: str
    ) -> None:
        """Send exactly one message, opening and closing a connection for it.

        Args:
            config: The resolved SMTP configuration.
            to: Recipient address.
            subject: Message subject line.
            body: Plain-text message body.

        Raises:
            EmailSendError: See :meth:`SmtpSession.send`.
        """
        async with self.session(config) as smtp:
            await smtp.send(to=to, subject=subject, body=body)


@lru_cache(maxsize=1)
def get_email_sender() -> SmtpEmailSender:
    """Return the process-wide SmtpEmailSender singleton.

    The sender holds no per-connection state — every call takes its
    :class:`SmtpConfig` as an argument — so one instance serves every caller.
    """
    return SmtpEmailSender()
