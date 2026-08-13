"""Startup registration and removal of the optional demo dataset.

Gated by ``Settings.demo_data`` (the ``DEMO_DATA`` environment variable),
this module keeps a small, self-contained example of everything the
approval-gated "launch an EC2 instance" workflow needs, all inside the
seeded ``Default`` tenant (see :mod:`infrastructure.bootstrap`):

* one Secret holding the AWS access key id and secret access key as two
  entries,
* one stdio MCPServer reaching the managed AWS MCP Server through the
  ``mcp-proxy-for-aws`` proxy launched with ``uvx``, referencing those
  entries from its ``env`` via ``${secret:NAME/KEY}``,
* one AgentSkill pointing at ``sample_skills/aws-ec2-launch`` in this
  repository,
* three Users -- a ``demo-approver`` (the manager the skill asks for approval),
  a ``demo-requester`` (who runs the workflow), and a ``demo-developer`` (who
  may build and register the workflow, MCP server, and agent skill in the
  first place) -- each holding **no direct role at all**,
* three UserGroups -- ``Demo Approvers``, ``Demo Requesters``, and
  ``Demo Developers`` -- each granting one role and holding the matching user
  as its only member, so every demo account gets its role purely by
  inheritance. That makes the group feature visible in the demo dataset
  itself: remove a user from their group and their access disappears on the
  next request.

The Workflow itself is deliberately *not* seeded — these records are the
ingredients an operator assembles one into.

The flag is declarative in both directions: ``DEMO_DATA=true`` guarantees the
records exist, and leaving it unset (the default) guarantees they do not, so
turning the option off and restarting removes whatever a previous run
registered. Every record is identified by a fixed id constant rather than by
name, which makes both directions exact and idempotent no matter how the rows
were renamed in the admin UI in between.

Rows are built as table models directly, not through the ``...Create``
validation models the API uses. That is deliberate: ``AgentSkillCreate``'s
``repo_url`` runs an SSRF check that resolves the host over DNS, which would
make application startup depend on working name resolution.
"""

import logging
from dataclasses import dataclass
from typing import TypeVar

from sqlalchemy.exc import IntegrityError
from sqlmodel import SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.bootstrap import DEFAULT_TENANT_NAME, resolve_seed_password
from infrastructure.password import hash_password
from infrastructure.secret_cipher import get_secret_cipher
from models.agent_skill import AgentSkill
from models.mcp_server import McpCommand, MCPServer, McpTransport
from models.secret import Secret, SecretType
from models.tenant import Tenant
from models.user import SYSTEM_USER_ID, Role, User
from models.user_group import UserGroup, UserGroupMember
from repositories.user import SqlUserRepository

logger = logging.getLogger(__name__)

#: Fixed identifier of the demo ``approver`` user (the manager the sample
#: skill requests approval from).
DEMO_APPROVER_USER_ID = "00000000-0000-0000-0000-00000000d001"

#: Fixed identifier of the demo ``requester`` user (who executes the workflow).
DEMO_REQUESTER_USER_ID = "00000000-0000-0000-0000-00000000d002"

#: Fixed identifier of the demo ``developer`` user (who builds and registers
#: the workflow, MCP server, and agent skill).
DEMO_DEVELOPER_USER_ID = "00000000-0000-0000-0000-00000000d003"

#: Fixed identifier of the demo ``Demo Approvers`` user group.
DEMO_APPROVERS_GROUP_ID = "00000000-0000-0000-0000-00000000d401"

#: Fixed identifier of the demo ``Demo Requesters`` user group.
DEMO_REQUESTERS_GROUP_ID = "00000000-0000-0000-0000-00000000d402"

#: Fixed identifier of the demo ``Demo Developers`` user group.
DEMO_DEVELOPERS_GROUP_ID = "00000000-0000-0000-0000-00000000d403"

#: Fixed identifier of the demo Secret holding the AWS credentials.
DEMO_AWS_SECRET_ID = "00000000-0000-0000-0000-00000000d101"

#: Fixed identifier of the demo AWS MCP server.
DEMO_MCP_SERVER_ID = "00000000-0000-0000-0000-00000000d201"

