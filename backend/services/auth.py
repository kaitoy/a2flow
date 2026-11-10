"""Authentication use-case service: login, session validation, and logout.

Sessions are server-side: a random opaque token is handed to the browser in a
cookie and only its hash is stored. Validity is governed by a sliding idle
timeout (``config.Settings.session_idle_timeout_seconds``, default 8 hours):
a successful :meth:`AuthService.authenticate` refreshes the session's
last-active time, and a session left idle past the window is revoked and
rejected. The refresh is written at most once per :data:`TOUCH_INTERVAL` (or
half the idle timeout, if that is shorter) rather than on every request, so
the frontend's polling does not turn every authenticated read into a write on
the primary; a session can therefore expire up to that much earlier than its
last request plus the idle timeout. A session whose browser never comes back
is not presented again, so every login also deletes the sessions already past
the window.

Failed logins are throttled per submitted account -- by the limit and lockout
time its tenant sets (``Tenant.login_max_failures`` /
``Tenant.login_lockout_minutes``, the ``models.tenant`` defaults for a
platform-scoped account or an unknown tenant). The counts live in the
``login_failures`` table, so every replica enforces the same limit.

Every bcrypt call runs in a worker thread: one costs hundreds of milliseconds
of CPU, and on the event loop it would stall every other request and stream
this process is serving.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from config import get_settings
from infrastructure.auth_tokens import generate_token, hash_token
from infrastructure.password import burn_password_check, verify_password
from models.tenant import (
    DEFAULT_LOGIN_LOCKOUT_MINUTES,
    DEFAULT_LOGIN_MAX_FAILURES,
    MAX_LOGIN_LOCKOUT_MINUTES,
    Tenant,
)
from models.user import User
from repositories.auth_session import AuthSessionRepository
from repositories.exceptions import TooManyLoginAttemptsError, UnauthorizedError
from repositories.login_failure import LoginFailureRepository
from repositories.tenant import TenantRepository
from repositories.user import UserRepository

#: The longest a session's stored ``last_active_at`` may lag behind its latest
#: request before :meth:`AuthService.authenticate` writes it again.
TOUCH_INTERVAL = timedelta(minutes=5)


@dataclass
class LoginResult:
    """Outcome of a successful login.

    Attributes:
        user: The authenticated user.
        session_token: The raw session token to set in the session cookie.
        csrf_token: The CSRF token to set in the readable double-submit cookie.
    """

    user: User
    session_token: str
    csrf_token: str


class AuthService:
    """Application service orchestrating authentication and session lifecycle."""

    def __init__(
        self,
        users: UserRepository,
        sessions: AuthSessionRepository,
        tenants: TenantRepository,
        login_failures: LoginFailureRepository,
    ) -> None:
        """Initialize the service.

        Args:
            users: Repository for user lookups and credential checks.
            sessions: Repository for login-session persistence.
            tenants: Repository used to resolve a submitted tenant name at login.
            login_failures: Repository counting recent failed logins for
                throttling.
        """
        self._users = users
        self._sessions = sessions
        self._tenants = tenants
        self._login_failures = login_failures

    def _idle_timeout(self) -> timedelta:
        """Return the configured sliding idle timeout as a ``timedelta``."""
        seconds = get_settings().session_idle_timeout_seconds
        return timedelta(seconds=max(seconds, 1))

    async def login(
        self,
        username: str,
        password: str,
        *,
        tenant_name: str | None = None,
    ) -> LoginResult:
        """Verify credentials and create a new login session.

        The same generic :class:`UnauthorizedError` is raised for an unknown
        username, an unknown or disabled tenant, a wrong password, and a
        disabled or soft-deleted account, so the response never reveals which
        users or tenants exist. Every one of those failures counts against the
        submitted account -- an unknown username included, so a lockout does
        not reveal existence either. A successful login clears the count.

        Args:
            username: The submitted username.
            password: The submitted plaintext password.
            tenant_name: Name (the URL-safe kebab-case identifier) of the
                tenant the user belongs to. Required to disambiguate a
                tenant-scoped user's username (unique only within its
                tenant); must be omitted for a platform-scoped user
                (``root``, or any other super_admin).

        Returns:
            A :class:`LoginResult` carrying the user and the freshly minted
            session and CSRF tokens.

        Raises:
            TooManyLoginAttemptsError: If the account is at its failure
                limit; raised before the password is checked.
            UnauthorizedError: If the credentials are invalid, the account
                cannot log in, or the submitted tenant is unknown or disabled.
        """
        tenant = await self._tenants.get_by_name(tenant_name) if tenant_name else None
        account_key = f"{tenant_name or ''}/{username}"
        # An unknown tenant gets the defaults, exactly like a known one that
        # never changed them, so the limit reveals nothing about existence.
        window = timedelta(
            minutes=tenant.login_lockout_minutes
            if tenant is not None
            else DEFAULT_LOGIN_LOCKOUT_MINUTES
        )
        limit = (
            tenant.login_max_failures
            if tenant is not None
            else DEFAULT_LOGIN_MAX_FAILURES
        )
        now = datetime.now(UTC)
        count, oldest = await self._login_failures.recent(account_key, now - window)
        if count >= limit and oldest is not None:
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=UTC)
            retry_after = (oldest + window - now).total_seconds()
            raise TooManyLoginAttemptsError(int(retry_after) + 1)
        try:
            user = await self._verify_credentials(
                username, password, tenant_name, tenant
            )
        except UnauthorizedError:
            await self._login_failures.record(
                account_key, now, now - timedelta(minutes=MAX_LOGIN_LOCKOUT_MINUTES)
            )
            raise
        await self._login_failures.clear(account_key)
        return await self.start_session(user)

    async def start_session(self, user: User) -> LoginResult:
        """Mint a login session for a user who has already been authenticated.

        Shared by password login and OIDC single sign-on, so both hand out
        identical sessions. Also deletes sessions already past the idle window.

        Args:
            user: The user to sign in; the caller has checked they may.

        Returns:
            A :class:`LoginResult` carrying the user and the freshly minted
            session and CSRF tokens.
        """
        session_token = generate_token()
        csrf_token = generate_token()
        await self._sessions.create(
            user_id=user.id,
            token_hash=hash_token(session_token),
            csrf_token=csrf_token,
            prune_before=datetime.now(UTC) - self._idle_timeout(),
        )
        return LoginResult(
            user=user, session_token=session_token, csrf_token=csrf_token
        )

    async def _verify_credentials(
        self,
        username: str,
        password: str,
        tenant_name: str | None,
        tenant: Tenant | None,
    ) -> User:
        """Return the user the credentials identify, if they may log in.

        Args:
            username: The submitted username.
            password: The submitted plaintext password.
            tenant_name: The submitted tenant name, if any.
            tenant: The tenant ``tenant_name`` resolved to, or ``None``.

        Returns:
            The enabled, non-deleted user whose password matches.

        Raises:
            UnauthorizedError: For every reason the login is refused.
        """
        tenant_id: str | None = None
        if tenant_name:
            if tenant is None or not tenant.enabled:
                await asyncio.to_thread(burn_password_check, password)
                raise UnauthorizedError("Invalid username or password")
            tenant_id = tenant.id
        user = await self._users.get_by_username(username, tenant_id=tenant_id)
        if user is None or not user.enabled or user.deleted_at is not None:
            # Pay the same bcrypt cost as a wrong password, so timing does
            # not reveal which accounts exist.
            await asyncio.to_thread(burn_password_check, password)
            raise UnauthorizedError("Invalid username or password")
        if user.password is None:
            # An SSO-only account has no hash to check; pay the bcrypt cost
            # anyway so its existence is not revealed by timing.
            await asyncio.to_thread(burn_password_check, password)
            raise UnauthorizedError("Invalid username or password")
        if not await asyncio.to_thread(verify_password, password, user.password):
            raise UnauthorizedError("Invalid username or password")
        return user

    async def authenticate(self, session_token: str) -> User:
        """Resolve the user for a session token, sliding the idle timeout.

        The session, its user, and the user's tenant flag come from one query,
        and the session's last-active time is written only once it is older
        than :data:`TOUCH_INTERVAL` (or half the idle timeout, if shorter), so
        a typical request costs a single SELECT.

        Args:
            session_token: The raw token from the session cookie.

        Returns:
            The authenticated, still-enabled user, whose tenant (if any) is
            still enabled.

        Raises:
            UnauthorizedError: If the session is missing, expired, the
                backing user is gone or disabled, or a tenant-scoped user's
                tenant has been disabled. Expired and rejected sessions are
                deleted.
        """
        if not session_token:
            raise UnauthorizedError()
        token_hash = hash_token(session_token)
        found = await self._sessions.get_with_user(token_hash)
        if found is None:
            raise UnauthorizedError()
        session, user, tenant_enabled = found

        now = datetime.now(UTC)
        last_active = session.last_active_at
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=UTC)
        if now - last_active > self._idle_timeout():
            await self._sessions.delete_by_token_hash(token_hash)
            raise UnauthorizedError("Session expired")

        if (
            not user.enabled
            or user.deleted_at is not None
            or (user.tenant_id is not None and not tenant_enabled)
        ):
            await self._sessions.delete_by_token_hash(token_hash)
            raise UnauthorizedError()

        if now - last_active > min(TOUCH_INTERVAL, self._idle_timeout() / 2):
            await self._sessions.touch(session, now)
        return user

    async def get_csrf_token(self, session_token: str) -> str | None:
        """Return the CSRF token bound to a session token, if the session exists.

        Args:
            session_token: The raw token from the session cookie.

        Returns:
            The session's CSRF token, or ``None`` if no session matches.
        """
        if not session_token:
            return None
        session = await self._sessions.get_by_token_hash(hash_token(session_token))
        return session.csrf_token if session is not None else None

    async def logout(self, session_token: str) -> None:
        """Revoke the session identified by the given token, if any.

        Args:
            session_token: The raw token from the session cookie.
        """
        if session_token:
            await self._sessions.delete_by_token_hash(hash_token(session_token))
