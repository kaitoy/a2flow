"""Bootstrap helpers that seed required baseline records on application startup."""

import logging
import secrets

from pydantic import ValidationError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.password import hash_password
from infrastructure.secret_cipher import SecretCipher, get_secret_cipher
from models.mcp_ca import MCPCertificateAuthority
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

#: The groups of variables apply_system_settings_env_overrides applies, keyed
#: by the ``<PREFIX>_*`` its log lines name. Each maps a config.Settings
#: attribute to the SystemSettingsUpdate field it sets. A group is validated and
#: applied on its own, so a bad ``SMTP_PORT`` does not hold back the LLM, nor the
#: reverse.
_SYSTEM_SETTINGS_ENV_GROUPS: dict[str, dict[str, str]] = {
    "SMTP": {
        field: field
        for field in (
            "smtp_enabled",
            "smtp_host",
            "smtp_port",
            "smtp_security",
            "smtp_username",
            "smtp_password",
            "smtp_from_email",
            "smtp_from_name",
        )
    },
    "SYSTEM_DEFAULT_LLM": {
        "system_default_llm_model": "llm_model",
        "system_default_llm_api_key": "llm_api_key",
    },
}


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
    """Apply whichever ``SMTP_*`` and ``SYSTEM_DEFAULT_LLM_*`` env vars are set onto the settings row.

    Runs on every startup, not just the first: an operator may add or rotate
    a variable on a later deploy (e.g. changing ``SMTP_PASSWORD`` or
    ``SYSTEM_DEFAULT_LLM_API_KEY``), and that should reach the database
    without a manual admin-UI edit. The flip side is that a set variable wins
    over what was saved on the System Settings screen, at the next restart.
    Only fields whose environment variable is actually set are touched — this
    is built by constructing a real
    :class:`~models.system_settings.SystemSettingsUpdate` from just those
    fields, not ``model_construct`` (which would skip validation entirely),
    so pydantic's ``model_fields_set`` records exactly the env-sourced fields
    as "set", and
    :meth:`~services.system_settings.SystemSettingsService.update` /
    :meth:`~repositories.system_settings.SqlSystemSettingsRepository.update`'s
    ``exclude_unset=True`` handling — the same mechanism the admin UI's
    partial PATCH already relies on — leaves every other field, including
    anything configured by hand through the admin UI, untouched. The service
    encrypts ``SMTP_PASSWORD`` and ``SYSTEM_DEFAULT_LLM_API_KEY`` on the way
    in, exactly as for a screen save.

    ``SMTP_ENABLED`` is never inferred from the presence of the other
    ``SMTP_*`` variables; it must be set explicitly, matching the opt-in
    default the row itself is seeded with (see :func:`seed_system_settings`).
    The other SMTP fields, when set, are still applied even while
    ``SMTP_ENABLED`` is absent or false: :func:`services.system_settings._assert_usable`
    only requires a host and sender address once the *merged* ``smtp_enabled``
    ends up true, so staging a relay's host/username/password ahead of
    flipping the flag on is harmless — it lets "configure the relay" and
    "turn delivery on" ship as two separate deploys.

    The two groups (:data:`_SYSTEM_SETTINGS_ENV_GROUPS`) are applied one after
    the other, each on its own. A malformed value — a pydantic field-level
    failure (an out-of-range ``SMTP_PORT``, a malformed ``SMTP_FROM_EMAIL``, an
    unrecognized ``SMTP_SECURITY``, a model name over the length cap) or the
    service's business-rule check (e.g. ``SMTP_ENABLED=true`` with no
    ``SMTP_HOST``) — is logged as a ``WARNING`` (naming only the offending
    field(s), never their value, so a bad password or API key is never written
    to the log) and that group's apply is skipped: the row keeps whatever that
    group had, the other group is still applied, and startup continues
    normally.

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
    service = SystemSettingsService(
        SqlSystemSettingsRepository(session), get_secret_cipher()
    )
    for prefix, fields in _SYSTEM_SETTINGS_ENV_GROUPS.items():
        set_fields = {
            target: getattr(settings, source)
            for source, target in fields.items()
            if getattr(settings, source) is not None
        }
        if not set_fields:
            continue

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
                "Invalid %s_* environment configuration for "
                "field(s) %s; leaving the stored system settings unchanged. "
                "(Values are never logged here, including passwords and keys.)",
                prefix,
                bad_fields,
            )
            continue

        try:
            await service.update(update, user_id=SYSTEM_USER_ID)
        except SystemSettingsValidationError as exc:
            logger.warning(
                "%s_* environment configuration would leave the system settings "
                "unusable (%s); leaving the stored system settings unchanged.",
                prefix,
                exc.reason,
            )


#: Bytes of entropy for a generated seed password (used when ``ROOT_PASSWORD``
#: or ``ADMIN_PASSWORD`` is unset). ``token_urlsafe`` renders ~1.3 chars/byte,
#: so 16 bytes yields a ~22-character password: comfortably above the model's
#: 12-character minimum and short enough to copy out of a log line.
_GENERATED_PASSWORD_BYTES = 16

#: Name (slug) of the tenant seeded on first startup to hold the initial
#: ``admin`` user. Also the one tenant the demo dataset keeps its legacy ids
#: in and receives the ``DEMO_*`` credentials -- see
#: :mod:`infrastructure.demo_data`.
DEFAULT_TENANT_NAME = "default"


async def rotate_master_key(
    session: AsyncSession, cipher: SecretCipher | None = None
) -> int:
    """Re-encrypt every master-key ciphertext under the current master key.

    Runs only while ``SECRET_ENCRYPTION_KEY_FALLBACKS`` lists previous keys:
    the wrapped data key of every tenant, the SMTP password and LLM API key in
    system settings, and the MCP certificate authority's private key. A value
    already under the current key is left alone, so a restart before the
    fallbacks are removed rewrites nothing. A value no configured key decrypts
    is logged and left as it is -- it was unreadable already.

    Must run after the migrations, which create the columns it reads, and
    under the startup lock, since it reads and rewrites shared rows.

    Args:
        session: Database session used to read and rewrite the rows.
        cipher: The master cipher; defaults to the process-wide one.

    Returns:
        How many values were re-encrypted.
    """
    cipher = cipher or get_secret_cipher()
    if not cipher.has_fallbacks:
        return 0

    rotated = 0

    def rotate(row: object, field: str, label: str) -> None:
        nonlocal rotated
        value = getattr(row, field)
        if not value:
            return
        try:
            new = cipher.rotate(value)
        except ValueError:
            logger.error(
                "%s does not decrypt under the master key or any fallback; left "
                "as it is",
                label,
            )
            return
        if new is not None:
            setattr(row, field, new)
            session.add(row)
            rotated += 1

    for tenant in (await session.exec(select(Tenant))).all():
        rotate(tenant, "data_key", f"The data key of tenant {tenant.name}")
    settings = await session.get(SystemSettings, SYSTEM_SETTINGS_ID)
    if settings is not None:
        rotate(settings, "smtp_password", "The SMTP password")
        rotate(settings, "llm_api_key", "The platform LLM API key")
    for ca in (await session.exec(select(MCPCertificateAuthority))).all():
        rotate(ca, "private_key_encrypted", f"The key of certificate authority {ca.id}")
    await session.commit()
    logger.warning(
        "Master key rotation: re-encrypted %d value(s) under the current key. "
        "Once every replica runs with the new key, remove "
        "SECRET_ENCRYPTION_KEY_FALLBACKS.",
        rotated,
    )
    return rotated


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

    Shared by the seed functions below, so every bootstrap account follows the
    same configure-or-generate rule.

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