#: Fixed identifier of the demo ``aws-ec2-launch`` agent skill.
DEMO_AGENT_SKILL_ID = "00000000-0000-0000-0000-00000000d301"

#: Name of the demo Secret holding both AWS credentials. Its two entries are
#: embedded in the demo MCP server's ``env`` as ``${secret:NAME/KEY}``
#: placeholders.
DEMO_AWS_SECRET_NAME = "demo-aws-credentials"

#: Entry key of the AWS access key id within :data:`DEMO_AWS_SECRET_NAME`.
DEMO_ACCESS_KEY_ENTRY_KEY = "AWS_ACCESS_KEY_ID"

#: Entry key of the AWS secret access key within :data:`DEMO_AWS_SECRET_NAME`.
DEMO_SECRET_KEY_ENTRY_KEY = "AWS_SECRET_ACCESS_KEY"

#: Name of the demo MCP server as shown in the admin UI.
DEMO_MCP_SERVER_NAME = "AWS MCP Server"

#: Name of the demo agent skill as shown in the admin UI.
DEMO_AGENT_SKILL_NAME = "Demo AWS EC2 Launch"

#: Proxy package the demo MCP server is launched from. Pinned to an exact
#: version rather than ``@latest``, which is what the upstream migration guide
#: recommends.
_DEMO_MCP_PROXY_PACKAGE = "mcp-proxy-for-aws@1.6.4"

#: Managed AWS MCP Server endpoint the proxy forwards SigV4-signed requests to.
#: It replaces the deprecated self-hosted ``awslabs.aws-api-mcp-server``.
_DEMO_MCP_ENDPOINT = "https://aws-mcp.us-east-1.api.aws/mcp"

#: Region :data:`_DEMO_MCP_ENDPOINT` lives in, and therefore the region the
#: proxy must sign for. Deliberately independent of ``DEMO_AWS_REGION``, which
#: selects the region the *tools* operate on: the proxy does not derive the
#: signing region from the endpoint URL, it falls back to ``AWS_REGION``, so
#: leaving it implicit would break signing as soon as the two differ.
_DEMO_MCP_ENDPOINT_REGION = "us-east-1"

#: Repository the demo agent skill is cloned from, and the path within it.
_DEMO_SKILL_REPO_URL = "https://github.com/kaitoy/a2flow"
_DEMO_SKILL_REPO_PATH = "sample_skills/aws-ec2-launch"

#: Stored in place of an AWS credential when ``DEMO_AWS_ACCESS_KEY_ID`` /
#: ``DEMO_AWS_SECRET_ACCESS_KEY`` are unset. The demo is then complete in shape
#: but cannot reach AWS until an operator edits the secret in the admin UI.
_PLACEHOLDER_SECRET_VALUE = "REPLACE_ME"

_RowT = TypeVar("_RowT", bound=SQLModel)


@dataclass(frozen=True)
class _DemoUserSpec:
    """The fixed identity of one demo user, minus its password.

    Carries no role: every demo account is granted its role through the
    matching :class:`_DemoGroupSpec` instead.

    Attributes:
        id: Fixed primary key, so the user can be found again for removal.
        username: Login name, unique within the ``Default`` tenant.
        first_name: Given name shown in the UI.
        last_name: Family name shown in the UI.
    """

    id: str
    username: str
    first_name: str
    last_name: str


@dataclass(frozen=True)
class _DemoGroupSpec:
    """One demo user group: a single role granted to a single member.

    Attributes:
        id: Fixed primary key, so the group can be found again for removal.
        name: Group name shown in the admin UI, unique within the tenant.
        description: Sentence shown on the group list and detail pages.
        role: The one role this group grants to its members.
        member_id: Id of the demo user placed in the group.
    """

    id: str
    name: str
    description: str
    role: Role
    member_id: str


