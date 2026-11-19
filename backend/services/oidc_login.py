"""OIDC single sign-on use cases: start the code flow, and complete it.

:meth:`OidcLoginService.start` builds the identity provider's authorization URL
plus an encrypted, short-lived state cookie carrying the tenant id, ``state``,
``nonce`` and PKCE verifier (no database row). :meth:`OidcLoginService.complete`
checks that cookie against the callback, exchanges the code, validates the ID
token, then resolves the user (by ``sub``, else a trusted e-mail link, else
creation), syncs IdP-mapped group membership and mints the session exactly as
password login does.

Every refusal is a :class:`SsoLoginError` with one of four public codes; the
reason goes to the server log at ``warning`` only. Every refusal is decided
before the first write, so none leaves a half-provisioned user behind. That
includes an e-mail that is not a usable address (the admin UI could never save
such a user) and a new account whose e-mail an existing account already has.
``start`` answers ``unavailable`` for every reason SSO cannot begin, so it never
reveals whether a tenant exists. :meth:`OidcLoginService.sso_enabled`, behind a
tenant subdomain's login page, reveals only which tenants have SSO switched on.
"""

import json
import logging
import re
import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import EmailStr, TypeAdapter, ValidationError

from config import get_settings
from infrastructure.oidc_client import (
    OidcClient,
    OidcError,
    OidcProviderMetadata,
    make_pkce_pair,
)
from infrastructure.secret_cipher import SecretCipher, data_key_cipher
from infrastructure.secret_resolver import SecretResolver
from models.tenant import Tenant, oidc_redirect_uri
from models.user import User
from repositories.exceptions import SecretResolutionError, UniqueViolationError
from repositories.tenant import TenantRepository
from repositories.user import UserRepository
from repositories.user_group import UserGroupRepository
from services.auth import AuthService, LoginResult

logger = logging.getLogger(__name__)

#: Name of the cookie carrying the encrypted sign-in state between the redirects.
STATE_COOKIE_NAME = "a2flow_oidc_state"
#: How long a started sign-in stays valid, in seconds (cookie and Fernet ``ttl``).
STATE_TTL_SECONDS = 600

_USERNAME_DROP = re.compile(r"[^a-zA-Z0-9._-]")
_USERNAME_MAX = 64
_NAME_MAX = 100
_SUBJECT_MAX = 255
_EMAIL: TypeAdapter[str] = TypeAdapter(EmailStr)


class SsoErrorCode(StrEnum):
    """Public reason a sign-in was refused, shown to the user as a toast."""

    unavailable = "unavailable"
    failed = "failed"
    account_disabled = "account_disabled"
    not_permitted = "not_permitted"


class SsoLoginError(Exception):
    """A sign-in was refused.

    Attributes:
        code: The public reason; the message is for the server log only.
    """

    def __init__(self, code: SsoErrorCode, message: str) -> None:
        """Create the error.

        Args:
            code: The public reason.
            message: Log-only detail.
        """
        super().__init__(message)
        self.code = code


def safe_next_path(value: str | None) -> str:
    """Return ``value`` if it is a path on this site, else ``/``.

    Where a sign-in returns to comes from the browser, so only a path that
    stays on the current origin passes: it must start with one ``/`` and hold
    no backslash or control character, which rules out ``//evil.example`` and
    ``/\evil.example`` (both read by browsers as another host).

    Args:
        value: The path the sign-in was asked to return to.
    """
    if (
        not value
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or any(ord(c) < 0x20 or ord(c) == 0x7F for c in value)
    ):
        return "/"
    return value


@dataclass
class SsoLoginResult(LoginResult):
    """A finished SSO sign-in: the session, plus where the browser goes next.

    Attributes:
        next_path: The page the sign-in started from (see :func:`safe_next_path`).
    """

    next_path: str = "/"


@dataclass(frozen=True)
class SsoStart:
    """Where to send the browser, and the state cookie to set on the way.

    Attributes:
        authorization_url: The identity provider's authorization URL.
        state_cookie: Encrypted sign-in state for :data:`STATE_COOKIE_NAME`.
    """

    authorization_url: str
    state_cookie: str


