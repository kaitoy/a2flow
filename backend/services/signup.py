"""Self-service sign-up: a visitor creates a tenant of their own and becomes its admin.

Sign-up takes two steps, so an account is only ever made for an address its
owner controls:

1. :meth:`SignupService.request` stores the submitted form as a
   :class:`~models.pending_signup.PendingSignup` and mails a confirmation link
   to the address. Nothing else is created.
2. :meth:`SignupService.complete`, reached from the page that link opens,
   turns the pending row into a tenant and its admin user, deletes the row,
   and signs the admin in.

Sign-up is offered only while ``config.Settings.signup_enabled``
(``SIGNUP_ENABLED``) is set, ``APP_BASE_URL`` is set (the link is built from
it), and email delivery is configured in System Settings. The link carries the
token in its fragment (``/signup/verify#<token>``), which browsers never send
to a server, so it stays out of access logs and ``Referer`` headers.

The mail goes out directly through the SMTP relay, not through the outbound
email queue: queued messages belong to a tenant, and there is none yet. The
endpoint is unauthenticated, so one address gets at most one confirmation per
:data:`RESEND_INTERVAL`, which keeps the form from being used to flood someone
else's inbox.

The tenant's name -- also its subdomain -- is derived from the chosen username
plus a random suffix, so the visitor never has to pick a globally unique one.
The tenant and its admin user are written in one transaction rather than
through ``SqlTenantRepository``/``SqlUserRepository``, which each commit on
their own: a failure between the two would otherwise leave a tenant nobody can
sign in to. Both rows are stamped with the system user as creator, like the
tenant and admin seeded at startup (``infrastructure/bootstrap.py``).
"""

import asyncio
import re
import secrets
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, EmailStr
from pydantic.alias_generators import to_camel
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.auth_tokens import generate_token, hash_token
from infrastructure.email_sender import SmtpConfig, SmtpEmailSender
from infrastructure.password import hash_password
from models.constraints import Password, PersonName, Username
from models.pending_signup import PendingSignup
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID, Role, User
from repositories.exceptions import (
    ForbiddenError,
    InvalidSignupLinkError,
    TooManySignupRequestsError,
)
from services.auth import AuthService, LoginResult
from services.system_settings import SystemSettingsService

#: How long a confirmation link stays usable.
CONFIRMATION_TTL = timedelta(hours=24)
#: The least time between two confirmation emails to the same address.
RESEND_INTERVAL = timedelta(minutes=1)
#: Tenant names tried before giving up; a collision needs the same username
#: base and the same 24-bit random suffix, so a second try practically never
#: happens.
_NAME_ATTEMPTS = 3

_SUBJECT = "Confirm your A2Flow sign-up"
_BODY = """\
Someone, hopefully you, asked to create an A2Flow account with this address.

To finish signing up, open this link within 24 hours and choose
"Complete sign-up":

{link}

If you did not ask for this, ignore this email. Nothing is created until the
link is used.
"""


class SignupRequest(BaseModel):
    """What a visitor enters on the sign-up page."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    email: EmailStr
    username: Username
    first_name: PersonName
    last_name: PersonName
    password: Password


class SignupCompletion(BaseModel):
    """The token from a sign-up confirmation link."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    token: str


def tenant_name_for(username: str) -> str:
    """Derive a fresh tenant name (a ``TenantSlug``) from a username.

    The username is lowercased and every run of characters outside
    ``[a-z0-9]`` becomes one hyphen, then a random six-hex-digit suffix is
    appended, e.g. ``John.Doe`` → ``john-doe-3fa9c1``.

    Args:
        username: The username the visitor chose.

    Returns:
        A kebab-case name of at most 57 characters.
    """
    base = re.sub(r"[^a-z0-9]+", "-", username.lower()).strip("-")[:50].strip("-")
    return f"{base or 'tenant'}-{secrets.token_hex(3)}"