#: The demo accounts, in creation order. Each is created with an empty
#: ``roles`` list and gets its role from :data:`_DEMO_GROUPS`.
_DEMO_USERS = (
    _DemoUserSpec(
        id=DEMO_APPROVER_USER_ID,
        username="demo-approver",
        first_name="Demo",
        last_name="Approver",
    ),
    _DemoUserSpec(
        id=DEMO_REQUESTER_USER_ID,
        username="demo-requester",
        first_name="Demo",
        last_name="Requester",
    ),
    _DemoUserSpec(
        id=DEMO_DEVELOPER_USER_ID,
        username="demo-developer",
        first_name="Demo",
        last_name="Developer",
    ),
)

#: The demo user groups, one per demo account. The sample skill looks for a
#: user holding ``approver`` to route its approval request to; ``requester`` is
#: the role that may execute a workflow; ``developer`` is the role that may
#: build and register a workflow, MCP server, or agent skill. Granting each
#: through a group rather than directly is what makes the demo exercise role
#: inheritance.
_DEMO_GROUPS = (
    _DemoGroupSpec(
        id=DEMO_APPROVERS_GROUP_ID,
        name="Demo Approvers",
        description="Managers who can be designated as workflow approvers.",
        role=Role.approver,
        member_id=DEMO_APPROVER_USER_ID,
    ),
    _DemoGroupSpec(
        id=DEMO_REQUESTERS_GROUP_ID,
        name="Demo Requesters",
        description="People who can run published workflows.",
        role=Role.requester,
        member_id=DEMO_REQUESTER_USER_ID,
    ),
    _DemoGroupSpec(
        id=DEMO_DEVELOPERS_GROUP_ID,
        name="Demo Developers",
        description="People who can build workflows, MCP servers, and agent skills.",
        role=Role.developer,
        member_id=DEMO_DEVELOPER_USER_ID,
    ),
)


async def sync_demo_data(session: AsyncSession) -> str | None:
    """Register or remove the demo dataset according to ``DEMO_DATA``.

    Must run **after** :func:`infrastructure.bootstrap.seed_root_user` and
    :func:`infrastructure.bootstrap.seed_default_tenant_and_admin_user`: the
    demo accounts are real (non-system) users, so seeding them first would
    make ``seed_root_user``'s "any real user exists" skip check wrongly fire,
    and the ``Default`` tenant these records hang off has to exist already.

    Args:
        session: Database session used to read, insert, and delete records.

    Returns:
        The id of a freshly registered demo AgentSkill, whose repository has
        not been cloned yet and whose sync the caller should schedule; or
        ``None`` when the skill already existed, could not be registered, or
        the demo data was removed instead.
    """
    if get_settings().demo_data:
        return await _seed_demo_data(session)
    await _remove_demo_data(session)
    return None


async def _seed_demo_data(session: AsyncSession) -> str | None:
    """Create every missing demo record in the seeded ``Default`` tenant.

    Args:
        session: Database session used to read and insert records.

    Returns:
        The id of the AgentSkill if this call created it, else ``None``.
    """
    tenant_id = await _default_tenant_id(session)
    if tenant_id is None:
        logger.warning(
            "DEMO_DATA is enabled but the seeded '%s' tenant does not exist; "
            "skipping demo data.",
            DEFAULT_TENANT_NAME,
        )
        return None
    await _seed_demo_users(session, tenant_id)
    await _seed_demo_groups(session, tenant_id)
    await _seed_demo_secrets(session, tenant_id)
    await _seed_demo_mcp_server(session, tenant_id)
    return await _seed_demo_agent_skill(session, tenant_id)


async def _remove_demo_data(session: AsyncSession) -> None:
    """Delete every demo record that is still present.

    Deletion follows the direction of the foreign keys — agent skill, then MCP
    server, then secrets, then user groups, then users — so a record is never
    orphaned by the removal of something it points at. A record that other data
    has come to depend on (a Workflow built on the demo skill, a task tool
    binding on the demo MCP server) cannot be deleted; that is logged and
    skipped rather than allowed to fail startup.

    Groups go before their members: the membership rows cascade away with the
    group, so the users are then free of them and the roles they granted are
    gone from the accounts' effective roles immediately. Nothing has to be
    recomputed, since inherited roles are never stored on the user.

    Args:
        session: Database session used to read and delete records.
    """
    await _delete_demo_row(
        session, AgentSkill, DEMO_AGENT_SKILL_ID, label="agent skill"
    )
    await _delete_demo_row(session, MCPServer, DEMO_MCP_SERVER_ID, label="MCP server")
    await _delete_demo_row(
        session, Secret, DEMO_AWS_SECRET_ID, label="AWS credentials secret"
    )
    for group_spec in _DEMO_GROUPS:
        await _delete_demo_row(
            session, UserGroup, group_spec.id, label=f"user group {group_spec.name!r}"
        )
    for spec in _DEMO_USERS:
        await _delete_demo_user(session, spec.id)


