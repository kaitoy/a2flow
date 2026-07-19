"""Authentication use-case service: login, session validation, and logout.

Sessions are server-side: a random opaque token is handed to the browser in a
cookie and only its hash is stored. Validity is governed by a sliding idle
timeout (``config.Settings.session_idle_timeout_seconds``, default 8 hours):
every successful :meth:`AuthService.authenticate` refreshes the session's
last-active time, and a session left idle past the window is revoked and
rejected.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from config import get_settings
from infrastructure.auth_tokens import generate_token, hash_token
from infrastructure.password import verify_password
from models.user import User
from repositories import AuthSessionRepository, TenantRepository, UserRepository
from repositories.exceptions import UnauthorizedError


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
    ) -> None:
        """Initialize the service.

        Args:
            users: Repository for user lookups and credential checks.
            sessions: Repository for login-session persistence.
            tenants: Repository used to resolve a submitted tenant slug at login.
        """
        self._users = users
        self._sessions = sessions
        self._tenants = tenants

    def _idle_timeout(self) -> timedelta:
        """Return the configured sliding idle timeout as a ``timedelta``."""
        seconds = get_settings().session_idle_timeout_seconds
        return timedelta(seconds=max(seconds, 1))

    async def login(
        self, username: str, password: str, *, tenant_slug: str | None = None
    ) -> LoginResult:
        """Verify credentials and create a new login session.

        The same generic :class:`UnauthorizedError` is raised for an unknown
        username, an unknown tenant slug, a wrong password, and a disabled or
        soft-deleted account, so the response never reveals which users or
        tenants exist.

        Args:
            username: The submitted username.
            password: The submitted plaintext password.
            tenant_slug: Slug of the tenant the user belongs to. Required to
                disambiguate a tenant-scoped user's username (unique only
                within its tenant); must be omitted for a platform-scoped
                user (``root``, or any other super_admin).

        Returns:
            A :class:`LoginResult` carrying the user and the freshly minted
            session and CSRF tokens.

        Raises:
            UnauthorizedError: If the credentials are invalid or the account
                cannot log in.
        """
        tenant_id: str | None = None
        if tenant_slug:
            tenant = await self._tenants.get_by_slug(tenant_slug)
            if tenant is None:
                raise UnauthorizedError("Invalid username or password")
            tenant_id = tenant.id
        user = await self._users.get_by_username(username, tenant_id=tenant_id)
        if (
            user is None
            or not user.enabled
            or user.deleted_at is not None
            or not verify_password(password, user.password)
        ):
            raise UnauthorizedError("Invalid username or password")

        session_token = generate_token()
        csrf_token = generate_token()
        await self._sessions.create(
            user_id=user.id,
            token_hash=hash_token(session_token),
            csrf_token=csrf_token,
        )
        return LoginResult(
            user=user, session_token=session_token, csrf_token=csrf_token
        )

    async def authenticate(self, session_token: str) -> User:
        """Resolve the user for a session token, sliding the idle timeout.

        Args:
            session_token: The raw token from the session cookie.

        Returns:
            The authenticated, still-enabled user.

        Raises:
            UnauthorizedError: If the session is missing, expired, or the
                backing user is gone or disabled. Expired sessions are deleted.
        """
        if not session_token:
            raise UnauthorizedError()
        token_hash = hash_token(session_token)
        session = await self._sessions.get_by_token_hash(token_hash)
        if session is None:
            raise UnauthorizedError()

        now = datetime.now(UTC)
        last_active = session.last_active_at
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=UTC)
        if now - last_active > self._idle_timeout():
            await self._sessions.delete_by_token_hash(token_hash)
            raise UnauthorizedError("Session expired")

        user = await self._users.get(session.user_id)
        if user is None or not user.enabled or user.deleted_at is not None:
            await self._sessions.delete_by_token_hash(token_hash)
            raise UnauthorizedError()

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