def normalize_username(candidates: Sequence[str | None]) -> str:
    """Return a username built from the first usable candidate.

    Each candidate is stripped of characters outside ``[a-zA-Z0-9._-]`` and
    truncated to 64 characters; the first with at least 3 characters left wins.

    Args:
        candidates: Raw values in order of preference (``None`` is skipped).

    Returns:
        The normalised username, or ``"user"`` when no candidate qualifies.
    """
    for candidate in candidates:
        name = _USERNAME_DROP.sub("", candidate or "")[:_USERNAME_MAX]
        if len(name) >= 3:
            return name
    return "user"


def _text(value: Any) -> str:
    """Return ``value`` stripped when it is a string, else ``""``."""
    return value.strip() if isinstance(value, str) else ""


def _groups(value: Any) -> list[str]:
    """Read a groups claim: a string is one group, a non-list is none."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [g for g in value if isinstance(g, str)]
    return []


def _is_overage(claims: dict[str, Any], groups_claim: str) -> bool:
    """Return whether the IdP moved the groups claim out of the token (Entra)."""
    names = claims.get("_claim_names")
    return isinstance(names, dict) and groups_claim in names


class OidcLoginService:
    """Runs a tenant's OpenID Connect sign-in from redirect to session."""

    def __init__(
        self,
        *,
        tenants: TenantRepository,
        users: UserRepository,
        auth: AuthService,
        oidc: OidcClient,
        cipher: SecretCipher,
        groups_for_tenant: Callable[[str], UserGroupRepository],
        secrets_for_tenant: Callable[[str], SecretResolver],
    ) -> None:
        """Initialize the service.

        Args:
            tenants: Resolves the tenant by name or id.
            users: Finds, links and creates users.
            auth: Mints the session.
            oidc: Talks to the identity provider.
            cipher: The master cipher, which encrypts the state cookie. A
                tenant's stored client secret is decrypted with its data key.
            groups_for_tenant: Builds an unrestricted user-group repository
                scoped to the given tenant id.
            secrets_for_tenant: Builds the resolver of the given tenant's
                secrets, for a client secret the tenant references from one.
        """
        self._tenants = tenants
        self._users = users
        self._auth = auth
        self._oidc = oidc
        self._cipher = cipher
        self._groups_for_tenant = groups_for_tenant
        self._secrets_for_tenant = secrets_for_tenant

    async def sso_enabled(self, tenant_name: str) -> bool:
        """Return whether the tenant named ``tenant_name`` offers SSO sign-in.

        Backs the login page of a tenant subdomain, which sends the visitor
        straight to the identity provider when this is ``True``. It reveals
        only what that redirect reveals anyway: an unknown tenant, a disabled
        one, and one without a complete SSO configuration all read ``False``.

        Args:
            tenant_name: The tenant named by the subdomain.
        """
        tenant = await self._tenants.get_by_name(tenant_name)
        return tenant is not None and tenant.enabled and _sso_configured(tenant)

    async def start(
        self, tenant_name: str, *, on_subdomain: bool = False, next_path: str = "/"
    ) -> SsoStart:
        """Begin a sign-in for the tenant named ``tenant_name``.

        The identity provider is told to return to the address the sign-in
        started at -- the deployment's ``APP_BASE_URL``, or the tenant's own
        subdomain of it (:meth:`config.Settings.tenant_origin`) -- so the
        session cookie lands where the user is. That redirect URI rides in the
        state cookie for :meth:`complete` to repeat.

        Args:
            tenant_name: The tenant the user typed on the login screen, or the
                one its subdomain names.
            on_subdomain: Whether the sign-in started on the tenant's subdomain.
            next_path: The page to return to once signed in; anything that is
                not a path on this site becomes ``/``.

        Returns:
            The authorization URL and the encrypted state cookie.

        Raises:
            SsoLoginError: ``unavailable`` for an unknown or disabled tenant,
                SSO off or incompletely configured, ``app_base_url`` unset, or
                a discovery failure -- indistinguishable on purpose.
        """
        tenant = await self._tenants.get_by_name(tenant_name)
        if tenant is None or not tenant.enabled:
            raise _refuse(
                SsoErrorCode.unavailable,
                tenant.id if tenant else None,
                "unknown or disabled tenant",
            )
        meta = await self._provider(tenant)
        settings = get_settings()
        redirect_uri = oidc_redirect_uri(
            settings.tenant_origin(tenant.name)
            if on_subdomain
            else settings.app_base_url
        )
        if redirect_uri is None:
            raise _refuse(SsoErrorCode.unavailable, tenant.id, "no sign-in origin")
        state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        verifier, challenge = make_pkce_pair()
        cookie = self._cipher.encrypt(
            json.dumps(
                {
                    "t": tenant.id,
                    "s": state,
                    "n": nonce,
                    "v": verifier,
                    "r": redirect_uri,
                    "x": safe_next_path(next_path),
                }
            )
        )
        url = self._oidc.authorization_url(
            meta,
            client_id=tenant.oidc_client_id or "",
            redirect_uri=redirect_uri,
            state=state,
            nonce=nonce,
            code_challenge=challenge,
        )
        return SsoStart(authorization_url=url, state_cookie=cookie)

    async def _provider(self, tenant: Tenant) -> OidcProviderMetadata:
        """Return the tenant's provider metadata.

        Raises:
            SsoLoginError: ``unavailable`` if SSO is off or incomplete, or
                discovery fails.
        """
        issuer = tenant.oidc_issuer
        if not (_sso_configured(tenant) and issuer):
            raise _refuse(SsoErrorCode.unavailable, tenant.id, "SSO off or incomplete")
        try:
            return await self._oidc.metadata(issuer)
        except OidcError as exc:
            raise _refuse(SsoErrorCode.unavailable, tenant.id, str(exc)) from exc

    def next_path_of(self, state_cookie: str | None) -> str:
        """Return the page a sign-in was to return to, read from its state cookie.

        For a callback that failed: the login page it lands on keeps that page,
        so signing in again still ends there. The cookie's age is not checked --
        it only picks a path on this site -- and anything unreadable gives ``/``.

        Args:
            state_cookie: The cookie :meth:`start` set, if the browser sent it.
        """
        if not state_cookie:
            return "/"
        try:
            payload = json.loads(self._cipher.decrypt(state_cookie))
        except ValueError:
            return "/"
        return safe_next_path(payload.get("x") if isinstance(payload, dict) else None)

    async def complete(
        self,
        *,
        state_cookie: str | None,
        state: str | None,
        code: str | None,
        error: str | None,
    ) -> SsoLoginResult:
        """Finish a sign-in from the identity provider's callback.

        Args:
            state_cookie: The cookie :meth:`start` set.
            state: The callback's ``state`` parameter.
            code: The callback's ``code`` parameter.
            error: The callback's ``error`` parameter (the IdP refused).

        Returns:
            The session, minted as password login does, and the page
            :meth:`start` was asked to return to.

        Raises:
            SsoLoginError: With the public reason; see the module docstring.
        """
        if error is not None:
            raise _refuse(SsoErrorCode.failed, None, "identity provider error")
        if not state_cookie or not state or not code:
            raise _refuse(SsoErrorCode.failed, None, "missing callback input")
        try:
            payload = json.loads(
                self._cipher.decrypt(state_cookie, ttl=STATE_TTL_SECONDS)
            )
        except ValueError as exc:
            raise _refuse(SsoErrorCode.failed, None, "bad or expired state") from exc
        if not isinstance(payload, dict) or not all(
            isinstance(payload.get(k), str) for k in ("t", "s", "n", "v", "r")
        ):
            raise _refuse(SsoErrorCode.failed, None, "malformed state")
        if not secrets.compare_digest(state.encode(), payload["s"].encode()):
            raise _refuse(SsoErrorCode.failed, None, "state mismatch")

        tenant = await self._tenants.get(payload["t"])
        if tenant is None:
            raise _refuse(SsoErrorCode.failed, payload["t"], "tenant gone")
        if not tenant.enabled:
            raise _refuse(SsoErrorCode.account_disabled, tenant.id, "tenant disabled")
        meta = await self._provider(tenant)
        claims = await self._claims(tenant, meta, payload["r"], code, payload)
        result = await self._resolve(tenant, claims)
        return SsoLoginResult(
            user=result.user,
            session_token=result.session_token,
            csrf_token=result.csrf_token,
            next_path=safe_next_path(payload.get("x")),
        )

    async def _claims(
        self,
        tenant: Tenant,
        meta: OidcProviderMetadata,
        redirect_uri: str,
        code: str,
        payload: dict[str, str],
    ) -> dict[str, Any]:
        """Exchange the code and return the validated claims.

        Userinfo is consulted only when the ID token lacks the e-mail or the
        groups claim (with no overage marker); its ``sub`` must equal the ID
        token's, and the ID token's claims win.
        """
        secret = await self._client_secret(tenant)
        client_id = tenant.oidc_client_id or ""
        try:
            tokens = await self._oidc.exchange_code(
                meta,
                client_id=client_id,
                client_secret=secret,
                code=code,
                redirect_uri=redirect_uri,
                code_verifier=payload["v"],
            )
            claims = await self._oidc.validate_id_token(
                meta, tokens["id_token"], client_id=client_id, nonce=payload["n"]
            )
        except OidcError as exc:
            raise _refuse(SsoErrorCode.failed, tenant.id, str(exc)) from exc
        sub = claims.get("sub")
        if not isinstance(sub, str) or not sub or len(sub) > _SUBJECT_MAX:
            raise _refuse(SsoErrorCode.failed, tenant.id, "unusable sub claim")

        groups_claim = tenant.oidc_groups_claim
        needs_groups = groups_claim not in claims and not _is_overage(
            claims, groups_claim
        )
        access_token = tokens.get("access_token")
        if (
            (not _text(claims.get("email")) or needs_groups)
            and meta.userinfo_endpoint
            and isinstance(access_token, str)
        ):
            try:
                info = await self._oidc.userinfo(meta, access_token)
            except OidcError as exc:
                raise _refuse(SsoErrorCode.failed, tenant.id, str(exc)) from exc
            if info.get("sub") != sub:
                raise _refuse(SsoErrorCode.failed, tenant.id, "userinfo sub mismatch")
            claims = {**info, **claims}
        return claims

    async def _client_secret(self, tenant: Tenant) -> str:
        """Return the tenant's client secret: referenced from a secret, or stored.

        A referenced secret is read at every sign-in, so rotating it (in Vault,
        say) takes effect without touching A2Flow.

        Raises:
            SsoLoginError: ``unavailable``, if the reference cannot be resolved
                or the stored secret no longer decrypts.
        """
        if tenant.oidc_client_secret_ref:
            try:
                return await self._secrets_for_tenant(tenant.id).resolve_ref(
                    tenant.oidc_client_secret_ref
                )
            except SecretResolutionError as exc:
                raise _refuse(SsoErrorCode.unavailable, tenant.id, str(exc)) from exc
        try:
            cipher = data_key_cipher(tenant.data_key)
            return cipher.decrypt(tenant.oidc_client_secret or "")
        except ValueError as exc:
            raise _refuse(
                SsoErrorCode.unavailable, tenant.id, "undecryptable client secret"
            ) from exc

    async def _resolve(self, tenant: Tenant, claims: dict[str, Any]) -> LoginResult:
        """Resolve, link or create the user, sync groups and mint the session."""
        sub: str = claims["sub"]
        groups_repo = self._groups_for_tenant(tenant.id)
        overage = _is_overage(claims, tenant.oidc_groups_claim)
        idp_groups = _groups(claims.get(tenant.oidc_groups_claim))

        user = await self._users.get_by_oidc_subject(tenant.id, sub)
        if user is not None:
            _require_active(user, tenant.id)
            return await self._finish(user, tenant.id, groups_repo, overage, idp_groups)

        email = _text(claims.get("email"))
        if not email:
            raise _refuse(SsoErrorCode.failed, tenant.id, "no e-mail claim")
        try:
            _EMAIL.validate_python(email)
        except ValidationError as exc:
            raise _refuse(
                SsoErrorCode.failed, tenant.id, "unusable e-mail claim"
            ) from exc
        key = email.casefold()
        matches = [
            u
            for u in await self._users.list_by_email(tenant.id, email)
            if u.email.strip().casefold() == key
        ]
        unlinked = [u for u in matches if u.oidc_subject is None]
        trusted = claims.get("email_verified") is True or tenant.oidc_trust_email

        if trusted and unlinked:
            if len(unlinked) > 1:
                raise _refuse(SsoErrorCode.failed, tenant.id, "several e-mail matches")
            _require_active(unlinked[0], tenant.id)
            try:
                user = await self._users.set_oidc_subject(unlinked[0].id, sub)
            except UniqueViolationError as exc:
                raise _refuse(SsoErrorCode.failed, tenant.id, "link race") from exc
            return await self._finish(user, tenant.id, groups_repo, overage, idp_groups)

        if overage:
            raise _refuse(SsoErrorCode.not_permitted, tenant.id, "groups overage")
        mapped = await groups_repo.list_mapped()
        if not any(g.idp_group in idp_groups for g in mapped):
            raise _refuse(SsoErrorCode.not_permitted, tenant.id, "no mapped group")
        if matches:
            # Untrusted e-mail, or one already tied to another subject: never
            # mint a second account for an address the tenant already holds.
            raise _refuse(
                SsoErrorCode.failed, tenant.id, "e-mail already used by an account"
            )

        username = await self._free_username(
            tenant.id,
            normalize_username(
                [_text(claims.get("preferred_username")), email.partition("@")[0]]
            ),
        )
        first, _, last = _text(claims.get("name")).partition(" ")
        try:
            user = await self._users.create_sso_user(
                tenant_id=tenant.id,
                username=username,
                first_name=(_text(claims.get("given_name")) or first or username)[
                    :_NAME_MAX
                ],
                last_name=(
                    _text(claims.get("family_name")) or last.strip() or username
                )[:_NAME_MAX],
                email=email,
                email_verified=trusted,
                oidc_subject=sub,
            )
        except UniqueViolationError as exc:
            raise _refuse(SsoErrorCode.failed, tenant.id, "creation race") from exc
        return await self._finish(user, tenant.id, groups_repo, False, idp_groups)

    async def _free_username(self, tenant_id: str, base: str) -> str:
        """Return ``base``, or ``base-2``, ``base-3`` ... whichever is free."""
        name, n = base, 1
        while await self._users.get_by_username(name, tenant_id=tenant_id):
            n += 1
            suffix = f"-{n}"
            name = base[: _USERNAME_MAX - len(suffix)] + suffix
        return name

    async def _finish(
        self,
        user: User,
        tenant_id: str,
        groups_repo: UserGroupRepository,
        overage: bool,
        idp_groups: list[str],
    ) -> LoginResult:
        """Sync mapped-group membership (unless overage) and mint the session."""
        if overage:
            logger.warning(
                "SSO groups overage for tenant %s; keeping memberships", tenant_id
            )
        else:
            await groups_repo.sync_mapped_membership(user.id, idp_groups)
        return await self._auth.start_session(user)


def _sso_configured(tenant: Tenant) -> bool:
    """Return whether ``tenant`` has SSO switched on with every required field set."""
    return bool(
        tenant.oidc_enabled
        and tenant.oidc_issuer
        and tenant.oidc_client_id
        and (tenant.oidc_client_secret or tenant.oidc_client_secret_ref)
    )


def _require_active(user: User, tenant_id: str) -> None:
    """Refuse a disabled or soft-deleted user with ``account_disabled``."""
    if not user.enabled or user.deleted_at is not None:
        raise _refuse(SsoErrorCode.account_disabled, tenant_id, "user disabled")


def _refuse(code: SsoErrorCode, tenant_id: str | None, reason: str) -> SsoLoginError:
    """Log a refusal at ``warning`` and return the error to raise.

    Args:
        code: The public reason.
        tenant_id: The tenant concerned, when known.
        reason: Log-only detail; never a token, code, secret or claim set.
    """
    logger.warning(
        "SSO sign-in refused (%s) for tenant %s: %s", code, tenant_id, reason
    )
    return SsoLoginError(code, reason)