async def _default_tenant_id(session: AsyncSession) -> str | None:
    """Return the id of the seeded ``Default`` tenant, or ``None`` if absent.

    Args:
        session: Database session used to read the tenant.

    Returns:
        The tenant's id, or ``None`` when it has not been seeded.
    """
    stmt = select(Tenant).where(col(Tenant.name) == DEFAULT_TENANT_NAME).limit(1)
    tenant = (await session.exec(stmt)).first()
    return None if tenant is None else tenant.id


async def _insert(session: AsyncSession, row: SQLModel, *, label: str) -> bool:
    """Insert one demo row, skipping it when it collides with existing data.

    The demo names (``demo-approver``, ``AWS MCP Server``, ...) are not reserved,
    so an operator may already have a record of their own under one of them.
    The per-tenant unique constraint catches that; the collision is reported
    and the remaining demo records are still registered, rather than the
    ``IntegrityError`` propagating out of the startup hook.

    Args:
        session: Database session used to insert the row.
        row: The fully populated table model to persist.
        label: Human-readable description of the row used in the log message.

    Returns:
        ``True`` when the row was inserted, ``False`` when it was skipped.
    """
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.warning(
            "Skipped registering the demo %s: it conflicts with an existing "
            "record (most likely one of the same name).",
            label,
        )
        return False
    return True


async def _delete_demo_row(
    session: AsyncSession, model: type[_RowT], row_id: str, *, label: str
) -> None:
    """Delete one demo row by id, tolerating both absence and references.

    Args:
        session: Database session used to read and delete the row.
        model: Table model class the row belongs to.
        row_id: Fixed identifier of the demo row.
        label: Human-readable description of the row used in the log message.
    """
    row = await session.get(model, row_id)
    if row is None:
        return
    try:
        await session.delete(row)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.warning(
            "Could not remove the demo %s: other records still reference it. "
            "Delete those first, then restart, or remove it in the admin UI.",
            label,
        )


async def _seed_demo_users(session: AsyncSession, tenant_id: str) -> None:
    """Create the demo approver and requester, reviving them if soft-deleted.

    The shared password is resolved only when at least one account is actually
    missing, so a restart with everything already in place never generates —
    and logs — a password nobody will use.

    A previous removal may have left an account *soft*-deleted rather than
    gone (see :meth:`repositories.user.SqlUserRepository.delete`), because it
    was still referenced through ``created_by`` / ``updated_by``. Re-enabling
    the demo data revives such an account instead of leaving it disabled.

    Args:
        session: Database session used to read, insert, and update users.
        tenant_id: Id of the ``Default`` tenant the accounts belong to.
    """
    missing: list[_DemoUserSpec] = []
    for spec in _DEMO_USERS:
        existing = await session.get(User, spec.id)
        if existing is None:
            missing.append(spec)
        else:
            await _revive_demo_user(session, existing)
    if not missing:
        return
    password = resolve_seed_password(
        get_settings().demo_password, subject="demo users", env_var="DEMO_PASSWORD"
    )
    for spec in missing:
        await _insert(
            session,
            User(
                id=spec.id,
                username=spec.username,
                first_name=spec.first_name,
                last_name=spec.last_name,
                password=hash_password(password),
                email=f"{spec.username}@example.com",
                enabled=True,
                email_verified=False,
                # No direct roles: every demo account inherits its role from
                # the matching group seeded by _seed_demo_groups.
                roles=[],
                tenant_id=tenant_id,
                created_by=SYSTEM_USER_ID,
                updated_by=SYSTEM_USER_ID,
            ),
            label=f"user '{spec.username}'",
        )


