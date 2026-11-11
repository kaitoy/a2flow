"""Tests for the OIDC sign-in service: start, callback, user resolution, group sync."""

import json
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.oidc_client import OidcClient
from infrastructure.password import hash_password
from infrastructure.secret_cipher import SecretCipher
from models.system_settings import SYSTEM_SETTINGS_ID, SystemSettings
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID, User
from models.user_group import UserGroup, UserGroupMember
from repositories.auth_session import SqlAuthSessionRepository
from repositories.exceptions import UnauthorizedError
from repositories.login_failure import SqlLoginFailureRepository
from repositories.system_settings import SqlSystemSettingsRepository
from repositories.tenant import SqlTenantRepository
from repositories.user import SqlUserRepository
from repositories.user_group import SqlUserGroupRepository
from services.auth import AuthService, LoginResult
from services.oidc_login import (
    STATE_TTL_SECONDS,
    OidcLoginService,
    SsoErrorCode,
    SsoLoginError,
    normalize_username,
)
from tests._engine import make_test_engine
from tests._oidc_fake import CLIENT_ID, ISSUER, FakeIdp
from tests._seed import seed_users

TENANT_ID = "t-acme"
BASE_URL = "https://a2flow.example.com"
PASSWORD = "correct-horse-battery"


@dataclass
class Ctx:
    """Everything a test needs: the service, its session, the fake IdP, the key."""

    svc: OidcLoginService
    auth: AuthService
    db: AsyncSession
    fake: FakeIdp
    key: bytes