class SignupService:
    """Mails sign-up confirmations and turns confirmed ones into a tenant and its admin."""

    def __init__(
        self,
        session: AsyncSession,
        auth: AuthService,
        system_settings: SystemSettingsService,
        sender: SmtpEmailSender,
    ) -> None:
        """Initialize the service.

        Args:
            session: The request's database session, written to directly so
                each step commits as one transaction.
            auth: Mints the new admin's login session.
            system_settings: Resolves the SMTP relay the confirmation is
                sent through.
            sender: Sends the confirmation email.
        """
        self._session = session
        self._auth = auth
        self._system_settings = system_settings
        self._sender = sender

    async def _smtp(self) -> SmtpConfig | None:
        """Return the relay to mail confirmations through, or ``None`` if sign-up is off.

        ``None`` while ``SIGNUP_ENABLED`` or ``APP_BASE_URL`` is unset, or email
        delivery is not configured.
        """
        settings = get_settings()
        if not settings.signup_enabled or settings.app_base_url is None:
            return None
        return await self._system_settings.resolve_smtp()

    async def available(self) -> bool:
        """Return whether visitors can sign up on this deployment."""
        return await self._smtp() is not None

    async def request(self, data: SignupRequest) -> None:
        """Store a sign-up form and mail its confirmation link.

        Args:
            data: The visitor's sign-up form.

        Raises:
            ForbiddenError: If sign-up is not available (see :meth:`available`).
            TooManySignupRequestsError: If a confirmation went to this address
                within :data:`RESEND_INTERVAL`.
            EmailSendError: If the relay rejected the message or could not be
                reached; nothing is stored then.
        """
        config = await self._smtp()
        if config is None:
            raise ForbiddenError("Sign-up is disabled")
        now = datetime.now(UTC)
        # ponytail: check-then-insert, so two requests racing within a few
        # milliseconds can both pass; the throttle is against flooding, not exact.
        recent = select(PendingSignup.id).where(
            col(PendingSignup.email) == data.email,
            col(PendingSignup.created_at) > now - RESEND_INTERVAL,
        )
        if (await self._session.exec(recent.limit(1))).first() is not None:
            raise TooManySignupRequestsError()
        await self._session.exec(
            delete(PendingSignup).where(col(PendingSignup.expires_at) <= now)
        )
        token = generate_token()
        self._session.add(
            PendingSignup(
                email=data.email,
                username=data.username,
                first_name=data.first_name,
                last_name=data.last_name,
                password=await asyncio.to_thread(hash_password, data.password),
                token_hash=hash_token(token),
                created_at=now,
                expires_at=now + CONFIRMATION_TTL,
            )
        )
        link = f"{get_settings().app_base_url}/signup/verify#{token}"
        await self._sender.send(
            config, to=data.email, subject=_SUBJECT, body=_BODY.format(link=link)
        )
        # Committed only once the mail is out: a failed send leaves no row
        # behind to block a retry through the throttle.
        await self._session.commit()

    async def complete(self, token: str) -> tuple[LoginResult, Tenant]:
        """Create the tenant and admin a confirmation link stands for, and sign the admin in.

        Args:
            token: The token from the confirmation link.

        Returns:
            The new admin's login result and the new tenant.

        Raises:
            ForbiddenError: If ``SIGNUP_ENABLED`` has been turned off since.
            InvalidSignupLinkError: If the token is unknown, already used, or
                expired.
            IntegrityError: If every generated tenant name was taken.
        """
        if not get_settings().signup_enabled:
            raise ForbiddenError("Sign-up is disabled")
        stmt = select(PendingSignup).where(
            col(PendingSignup.token_hash) == hash_token(token),
            col(PendingSignup.expires_at) > datetime.now(UTC),
        )
        pending = (await self._session.exec(stmt)).first()
        if pending is None:
            raise InvalidSignupLinkError()
        # Copied out up front: a rollback below expires the loaded row.
        pending_id, username = pending.id, pending.username
        first_name, last_name = pending.first_name, pending.last_name
        password, email = pending.password, pending.email
        for attempt in range(_NAME_ATTEMPTS):
            name = tenant_name_for(username)
            tenant = Tenant(
                display_name=name,
                name=name,
                enabled=True,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
            user = User(
                username=username,
                first_name=first_name,
                last_name=last_name,
                password=password,
                email=email,
                enabled=True,
                email_verified=True,
                roles=[Role.admin.value],
                tenant_id=tenant.id,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
            try:
                self._session.add(tenant)
                # Flushed first so the tenants row exists when the users row's
                # foreign key to it is checked.
                await self._session.flush()
                self._session.add(user)
                await self._session.exec(
                    delete(PendingSignup).where(col(PendingSignup.id) == pending_id)
                )
                await self._session.commit()
            except IntegrityError:
                # The only unique values here are the tenant's name and
                # display name: the user is the first one in a new tenant.
                await self._session.rollback()
                if attempt == _NAME_ATTEMPTS - 1:
                    raise
                continue
            return await self._auth.start_session(user), tenant
        raise AssertionError("unreachable")