async def _revive_demo_user(session: AsyncSession, user: User) -> None:
    """Normalize an existing demo user back to this module's declared shape.

    Clears a soft delete, re-enables the account, and — for a database seeded
    by an older version of this module, which granted each demo account its
    role directly — strips the direct roles so the account gets them from its
    group instead. Without that last step, upgrading with ``DEMO_DATA`` left
    enabled would leave the role granted twice over, and removing a user from
    their demo group would visibly fail to revoke anything.

    Args:
        session: Database session used to update the user.
        user: The existing demo user row.
    """
    if user.deleted_at is None and user.enabled and not user.roles:
        return
    user.deleted_at = None
    user.enabled = True
    user.roles = []
    user.updated_by = SYSTEM_USER_ID
    session.add(user)
    await session.commit()


async def _delete_demo_user(session: AsyncSession, user_id: str) -> None:
    """Delete one demo user, falling back to a soft delete when referenced.

    Goes through :class:`repositories.user.SqlUserRepository` rather than
    deleting the row here, to reuse its hard-delete-then-soft-delete fallback:
    a demo user that has signed in and created records cannot be removed
    outright, and must keep resolving as a name on those records.

    Args:
        session: Database session used to read and delete the user.
        user_id: Fixed identifier of the demo user.
    """
    if await session.get(User, user_id) is None:
        return
    await SqlUserRepository(session).delete(user_id)


async def _seed_demo_groups(session: AsyncSession, tenant_id: str) -> None:
    """Create the demo user groups and place each demo account in its own.

    Must run after :func:`_seed_demo_users`: the membership rows reference
    ``users.id``. A group whose row already exists is left alone, but its
    membership is re-asserted, so a member removed by hand in the admin UI
    comes back on the next restart — matching this module's declarative
    contract for every other record.

    Nothing needs recomputing afterwards: a member's inherited roles are
    resolved from these rows on every request rather than stored on the user.

    Args:
        session: Database session used to read and insert groups and members.
        tenant_id: Id of the ``Default`` tenant the groups belong to.
    """
    for spec in _DEMO_GROUPS:
        if await session.get(UserGroup, spec.id) is None:
            await _insert(
                session,
                UserGroup(
                    id=spec.id,
                    tenant_id=tenant_id,
                    name=spec.name,
                    description=spec.description,
                    roles=[spec.role.value],
                    created_by=SYSTEM_USER_ID,
                    updated_by=SYSTEM_USER_ID,
                ),
                label=f"user group '{spec.name}'",
            )
        if await session.get(UserGroup, spec.id) is None:
            # The insert collided with an operator's own group of that name;
            # there is nothing to attach a membership to.
            continue
        if await session.get(UserGroupMember, (spec.id, spec.member_id)) is None:
            await _insert(
                session,
                UserGroupMember(group_id=spec.id, user_id=spec.member_id),
                label=f"membership of user group '{spec.name}'",
            )


async def _seed_demo_secrets(session: AsyncSession, tenant_id: str) -> None:
    """Create the demo AWS credentials secret.

    Both credentials live in a single secret as two entries, the way a Vault KV
    path holds several keys. Values come from ``DEMO_AWS_ACCESS_KEY_ID`` /
    ``DEMO_AWS_SECRET_ACCESS_KEY`` when set, so a fully working demo is one
    restart away, and fall back to a placeholder otherwise. They are stored as
    Fernet ciphertext, the same as any secret created through the API — the
    encryption lives in the service layer, which this out-of-request caller
    cannot use, so the cipher is applied directly here.

    Args:
        session: Database session used to read and insert secrets.
        tenant_id: Id of the ``Default`` tenant the secret belongs to.
    """
    if await session.get(Secret, DEMO_AWS_SECRET_ID) is not None:
        return
    settings = get_settings()
    cipher = get_secret_cipher()
    await _insert(
        session,
        Secret(
            id=DEMO_AWS_SECRET_ID,
            tenant_id=tenant_id,
            name=DEMO_AWS_SECRET_NAME,
            type=SecretType.local,
            entries={
                DEMO_ACCESS_KEY_ENTRY_KEY: cipher.encrypt(
                    settings.demo_aws_access_key_id or _PLACEHOLDER_SECRET_VALUE
                ),
                DEMO_SECRET_KEY_ENTRY_KEY: cipher.encrypt(
                    settings.demo_aws_secret_access_key or _PLACEHOLDER_SECRET_VALUE
                ),
            },
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        ),
        label=f"secret '{DEMO_AWS_SECRET_NAME}'",
    )


