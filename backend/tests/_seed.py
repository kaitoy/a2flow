"""Test helpers for seeding the users that the audit foreign keys require.

Every persistent entity records ``created_by`` / ``updated_by`` as a foreign key
to ``users.id``. Tests therefore need the acting users to exist before they write
any record. These helpers seed the system user plus a small set of named test
actors so existing tests can keep using ``X-User-Id: alice`` style headers.
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.bootstrap import seed_system_user
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID, Role, User

#: Named test actors seeded with ``id == username`` so ``X-User-Id: alice`` works.
DEFAULT_TEST_USER_IDS: tuple[str, ...] = ("alice", "bob", "carol", "owner", "tester")

#: Roles granted to every seeded test actor. ``approver`` keeps the pre-RBAC
#: test semantics: any named actor can be designated as an approval's approver
#: (the ``request_approval`` tool validates approver eligibility).
DEFAULT_TEST_USER_ROLES: tuple[Role, ...] = (Role.approver,)

#: Tenant id every test client is scoped to by default (see conftest.py's
#: ``X-User-Tenant-Id`` header handling).
DEFAULT_TEST_TENANT_ID = "tenant-default"


async def seed_tenant(
    engine: AsyncEngine, tenant_id: str = DEFAULT_TEST_TENANT_ID
) -> None:
    """Seed a single Tenant row if it does not already exist.

    Args:
        engine: The async engine bound to the test database.
        tenant_id: Id of the tenant to seed.
    """
    async with AsyncSession(engine) as session:
        if await session.get(Tenant, tenant_id) is None:
            session.add(
                Tenant(
                    id=tenant_id,
                    name=f"Test Tenant ({tenant_id})",
                    slug=tenant_id,
                    enabled=True,
                    created_by=SYSTEM_USER_ID,
                    updated_by=SYSTEM_USER_ID,
                )
            )
            await session.commit()


async def seed_users(
    engine: AsyncEngine,
    ids: Sequence[str] = DEFAULT_TEST_USER_IDS,
    *,
    roles: Sequence[Role] = DEFAULT_TEST_USER_ROLES,
    tenant_id: str | None = None,
) -> None:
    """Seed the system user and the given named test actors into the database.

    Args:
        engine: The async engine bound to the test database.
        ids: User ids to seed; each becomes a user whose ``id`` equals its
            ``username`` so it can be referenced by ``X-User-Id`` headers.
        roles: Roles granted to each seeded actor; defaults to ``approver`` so
            actors stay eligible as approval approvers.
        tenant_id: Tenant each seeded actor belongs to. Defaults to ``None``,
            which resolves to :data:`DEFAULT_TEST_TENANT_ID` unless ``roles``
            includes ``super_admin`` (which must stay tenant-less) — every
            other user must carry a ``tenant_id``
            (``ck_users_non_super_admin_requires_tenant``). Pass an explicit
            value to opt out. The resolved tenant is seeded automatically if
            missing, so callers don't need to seed it themselves first.
    """
    if tenant_id is None:
        tenant_id = None if Role.super_admin in roles else DEFAULT_TEST_TENANT_ID
    async with AsyncSession(engine) as session:
        await seed_system_user(session)
    if tenant_id is not None:
        await seed_tenant(engine, tenant_id)
    async with AsyncSession(engine) as session:
        for uid in ids:
            if await session.get(User, uid) is None:
                session.add(
                    User(
                        id=uid,
                        username=uid,
                        first_name=uid.capitalize(),
                        last_name="Test",
                        password="testpassword",
                        email=f"{uid}@test.local",
                        roles=[role.value for role in roles],
                        tenant_id=tenant_id,
                        created_by=SYSTEM_USER_ID,
                        updated_by=SYSTEM_USER_ID,
                    )
                )
        await session.commit()