@pytest_asyncio.fixture()
async def ctx() -> AsyncGenerator[Ctx, None]:
    """Seed tenant ``acme`` with SSO on and a mapped group ``Eng``; build the service."""
    engine = await make_test_engine()
    await seed_users(engine, ids=())
    key = Fernet.generate_key()
    cipher = SecretCipher(key)
    async with AsyncSession(engine, expire_on_commit=False) as db:
        db.add(
            Tenant(
                id=TENANT_ID,
                name="acme",
                display_name="Acme",
                enabled=True,
                oidc_enabled=True,
                oidc_issuer=ISSUER,
                oidc_client_id=CLIENT_ID,
                oidc_client_secret=cipher.encrypt("s3cret"),
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        settings = await db.get(SystemSettings, SYSTEM_SETTINGS_ID)
        assert settings is not None
        settings.app_base_url = BASE_URL
        db.add(settings)
        db.add(
            UserGroup(
                id="g-eng",
                name="Eng",
                idp_group="eng",
                roles=["developer"],
                tenant_id=TENANT_ID,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            )
        )
        await db.commit()

        fake = FakeIdp()
        users = SqlUserRepository(db)
        auth = AuthService(
            users,
            SqlAuthSessionRepository(db),
            SqlTenantRepository(db),
            SqlLoginFailureRepository(db),
        )
        svc = OidcLoginService(
            tenants=SqlTenantRepository(db),
            users=users,
            auth=auth,
            oidc=OidcClient(
                httpx.AsyncClient(transport=fake.transport), allowed_hosts=()
            ),
            cipher=cipher,
            system_settings=SqlSystemSettingsRepository(db),
            groups_for_tenant=lambda t: SqlUserGroupRepository(
                db, SqlUserRepository(db), tenant_id=t
            ),
        )
        try:
            yield Ctx(svc=svc, auth=auth, db=db, fake=fake, key=key)
        finally:
            await engine.dispose()


async def begin(c: Ctx, **claims: Any) -> dict[str, Any]:
    """Start a flow for ``acme`` and arm the IdP; return ``complete`` kwargs.

    A claim passed as ``None`` is removed from the ID token.
    """
    start = await c.svc.start("acme")
    query = dict(parse_qsl(urlsplit(start.authorization_url).query))
    merged = c.fake.claims(nonce=query["nonce"], **claims)
    c.fake.next_claims = {k: v for k, v in merged.items() if v is not None}
    return {
        "state_cookie": start.state_cookie,
        "state": query["state"],
        "code": "code-1",
        "error": None,
    }


async def run_flow(c: Ctx, **claims: Any) -> LoginResult:
    """Run a whole sign-in with the given ID-token claims."""
    return await c.svc.complete(**await begin(c, **claims))


async def refused(c: Ctx, **claims: Any) -> SsoErrorCode:
    """Run a sign-in that must be refused; return its error code."""
    with pytest.raises(SsoLoginError) as info:
        await run_flow(c, **claims)
    return info.value.code


async def add_user(
    c: Ctx,
    username: str,
    email: str,
    *,
    oidc_subject: str | None = None,
    enabled: bool = True,
    first_name: str = "First",
    last_name: str = "Last",
) -> User:
    """Insert a user into ``acme``."""
    user = User(
        username=username,
        first_name=first_name,
        last_name=last_name,
        password=None,
        email=email,
        enabled=enabled,
        oidc_subject=oidc_subject,
        tenant_id=TENANT_ID,
        created_by=SYSTEM_USER_ID,
        updated_by=SYSTEM_USER_ID,
    )
    c.db.add(user)
    await c.db.commit()
    return user


async def group_names(c: Ctx, user_id: str) -> set[str]:
    """Return the names of the groups ``user_id`` belongs to."""
    rows = await c.db.exec(
        select(UserGroup.name)
        .join(UserGroupMember, col(UserGroupMember.group_id) == col(UserGroup.id))
        .where(col(UserGroupMember.user_id) == user_id)
    )
    return set(rows.all())


async def user_count(c: Ctx) -> int:
    """Return how many users ``acme`` has."""
    rows = await c.db.exec(select(func.count()).where(col(User.tenant_id) == TENANT_ID))
    return int(rows.one())


@pytest.mark.asyncio
async def test_first_login_creates_user_in_mapped_group(ctx: Ctx) -> None:
    result = await run_flow(
        ctx,
        sub="s1",
        email="a@x.com",
        email_verified=True,
        groups=["eng"],
        preferred_username="alice",
        name="Alice Liddell",
    )
    user = result.user
    assert user.username == "alice"
    assert user.password is None
    assert user.oidc_subject == "s1"
    assert user.email == "a@x.com"
    assert user.email_verified is True
    assert user.roles == []
    assert (user.first_name, user.last_name) == ("Alice", "Liddell")
    assert user.created_by == SYSTEM_USER_ID
    assert await group_names(ctx, user.id) == {"Eng"}
    assert result.session_token and result.csrf_token


@pytest.mark.asyncio
async def test_second_login_resolves_by_sub(ctx: Ctx) -> None:
    first = await run_flow(ctx, sub="s1", email="a@x.com", groups=["eng"])
    # Already in the wanted mapped group: the sync must not insert it twice.
    second = await run_flow(ctx, sub="s1", email="changed@x.com", groups=["eng"])
    assert second.user.id == first.user.id
    assert second.user.email == "a@x.com"
    assert await group_names(ctx, first.user.id) == {"Eng"}
    assert await user_count(ctx) == 1

    # Break-glass: an admin sets a password; both sign-in paths keep working.
    second.user.password = hash_password(PASSWORD)
    ctx.db.add(second.user)
    await ctx.db.commit()
    third = await run_flow(ctx, sub="s1", email="a@x.com", groups=["eng"])
    assert third.user.id == first.user.id
    by_password = await ctx.auth.login(
        first.user.username, PASSWORD, tenant_name="acme"
    )
    assert by_password.user.id == first.user.id


@pytest.mark.asyncio
async def test_not_in_mapped_group_is_not_permitted(ctx: Ctx) -> None:
    assert await refused(ctx, sub="s1", groups=["other"]) == SsoErrorCode.not_permitted
    assert await user_count(ctx) == 0


@pytest.mark.asyncio
async def test_overage_new_user_not_permitted(ctx: Ctx) -> None:
    code = await refused(ctx, sub="s1", _claim_names={"groups": "src1"})
    assert code == SsoErrorCode.not_permitted
    assert await user_count(ctx) == 0


@pytest.mark.asyncio
async def test_overage_existing_user_keeps_memberships(ctx: Ctx) -> None:
    first = await run_flow(ctx, sub="s1", groups=["eng"])
    again = await run_flow(ctx, sub="s1", _claim_names={"groups": "src1"})
    assert again.user.id == first.user.id
    assert await group_names(ctx, first.user.id) == {"Eng"}


@pytest.mark.asyncio
async def test_links_existing_user_by_verified_email(ctx: Ctx) -> None:
    alice = await add_user(ctx, "alice", "alice@x.com")
    result = await run_flow(
        ctx, sub="s9", email="Alice@X.com ", email_verified=True, groups=["eng"]
    )
    assert result.user.id == alice.id
    assert result.user.oidc_subject == "s9"
    assert await user_count(ctx) == 1
    assert await group_names(ctx, alice.id) == {"Eng"}


@pytest.mark.asyncio
async def test_unverified_email_not_linked_unless_trusted(ctx: Ctx) -> None:
    alice = await add_user(ctx, "alice", "a@x.com")
    # Untrusted and an account already owns the address: refused, no second account.
    code = await refused(
        ctx, sub="s1", email="a@x.com", groups=["eng"], preferred_username="alice"
    )
    assert code == SsoErrorCode.failed
    assert await user_count(ctx) == 1
    assert alice.oidc_subject is None

    bob = await add_user(ctx, "bob", "b@x.com")
    tenant = await ctx.db.get(Tenant, TENANT_ID)
    assert tenant is not None
    tenant.oidc_trust_email = True
    ctx.db.add(tenant)
    await ctx.db.commit()
    linked = await run_flow(ctx, sub="s2", email="b@x.com", groups=["eng"])
    assert linked.user.id == bob.id
    assert linked.user.oidc_subject == "s2"


@pytest.mark.asyncio
async def test_unusable_email_is_failed_and_creates_nothing(ctx: Ctx) -> None:
    for bad in ("alice@corp.local", "not-an-address"):
        code = await refused(ctx, sub="s1", email=bad, groups=["eng"])
        assert code == SsoErrorCode.failed
    assert await user_count(ctx) == 0


@pytest.mark.asyncio
async def test_other_tenant_rows_never_match(ctx: Ctx) -> None:
    ctx.db.add(
        Tenant(
            id="t-beta",
            name="beta",
            display_name="Beta",
            enabled=True,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
    )
    await ctx.db.commit()
    beta = [
        User(
            username=name,
            first_name="B",
            last_name="B",
            password=None,
            email=email,
            oidc_subject=subject,
            tenant_id="t-beta",
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        for name, email, subject in (
            ("bsub", "other@beta.com", "s1"),
            ("bmail", "a@x.com", None),
        )
    ]
    ctx.db.add_all(beta)
    await ctx.db.commit()

    result = await run_flow(
        ctx, sub="s1", email="a@x.com", email_verified=True, groups=["eng"]
    )
    assert result.user.tenant_id == TENANT_ID
    assert result.user.id not in {u.id for u in beta}
    for u in beta:
        await ctx.db.refresh(u)
    assert [(u.oidc_subject) for u in beta] == ["s1", None]
    assert await user_count(ctx) == 1


@pytest.mark.asyncio
async def test_password_login_as_sso_only_user_burns_a_check(
    ctx: Ctx, monkeypatch: pytest.MonkeyPatch
) -> None:
    await add_user(ctx, "alice", "a@x.com", oidc_subject="s1")
    burned: list[str] = []
    monkeypatch.setattr("services.auth.burn_password_check", burned.append)
    with pytest.raises(UnauthorizedError):
        await ctx.auth.login("alice", PASSWORD, tenant_name="acme")
    assert burned == [PASSWORD]


@pytest.mark.asyncio
async def test_two_email_candidates_is_failed(ctx: Ctx) -> None:
    await add_user(ctx, "alice", "a@x.com")
    await add_user(ctx, "alice2", "A@x.com")
    code = await refused(
        ctx, sub="s1", email="a@x.com", email_verified=True, groups=["eng"]
    )
    assert code == SsoErrorCode.failed
    assert await user_count(ctx) == 2


@pytest.mark.asyncio
async def test_email_linked_to_other_sub_is_failed(ctx: Ctx) -> None:
    await add_user(ctx, "alice", "a@x.com", oidc_subject="other")
    for verified in (True, None):
        code = await refused(
            ctx, sub="s1", email="a@x.com", email_verified=verified, groups=["eng"]
        )
        assert code == SsoErrorCode.failed
    assert await user_count(ctx) == 1


@pytest.mark.asyncio
async def test_disabled_user_and_disabled_tenant_are_account_disabled(
    ctx: Ctx,
) -> None:
    await add_user(ctx, "alice", "a@x.com", oidc_subject="s1", enabled=False)
    # Resolved by sub and disabled: never re-linked or recreated via e-mail.
    code = await refused(
        ctx, sub="s1", email="a@x.com", email_verified=True, groups=["eng"]
    )
    assert code == SsoErrorCode.account_disabled
    # An e-mail match that is disabled is not linked either.
    await add_user(ctx, "bob", "b@x.com", enabled=False)
    code = await refused(
        ctx, sub="s2", email="b@x.com", email_verified=True, groups=["eng"]
    )
    assert code == SsoErrorCode.account_disabled
    assert await user_count(ctx) == 2

    kwargs = await begin(ctx, sub="s3", email="c@x.com", groups=["eng"])
    tenant = await ctx.db.get(Tenant, TENANT_ID)
    assert tenant is not None
    tenant.enabled = False
    ctx.db.add(tenant)
    await ctx.db.commit()
    with pytest.raises(SsoLoginError) as info:
        await ctx.svc.complete(**kwargs)
    assert info.value.code == SsoErrorCode.account_disabled
    assert await user_count(ctx) == 2


@pytest.mark.asyncio
async def test_sync_removes_from_mapped_keeps_unmapped(ctx: Ctx) -> None:
    alice = await add_user(ctx, "alice", "a@x.com", oidc_subject="s1")
    ctx.db.add(
        UserGroup(
            id="g-ops",
            name="Ops",
            tenant_id=TENANT_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
    )
    await ctx.db.commit()
    ctx.db.add(UserGroupMember(group_id="g-eng", user_id=alice.id))
    ctx.db.add(UserGroupMember(group_id="g-ops", user_id=alice.id))
    await ctx.db.commit()
    await run_flow(ctx, sub="s1", groups=[])
    assert await group_names(ctx, alice.id) == {"Ops"}


@pytest.mark.asyncio
async def test_groups_claim_string_is_single_group(ctx: Ctx) -> None:
    result = await run_flow(ctx, sub="s1", groups="eng")
    assert await group_names(ctx, result.user.id) == {"Eng"}
    await run_flow(ctx, sub="s1", groups=123)
    assert await group_names(ctx, result.user.id) == set()
    assert await refused(ctx, sub="s2", groups=123) == SsoErrorCode.not_permitted


@pytest.mark.asyncio
async def test_username_collision_and_normalisation(ctx: Ctx) -> None:
    await add_user(ctx, "yamada", "other@x.com")
    yamada = await run_flow(
        ctx, sub="s1", preferred_username="山田", email="yamada@x.com", groups=["eng"]
    )
    assert yamada.user.username == "yamada-2"
    j1 = await run_flow(
        ctx, sub="s2", preferred_username="j", email="j@x.com", groups=["eng"]
    )
    assert j1.user.username == "user"
    j2 = await run_flow(
        ctx, sub="s3", preferred_username="j", email="j@y.com", groups=["eng"]
    )
    assert j2.user.username == "user-2"


def test_normalize_username() -> None:
    assert normalize_username([None, "a b!c", "x"]) == "abc"
    assert normalize_username(["ab", "a" * 80]) == "a" * 64
    assert normalize_username(["山田", "", None]) == "user"


@pytest.mark.asyncio
async def test_missing_email_is_failed(ctx: Ctx) -> None:
    ctx.fake.userinfo_claims = {"sub": "s1"}
    assert await refused(ctx, sub="s1", email=None, groups=["eng"]) == (
        SsoErrorCode.failed
    )
    assert await user_count(ctx) == 0


@pytest.mark.asyncio
async def test_userinfo_fills_missing_email(ctx: Ctx) -> None:
    ctx.fake.userinfo_claims = {"sub": "s1", "email": "u@x.com", "groups": ["eng"]}
    result = await run_flow(ctx, sub="s1", email=None)
    assert result.user.email == "u@x.com"
    assert await group_names(ctx, result.user.id) == {"Eng"}


@pytest.mark.asyncio
async def test_userinfo_with_other_sub_is_failed(ctx: Ctx) -> None:
    ctx.fake.userinfo_claims = {"sub": "someone-else", "email": "u@x.com"}
    code = await refused(ctx, sub="s1", email=None, groups=["eng"])
    assert code == SsoErrorCode.failed
    assert await user_count(ctx) == 0


@pytest.mark.asyncio
async def test_userinfo_not_called_when_token_has_everything(ctx: Ctx) -> None:
    await run_flow(ctx, sub="s1", email="a@x.com", groups=["eng"])
    assert ctx.fake.count("/userinfo") == 0


@pytest.mark.asyncio
async def test_start_unavailable_is_uniform(ctx: Ctx) -> None:
    async def code_for(name: str) -> SsoErrorCode:
        with pytest.raises(SsoLoginError) as info:
            await ctx.svc.start(name)
        return info.value.code

    tenant = await ctx.db.get(Tenant, TENANT_ID)
    settings = await ctx.db.get(SystemSettings, SYSTEM_SETTINGS_ID)
    assert tenant is not None and settings is not None

    async def save(*rows: Any) -> None:
        for row in rows:
            ctx.db.add(row)
        await ctx.db.commit()

    assert await code_for("nope") == SsoErrorCode.unavailable

    tenant.enabled = False
    await save(tenant)
    assert await code_for("acme") == SsoErrorCode.unavailable
    tenant.enabled = True

    tenant.oidc_enabled = False
    await save(tenant)
    assert await code_for("acme") == SsoErrorCode.unavailable
    tenant.oidc_enabled = True

    tenant.oidc_client_secret = None
    await save(tenant)
    assert await code_for("acme") == SsoErrorCode.unavailable
    tenant.oidc_client_secret = SecretCipher(ctx.key).encrypt("s3cret")

    settings.app_base_url = None
    await save(tenant, settings)
    assert await code_for("acme") == SsoErrorCode.unavailable
    settings.app_base_url = BASE_URL

    tenant.oidc_issuer = "https://elsewhere.example.com"
    await save(tenant, settings)
    assert await code_for("acme") == SsoErrorCode.unavailable


@pytest.mark.asyncio
async def test_start_builds_url_and_encrypted_cookie(ctx: Ctx) -> None:
    start = await ctx.svc.start("acme")
    query = dict(parse_qsl(urlsplit(start.authorization_url).query))
    assert query["redirect_uri"] == f"{BASE_URL}/api/v1/auth/oidc/callback"
    assert query["client_id"] == CLIENT_ID
    payload = json.loads(SecretCipher(ctx.key).decrypt(start.state_cookie))
    assert payload["t"] == TENANT_ID
    assert payload["s"] == query["state"]
    assert payload["n"] == query["nonce"]
    assert payload["v"]


@pytest.mark.asyncio
async def test_expired_state_cookie_is_failed(ctx: Ctx) -> None:
    kwargs = await begin(ctx, sub="s1", groups=["eng"])
    payload = SecretCipher(ctx.key).decrypt(kwargs["state_cookie"])
    old = int(time.time()) - STATE_TTL_SECONDS - 5
    kwargs["state_cookie"] = (
        Fernet(ctx.key).encrypt_at_time(payload.encode(), old).decode()
    )
    with pytest.raises(SsoLoginError) as info:
        await ctx.svc.complete(**kwargs)
    assert info.value.code == SsoErrorCode.failed
    assert ctx.fake.count("/token") == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "override",
    [
        {"error": "access_denied"},
        {"state_cookie": None},
        {"state_cookie": "garbage"},
        {"state": None},
        {"state": "wrong"},
        {"code": None},
    ],
)
async def test_bad_callback_is_failed(ctx: Ctx, override: dict[str, Any]) -> None:
    kwargs = {**await begin(ctx, sub="s1", groups=["eng"]), **override}
    with pytest.raises(SsoLoginError) as info:
        await ctx.svc.complete(**kwargs)
    assert info.value.code == SsoErrorCode.failed
    assert ctx.fake.count("/token") == 0


@pytest.mark.asyncio
async def test_existing_user_names_not_overwritten(ctx: Ctx) -> None:
    alice = await add_user(
        ctx, "alice", "alice@x.com", first_name="Alice", last_name="Smith"
    )
    claims: dict[str, Any] = {
        "sub": "s1",
        "email": "alice@x.com",
        "email_verified": True,
        "groups": ["eng"],
        "given_name": "Eve",
        "family_name": "Evil",
    }
    await run_flow(ctx, **claims)
    claims["email"] = "eve@evil.com"
    result = await run_flow(ctx, **claims)
    assert result.user.id == alice.id
    assert (result.user.first_name, result.user.last_name) == ("Alice", "Smith")
    assert result.user.email == "alice@x.com"