async def _seed_demo_mcp_server(session: AsyncSession, tenant_id: str) -> None:
    """Create the demo AWS MCP server.

    The AWS MCP Server is a managed remote endpoint rather than something to
    self-host, so the row is registered as a ``stdio`` server launching the
    ``mcp-proxy-for-aws`` bridge with ``uvx``, which the backend image already
    provides. The proxy signs every request to :data:`_DEMO_MCP_ENDPOINT` with
    SigV4 using the AWS credentials it finds in its environment; those are
    ``${secret:NAME/KEY}`` placeholders resolved at connection time by
    :class:`infrastructure.secret_resolver.SecretResolver`, so the plaintext
    never lands in the ``mcp_servers`` row.

    ``DEMO_AWS_REGION`` is carried in this row's own ``env`` (as
    ``AWS_REGION``) and referenced from ``args`` via ``${env:AWS_REGION}`` —
    the remote server reads that metadata value to pick the region its tools
    act on — kept apart from ``--region``, which only governs the signature
    and is not configurable through ``env``.

    Args:
        session: Database session used to read and insert the server.
        tenant_id: Id of the ``Default`` tenant the server belongs to.
    """
    if await session.get(MCPServer, DEMO_MCP_SERVER_ID) is not None:
        return
    settings = get_settings()
    await _insert(
        session,
        MCPServer(
            id=DEMO_MCP_SERVER_ID,
            tenant_id=tenant_id,
            name=DEMO_MCP_SERVER_NAME,
            transport=McpTransport.stdio,
            command=McpCommand.uvx,
            args=[
                _DEMO_MCP_PROXY_PACKAGE,
                _DEMO_MCP_ENDPOINT,
                "--region",
                _DEMO_MCP_ENDPOINT_REGION,
                "--metadata",
                "AWS_REGION=${env:AWS_REGION}",
            ],
            headers={},
            env={
                "AWS_ACCESS_KEY_ID": (
                    f"${{secret:{DEMO_AWS_SECRET_NAME}/{DEMO_ACCESS_KEY_ENTRY_KEY}}}"
                ),
                "AWS_SECRET_ACCESS_KEY": (
                    f"${{secret:{DEMO_AWS_SECRET_NAME}/{DEMO_SECRET_KEY_ENTRY_KEY}}}"
                ),
                "AWS_REGION": settings.demo_aws_region,
            },
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        ),
        label=f"MCP server '{DEMO_MCP_SERVER_NAME}'",
    )


async def _seed_demo_agent_skill(session: AsyncSession, tenant_id: str) -> str | None:
    """Create the demo agent skill pointing at this repository's sample skill.

    The repository is public, so no ``repo_auth_password`` is needed. The row is
    left ``pending``: cloning is the caller's job, since it is a network
    operation that must not block application startup.

    Args:
        session: Database session used to read and insert the skill.
        tenant_id: Id of the ``Default`` tenant the skill belongs to.

    Returns:
        The skill's id when this call created it, else ``None``.
    """
    if await session.get(AgentSkill, DEMO_AGENT_SKILL_ID) is not None:
        return None
    created = await _insert(
        session,
        AgentSkill(
            id=DEMO_AGENT_SKILL_ID,
            tenant_id=tenant_id,
            name=DEMO_AGENT_SKILL_NAME,
            repo_url=_DEMO_SKILL_REPO_URL,
            repo_path=_DEMO_SKILL_REPO_PATH,
            description=(
                "Launch an AWS EC2 instance through a registered MCP tool, "
                "gated by a manager's explicit approval."
            ),
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        ),
        label=f"agent skill '{DEMO_AGENT_SKILL_NAME}'",
    )
    return DEMO_AGENT_SKILL_ID if created else None
