"""Bootstrap helpers that seed required baseline records on application startup."""

import logging
import secrets

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.password import hash_password
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID, Role, User

logger = logging.getLogger(__name__)

#: Bytes of entropy for a generated seed password (used when ``ROOT_PASSWORD``
#: or ``ADMIN_PASSWORD`` is unset). ``token_urlsafe`` renders ~1.3 chars/byte,
#: so 16 bytes yields a ~22-character password: comfortably above the model's
#: 12-character minimum and short enough to copy out of a log line.
_GENERATED_PASSWORD_BYTES = 16

#: Slug of the tenant seeded on first startup to hold the initial ``admin`` user.
_DEFAULT_TENANT_SLUG = "default"


async def seed_system_user(session: AsyncSession) -> None:
    """Insert the system user if it does not already exist.

    The system user owns the bootstrap records as their ``created_by`` /
    ``updated_by`` — including itself, via a self-referential foreign key. It is
    hidden from the user list and cannot log in (its password hash matches no
    input). The first real user is created with ``X-User-Id`` set to
    :data:`SYSTEM_USER_ID`.

    Args:
        session: Database session used to read and insert the user.
    """
    if await session.get(User, SYSTEM_USER_ID) is not None:
        return
    system = User(
        id=SYSTEM_USER_ID,
        username="system",
        first_name="System",
        last_name="User",
        password=hash_password(secrets.token_urlsafe(32)),
        email="system@localhost",
        enabled=False,
        email_verified=False,
        created_by=SYSTEM_USER_ID,
        updated_by=SYSTEM_USER_ID,
    )
    session.add(system)
    await session.commit()


def _resolve_seed_password(
    configured: str | None, *, subject: str, env_var: str
) -> str:
    """Return a configured seed password, or generate and log one once.

    Args:
        configured: Password read from settings (e.g.
            ``Settings.root_password``), or ``None``/empty when unset.
        subject: Human-readable account description interpolated into the
            generated-password log message, e.g. ``"'root' user"``.
        env_var: Name of the environment variable ``configured`` came from,
            e.g. ``"ROOT_PASSWORD"`` — also interpolated into that message.

    Returns:
        ``configured`` unchanged when truthy; otherwise a freshly generated
        password, logged once at ``WARNING`` since it can't be recovered
        afterwards.
    """
    if configured:
        return configured
    password = secrets.token_urlsafe(_GENERATED_PASSWORD_BYTES)
    logger.warning(
        f"{env_var} not set; generated a random password for the {subject}. "
        "This is logged once and cannot be recovered afterwards - copy it "
        "now, then change it after logging in: %s",
        password,
    )
    return password


async def seed_root_user(session: AsyncSession) -> None:
    """Create the initial ``root`` user, holding ``super_admin``, on first bootstrap.

    The user is granted the :attr:`Role.super_admin` role and no ``tenant_id``
    (platform-scoped), so a fresh deployment always has an account able to
    manage every tenant, user, and role. Skipped when any real (non-system)
    user already exists, so it runs only on the very first startup.

    This must run **before** :func:`seed_default_tenant_and_admin_user` in the
    startup sequence (see ``main.py``'s ``lifespan``): that function creates
    its own real (non-system) user, which would make this function's skip
    check wrongly conclude ``root`` already exists if the order were reversed.

    The password is read from ``config.Settings.root_password`` (the
    ``ROOT_PASSWORD`` environment variable); if unset (or empty), a random
    password is generated and logged once at ``WARNING`` level, since it
    cannot be recovered afterwards. The user is created with ``created_by`` /
    ``updated_by`` pointing at the seeded system user (:data:`SYSTEM_USER_ID`);
    its own ``id`` is an auto-generated UUID7.

    Args:
        session: Database session used to read and insert the user.
    """
    stmt = select(User).where(col(User.id) != SYSTEM_USER_ID).limit(1)
    if (await session.exec(stmt)).first() is not None:
        return
    password = _resolve_seed_password(
        get_settings().root_password, subject="'root' user", env_var="ROOT_PASSWORD"
    )
    root = User(
        username="root",
        first_name="Root",
        last_name="User",
        password=hash_password(password),
        email="root@localhost",
        enabled=True,
        email_verified=False,
        roles=[Role.super_admin.value],
        created_by=SYSTEM_USER_ID,
        updated_by=SYSTEM_USER_ID,
    )
    session.add(root)
    await session.commit()


async def seed_default_tenant_and_admin_user(session: AsyncSession) -> None:
    """Create the seeded ``Default`` tenant and its ``admin`` user on first bootstrap.

    The tenant (looked up by ``slug``) and the user (looked up by
    ``username``) are checked independently, so either can be (re)created on
    a later startup without duplicating the other. This must run **after**
    :func:`seed_root_user` — see that function's docstring for why.

    The ``admin`` user holds :attr:`Role.admin` (not ``super_admin``), scoped
    to the seeded tenant. Its password is read from
    ``config.Settings.admin_password`` (the ``ADMIN_PASSWORD`` environment
    variable), with the same generate-and-log-once-at-``WARNING`` fallback as
    :func:`seed_root_user`. Both records are created with ``created_by`` /
    ``updated_by`` pointing at the seeded system user (:data:`SYSTEM_USER_ID`).

    On a deployment that already has a pre-existing ``admin`` user from
    before this function existed (e.g. the old single seeded super_admin),
    the ``Default`` tenant is still created, but a second ``admin`` user is
    not — the username-uniqueness check skips it, leaving the legacy user's
    roles and ``tenant_id`` untouched.

    Args:
        session: Database session used to read and insert the tenant and user.
    """
    tenant_stmt = (
        select(Tenant).where(col(Tenant.slug) == _DEFAULT_TENANT_SLUG).limit(1)
    )
    tenant = (await session.exec(tenant_stmt)).first()
    if tenant is None:
        tenant = Tenant(
            name="Default",
            slug=_DEFAULT_TENANT_SLUG,
            enabled=True,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        # id is populated by BaseEntity's default_factory at construction
        # time, so read it before commit() expires the instance's attributes
        # (an AsyncSession attribute refresh outside a greenlet context would
        # raise MissingGreenlet).
        tenant_id = tenant.id
        session.add(tenant)
        await session.commit()
    else:
        tenant_id = tenant.id

    user_stmt = select(User).where(col(User.username) == "admin").limit(1)
    if (await session.exec(user_stmt)).first() is not None:
        return
    password = _resolve_seed_password(
        get_settings().admin_password, subject="'admin' user", env_var="ADMIN_PASSWORD"
    )
    admin = User(
        username="admin",
        first_name="Admin",
        last_name="User",
        password=hash_password(password),
        email="admin@localhost",
        enabled=True,
        email_verified=False,
        roles=[Role.admin.value],
        tenant_id=tenant_id,
        created_by=SYSTEM_USER_ID,
        updated_by=SYSTEM_USER_ID,
    )
    session.add(admin)
    await session.commit()
