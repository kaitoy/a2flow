"""Bootstrap helpers that seed required baseline records on application startup."""

import logging
import secrets

from pydantic import ValidationError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.password import hash_password
from infrastructure.secret_cipher import get_secret_cipher
from models.system_settings import (
    SYSTEM_SETTINGS_ID,
    SystemSettings,
    SystemSettingsUpdate,
)
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID, Role, User
from repositories.exceptions import SystemSettingsValidationError
from repositories.system_settings import SqlSystemSettingsRepository
from services.system_settings import SystemSettingsService

logger = logging.getLogger(__name__)

#: Attribute names on config.Settings that apply_system_settings_env_overrides
#: may apply, exactly as SystemSettingsUpdate's fields expect (snake_case;
#: populate_by_name=True accepts these directly without the camelCase alias).
_SYSTEM_SETTINGS_ENV_FIELDS = (
    "app_base_url",
    "smtp_enabled",
    "smtp_host",
    "smtp_port",
    "smtp_security",
    "smtp_username",
    "smtp_password",
    "smtp_from_email",
    "smtp_from_name",
)


async def seed_system_settings(session: AsyncSession) -> None:
    """Insert the singleton system-settings row if it does not already exist.

    Seeding it up front rather than creating it lazily on first write means
    every reader can assume the row exists: ``GET /system-settings`` returns the
    defaults without a special case, and the notification dispatcher's SMTP
    lookup is a plain read. The row is owned by the system user, so this must
    run after :func:`seed_system_user`.

    The seeded defaults leave email delivery switched off, so a fresh
    deployment behaves exactly as it did before it had this table.

    Args:
        session: Database session used to read and insert the row.
    """
    if await session.get(SystemSettings, SYSTEM_SETTINGS_ID) is not None:
        return
    session.add(
        SystemSettings(
            id=SYSTEM_SETTINGS_ID,
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
    )
    await session.commit()


async def apply_system_settings_env_overrides(session: AsyncSession) -> None:
    """Apply whichever ``APP_BASE_URL``/``SMTP_*`` env vars are set onto the settings row.

    Runs on every startup, not just the first: an operator may add or rotate
    ``APP_BASE_URL`` or a ``SMTP_*`` variable on a later deploy (e.g. changing
    ``SMTP_PASSWORD``), and that should reach the database without a manual
    admin-UI edit. Only fields whose environment variable is actually set are
    touched — this is built by constructing a real
    :class:`~models.system_settings.SystemSettingsUpdate` from just those
    fields, not ``model_construct`` (which would skip validation entirely),
    so pydantic's ``model_fields_set`` records exactly the env-sourced fields
    as "set", and
    :meth:`~services.system_settings.SystemSettingsService.update` /
    :meth:`~repositories.system_settings.SqlSystemSettingsRepository.update`'s
    ``exclude_unset=True`` handling — the same mechanism the admin UI's
    partial PATCH already relies on — leaves every other field, including
    anything configured by hand through the admin UI, untouched.

    ``SMTP_ENABLED`` is never inferred from the presence of the other
    ``SMTP_*`` variables; it must be set explicitly, matching the opt-in
    default the row itself is seeded with (see :func:`seed_system_settings`).
    The other SMTP fields, when set, are still applied even while
    ``SMTP_ENABLED`` is absent or false: :func:`services.system_settings._assert_usable`
    only requires a host and sender address once the *merged* ``smtp_enabled``
    ends up true, so staging a relay's host/username/password ahead of
    flipping the flag on is harmless — it lets "configure the relay" and
    "turn delivery on" ship as two separate deploys. ``APP_BASE_URL`` has no
    such enable flag; when set, it is applied unconditionally.

    A malformed value — a pydantic field-level failure (an out-of-range
    ``SMTP_PORT``, a malformed ``SMTP_FROM_EMAIL``, an unrecognized
    ``SMTP_SECURITY``, an ``APP_BASE_URL`` not starting with
    ``http://``/``https://``) or the service's business-rule check (e.g.
    ``SMTP_ENABLED=true`` with no ``SMTP_HOST``) — is logged as a
    ``WARNING`` (naming only the offending field(s), never their value, so a
    bad ``SMTP_PASSWORD`` is never written to the log) and the entire apply
    is skipped: the row keeps whatever configuration it already had, and
    startup continues normally.

    Must run after :func:`seed_system_settings` — the row has to exist,
    since :meth:`~services.system_settings.SystemSettingsService.update`
    raises ``NotFoundError`` on a missing row rather than creating one — and
    after :func:`seed_system_user`, since the update stamps ``updated_by``
    with :data:`SYSTEM_USER_ID`, which must already satisfy the ``users``
    foreign key.

    Args:
        session: Database session used to read and write the settings row.
    """
    settings = get_settings()
    set_fields = {
        field: getattr(settings, field)
        for field in _SYSTEM_SETTINGS_ENV_FIELDS
        if getattr(settings, field) is not None
    }
    if not set_fields:
        return

    try:
        update = SystemSettingsUpdate(**set_fields)
    except ValidationError as exc:
        bad_fields = ", ".join(
            str(err["loc"][0])
            for err in exc.errors(
                include_url=False, include_input=False, include_context=False
            )
        )
        logger.warning(
            "Invalid APP_BASE_URL/SMTP_* environment configuration for "
            "field(s) %s; leaving the stored system settings unchanged. "
            "(Values are never logged here, including SMTP_PASSWORD.)",
            bad_fields,
        )
        return

    service = SystemSettingsService(
        SqlSystemSettingsRepository(session), get_secret_cipher()
    )
    try:
        await service.update(update, user_id=SYSTEM_USER_ID)
    except SystemSettingsValidationError as exc:
        logger.warning(
            "SMTP_* environment configuration would leave email delivery "
            "unusable (%s); leaving the stored system settings unchanged.",
            exc.reason,
        )


#: Bytes of entropy for a generated seed password (used when ``ROOT_PASSWORD``
#: or ``ADMIN_PASSWORD`` is unset). ``token_urlsafe`` renders ~1.3 chars/byte,
#: so 16 bytes yields a ~22-character password: comfortably above the model's
#: 12-character minimum and short enough to copy out of a log line.
_GENERATED_PASSWORD_BYTES = 16

#: Name (slug) of the tenant seeded on first startup to hold the initial
#: ``admin`` user. Also the tenant the demo dataset is registered in — see
#: :mod:`infrastructure.demo_data`.
DEFAULT_TENANT_NAME = "default"


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


def resolve_seed_password(configured: str | None, *, subject: str, env_var: str) -> str:
    """Return a configured seed password, or generate and log one once.

    Shared by the seed functions below and by :mod:`infrastructure.demo_data`,
    so every bootstrap account follows the same configure-or-generate rule.

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
    password = resolve_seed_password(
        get_settings().root_password, subject="'root' user", env_var="ROOT_PASSWORD"
    )
    root = User(
        username="root",
        first_name="Root",
        last_name="User",
        password=hash_password(password),
        email="root@example.com",
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

    The tenant (looked up by ``name``) and the user (looked up by ``username``
    scoped to this tenant's id) are checked independently, so either can be
    (re)created on a later startup without duplicating the other. This must
    run **after** :func:`seed_root_user` — see that function's docstring for
    why.

    The ``admin`` user holds :attr:`Role.admin` (not ``super_admin``), scoped
    to the seeded tenant. Its password is read from
    ``config.Settings.admin_password`` (the ``ADMIN_PASSWORD`` environment
    variable), with the same generate-and-log-once-at-``WARNING`` fallback as
    :func:`seed_root_user`. Both records are created with ``created_by`` /
    ``updated_by`` pointing at the seeded system user (:data:`SYSTEM_USER_ID`).

    The username-uniqueness check is scoped to this tenant's id, so a
    pre-existing ``admin`` user from before this function existed (e.g. the
    old single seeded, platform-scoped super_admin) does **not** block this
    tenant from getting its own ``admin`` — the legacy user's roles and
    ``tenant_id`` are left untouched, and a second, Default-tenant-scoped
    ``admin`` is created alongside it.

    Args:
        session: Database session used to read and insert the tenant and user.
    """
    tenant_stmt = select(Tenant).where(col(Tenant.name) == DEFAULT_TENANT_NAME).limit(1)
    tenant = (await session.exec(tenant_stmt)).first()
    if tenant is None:
        tenant = Tenant(
            display_name="Default",
            name=DEFAULT_TENANT_NAME,
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

    user_stmt = (
        select(User)
        .where(col(User.username) == "admin", col(User.tenant_id) == tenant_id)
        .limit(1)
    )
    if (await session.exec(user_stmt)).first() is not None:
        return
    password = resolve_seed_password(
        get_settings().admin_password, subject="'admin' user", env_var="ADMIN_PASSWORD"
    )
    admin = User(
        username="admin",
        first_name="Admin",
        last_name="User",
        password=hash_password(password),
        email="admin@example.com",
        enabled=True,
        email_verified=False,
        roles=[Role.admin.value],
        tenant_id=tenant_id,
        created_by=SYSTEM_USER_ID,
        updated_by=SYSTEM_USER_ID,
    )
    session.add(admin)
    await session.commit()
