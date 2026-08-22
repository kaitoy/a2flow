"""A2Flow's own gateway to the MCP servers a tenant has registered.

Every call the agent makes to a user-registered MCP server passes through
:class:`McpProxy`. The proxy owns the three things the ADK tool functions in
:mod:`infrastructure.mcp_tools` used to each own a copy of:

1. **Authentication** -- turning the caller's claimed :class:`McpPrincipal`
   into a verified :class:`McpIdentity` (which tenant, which run). Pluggable
   through the :class:`McpAuthenticator` protocol.
2. **Authorization** -- a chain of :class:`McpPolicy` objects consulted before
   every operation, each of which may veto by raising
   :class:`McpPolicyDeniedError`.
3. **Credential injection** -- expanding the registered server's
   ``${secret:NAME/KEY}`` placeholders into a connection spec.

The transport itself still belongs to :mod:`infrastructure.mcp_client`, which
this module calls and never bypasses.

Why a layer at all: the two hooks above are the seams a real security layer
lands in later. Today the authenticator is a pass-through (the caller is a run
this very process is driving, so there is no channel to forge a session id
over) and exactly one policy is registered.

**Shaped for a future HTTP lift.** Every value this module's public surface
accepts or returns is a plain, serializable value object or an MCP wire type --
no ``ToolContext``, no ``AsyncSession``, no ORM row. Re-exposing the proxy as
an MCP/HTTP endpoint therefore means parsing a request body into
:class:`CallToolRequest` and replacing the body of
:meth:`McpAuthenticator.authenticate`; nothing downstream changes. That is also
when :class:`McpProxyError` earns rows in ``routers/exception_handlers.py``
(``McpPolicyDeniedError`` -> 403, ``McpServerUnknownError`` -> 404, the rest ->
502).

Note for tests: :func:`get_mcp_proxy` is ``lru_cache``d, so a test that needs a
different policy chain must construct :class:`McpProxy` directly or call
``get_mcp_proxy.cache_clear()``.
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from typing import Any, Protocol

from mcp import types
from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure import database, mcp_client
from infrastructure.mcp_client import McpConnection
from infrastructure.secret_cipher import get_secret_cipher
from infrastructure.secret_resolver import SecretResolver
from infrastructure.vault_client import get_vault_client
from models.mcp_server import MCPServer
from repositories.exceptions import McpConnectionError, SecretResolutionError
from repositories.mcp_server import SqlMCPServerRepository
from repositories.secret import SqlSecretRepository
from repositories.tenant_bootstrap import (
    resolve_agent_run_tenant,
    resolve_workflow_execution_tenant,
)

logger = logging.getLogger(__name__)

#: Message returned when ``call_tool``'s caller maps to no WorkflowExecution.
NO_SESSION = "no workflow execution is bound to the current run; cannot use MCP tools"

#: Message returned when ``list_tools``'s caller maps to no tenant at all.
NO_TENANT = (
    "the current run is not bound to a workflow or design session; "
    "cannot list MCP tools"
)

#: Upper bound on how many registered servers one listing queries.
_MAX_SERVERS = 1000


class PrincipalKind(StrEnum):
    """How the caller identified itself to the proxy."""

    agent_run = "agent_run"


class McpOperation(StrEnum):
    """Which proxied MCP operation a policy is being consulted about."""

    list_tools = "list_tools"
    call_tool = "call_tool"


@dataclass(frozen=True)
class McpPrincipal:
    """The caller's *claimed* identity, as the caller knows itself.

    Deliberately unverified: this is what an HTTP request body or header would
    carry. :meth:`McpAuthenticator.authenticate` turns it into an
    :class:`McpIdentity`.

    Attributes:
        kind: What sort of caller this is.
        session_id: The ADK session id of the run making the call, which is
            also the AG-UI thread id. Empty when the caller could not determine
            one.
        user_id: The acting user, when the caller knows it.
    """

    kind: PrincipalKind
    session_id: str
    user_id: str | None = None


@dataclass(frozen=True)
class McpIdentity:
    """The caller after authentication: which tenant, which run, which user.

    Attributes:
        tenant_id: The tenant whose MCP registry the caller may reach.
        execution_id: The WorkflowExecution driving the run, or ``None`` when
            the run is a workflow *design* session (which may list tools but
            has no tasks to invoke them from).
        user_id: The acting user, carried through from the principal.
    """

    tenant_id: str
    execution_id: str | None
    user_id: str | None = None


@dataclass(frozen=True)
class ListToolsRequest:
    """A proxied ``tools/list`` across the caller's whole tenant registry.

    Attributes:
        principal: The caller's claimed identity.
    """

    principal: McpPrincipal


@dataclass(frozen=True)
class CallToolRequest:
    """A proxied ``tools/call`` against one registered server.

    Attributes:
        principal: The caller's claimed identity.
        server_id: Id of the registered MCP server to call.
        tool_name: Name of the tool on that server.
        arguments: Arguments matching the tool's input schema.
    """

    principal: McpPrincipal
    server_id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class McpCallContext:
    """One proxied operation, fully described, for the policy layer.

    Holds everything a policy could need and no live handles (no session, no
    connection), so it stays the exact value an HTTP handler would rebuild from
    a request body.

    Attributes:
        operation: Which proxied operation is being attempted.
        principal: The caller's claimed identity.
        identity: The caller's verified identity.
        server_id: The target server, or ``None`` for a registry-wide listing.
        server_name: The target server's name. Filled for a listing entry, but
            ``None`` while authorizing a call: the row is deliberately loaded
            only after the policy chain allows the call (see
            :meth:`McpProxy.call_tool`).
        tool_name: The target tool, or ``None`` for a listing.
        arguments: The call's arguments, or ``None`` for a listing.
    """

    operation: McpOperation
    principal: McpPrincipal
    identity: McpIdentity
    server_id: str | None = None
    server_name: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None


@dataclass(frozen=True)
class ServerToolListing:
    """One registered server's contribution to a proxied listing.

    Carries either ``tools`` or ``error``: a listing isolates per-server
    failures rather than failing whole, so partial failure is an ordinary
    result here, not an exception.

    Attributes:
        server_id: Id of the registered server.
        server_name: Name of the registered server.
        tools: The tools it advertises; empty when ``error`` is set.
        error: Why this server could not be queried, or ``None`` on success.
    """

    server_id: str
    server_name: str
    tools: list[types.Tool] = field(default_factory=list)
    error: str | None = None


class McpProxyError(Exception):
    """Base for every failure the proxy attributes to the caller or the target.

    ``message`` is safe to return to the caller verbatim. Raw underlying
    reasons are logged by the proxy and reachable through ``__cause__``; they
    are never folded into ``message`` beyond what the agent-facing contract
    already exposed.
    """

    def __init__(self, message: str) -> None:
        """Initialize the error.

        Args:
            message: Caller-safe explanation of the failure.
        """
        self.message = message
        super().__init__(message)


class McpAuthenticationError(McpProxyError):
    """Raised when a principal cannot be verified or maps to no known run."""


class McpPolicyDeniedError(McpProxyError):
    """Raised by a policy to veto an operation."""


class McpServerUnknownError(McpProxyError):
    """Raised when the target server is not registered in the caller's tenant."""


class McpServerUnusableError(McpProxyError):
    """Raised when a registered server's connection spec cannot be built."""


class McpUpstreamError(McpProxyError):
    """Raised when the target server cannot be reached, launched, or times out."""


class McpAuthenticator(Protocol):
    """Turns a caller's claimed :class:`McpPrincipal` into a verified identity."""

    async def authenticate(
        self, principal: McpPrincipal, db: AsyncSession
    ) -> McpIdentity:
        """Verify the principal and resolve the run it belongs to.

        Args:
            principal: The caller's claimed identity.
            db: The proxy's open database session. Valid only for the duration
                of this call; do not retain it.

        Returns:
            The verified identity.

        Raises:
            McpAuthenticationError: If the principal cannot be verified or maps
                to no known tenant.
        """
        ...


class AgentRunAuthenticator:
    """Pass-through authenticator for agent runs driven by this process.

    ``principal.session_id`` is trusted without verification because it comes
    from the ADK ``ToolContext`` of a run this very process is driving -- there
    is no channel to forge it over. All this class does is resolve that id to a
    tenant (and, when the run is an execution rather than a design session, to a
    WorkflowExecution) through :mod:`repositories.tenant_bootstrap`.

    This is the seam the real security layer lands in: when the proxy is lifted
    to an MCP/HTTP endpoint, the bearer-token or mTLS check replaces the body of
    :meth:`authenticate` and nothing downstream changes.
    """

    async def authenticate(
        self, principal: McpPrincipal, db: AsyncSession
    ) -> McpIdentity:
        """Resolve the run behind ``principal.session_id`` to a tenant.

        An execution run is tried first, since one query yields both the
        WorkflowExecution id and the tenant. A design session resolves to a
        tenant with no execution id, which is what keeps tool *listing*
        available during design while tool *invocation* is not.

        Args:
            principal: The caller's claimed identity.
            db: The proxy's open database session.

        Returns:
            The verified identity.

        Raises:
            McpAuthenticationError: If the session id is empty or matches
                neither a WorkflowExecution nor a Workflow.
        """
        if not principal.session_id:
            raise McpAuthenticationError("no session is bound to the current run")
        resolved = await resolve_workflow_execution_tenant(db, principal.session_id)
        if resolved is not None:
            execution_id, tenant_id = resolved
            return McpIdentity(
                tenant_id=tenant_id,
                execution_id=execution_id,
                user_id=principal.user_id,
            )
        design_tenant_id = await resolve_agent_run_tenant(db, principal.session_id)
        if design_tenant_id is None:
            raise McpAuthenticationError("the session maps to no known tenant")
        return McpIdentity(
            tenant_id=design_tenant_id, execution_id=None, user_id=principal.user_id
        )


class McpPolicy(Protocol):
    """A decision point consulted before every operation the proxy performs.

    Implementations veto by raising :class:`McpPolicyDeniedError` and allow by
    returning. They must not mutate the context, perform the call, or swallow
    another policy's denial. Every registered policy is consulted in
    registration order and the first denial short-circuits the chain, so an
    expensive check should be registered after a cheap one.

    There is one method rather than one per operation so that a policy author
    cannot accidentally guard only half the surface: skipping an operation is an
    explicit early ``return`` they have to write.
    """

    async def authorize(self, ctx: McpCallContext, db: AsyncSession) -> None:
        """Allow the operation, or raise :class:`McpPolicyDeniedError`.

        Args:
            ctx: The operation being attempted, with the caller already
                authenticated.
            db: The proxy's open session, for policies that must query. Valid
                only for the duration of this call; do not retain it.

        Raises:
            McpPolicyDeniedError: To refuse the operation. Its ``message`` is
                shown to the caller, so it must be safe to disclose.
        """
        ...


@asynccontextmanager
async def _default_session() -> AsyncIterator[AsyncSession]:
    """Open a database session on the module-level engine.

    The engine is referenced through the ``database`` module so tests can
    monkeypatch ``database.engine``.

    Yields:
        A fresh ``AsyncSession``.
    """
    async with AsyncSession(database.engine) as db:
        yield db


def _with_error(base: ServerToolListing, error: str) -> ServerToolListing:
    """Return a copy of a listing entry carrying an error instead of tools.

    Args:
        base: The entry identifying the server.
        error: Why the server could not be queried.

    Returns:
        A new entry with ``error`` set.
    """
    return ServerToolListing(
        server_id=base.server_id, server_name=base.server_name, error=error
    )


class McpProxy:
    """Single gateway through which callers reach registered MCP servers.

    The database session is opened by the proxy and **closed before any network
    or subprocess call**: a stdio server spawn can hold the caller for two
    minutes, which must not pin a database connection for the duration. A
    policy's ``db`` is therefore valid only while its ``authorize`` runs.
    """

    def __init__(
        self,
        *,
        authenticator: McpAuthenticator | None = None,
        policies: Sequence[McpPolicy] | None = None,
        session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]]
        | None = None,
    ) -> None:
        """Initialize the proxy.

        Args:
            authenticator: Verifies callers. Defaults to
                :class:`AgentRunAuthenticator`.
            policies: The authorization chain, consulted in order. Defaults to
                an empty chain, which allows everything -- the process-wide
                proxy built by :func:`get_mcp_proxy` passes
                :func:`infrastructure.mcp_policies.default_policies` instead.
            session_factory: Opens the database session each operation runs
                against. Defaults to a session on the module-level engine.
        """
        self._authenticator: McpAuthenticator = authenticator or AgentRunAuthenticator()
        self._policies: tuple[McpPolicy, ...] = tuple(policies or ())
        self._session_factory = session_factory or _default_session

    async def list_tools(self, request: ListToolsRequest) -> list[ServerToolListing]:
        """Return the tools advertised by every server registered in the tenant.

        Each server is queried live and concurrently; one that cannot be reached
        is reported through its entry's ``error`` field instead of failing the
        whole listing.

        Args:
            request: The listing request.

        Returns:
            One :class:`ServerToolListing` per registered server, in
            registration order. An empty registry yields an empty list.

        Raises:
            McpAuthenticationError: If the caller maps to no tenant.
            McpPolicyDeniedError: If a policy vetoes the listing.
        """
        prepared: list[tuple[ServerToolListing, McpConnection | None]] = []
        async with self._session_factory() as db:
            identity = await self._authenticate(db, request.principal, NO_TENANT)
            servers = await SqlMCPServerRepository(
                db, tenant_id=identity.tenant_id
            ).list(limit=_MAX_SERVERS, offset=0)
            resolver = self._build_resolver(db, identity.tenant_id)
            for server in servers:
                await self._authorize(
                    McpCallContext(
                        operation=McpOperation.list_tools,
                        principal=request.principal,
                        identity=identity,
                        server_id=server.id,
                        server_name=server.name,
                    ),
                    db,
                )
                base = ServerToolListing(server_id=server.id, server_name=server.name)
                try:
                    connection = await self._resolve_connection(
                        server, resolver, operation=McpOperation.list_tools
                    )
                except McpServerUnusableError as exc:
                    prepared.append((_with_error(base, exc.message), None))
                    continue
                prepared.append((base, connection))
        # The session is closed: the fan-out below reaches the network and may
        # spawn child processes.
        return list(await asyncio.gather(*(self._query(*p) for p in prepared)))

    async def call_tool(self, request: CallToolRequest) -> types.CallToolResult:
        """Invoke one tool on one registered server.

        Tool-level failures are *not* raised: they come back inside the returned
        result with ``isError`` set, so the caller can relay them verbatim. Only
        proxy-level failures raise.

        Args:
            request: The call request.

        Returns:
            The raw ``tools/call`` result.

        Raises:
            McpAuthenticationError: If the caller maps to no WorkflowExecution.
            McpPolicyDeniedError: If a policy vetoes the call.
            McpServerUnknownError: If the server is not registered in the
                caller's tenant.
            McpServerUnusableError: If the server's connection spec cannot be
                built (typically an unresolvable secret reference).
            McpUpstreamError: If the server cannot be reached or launched.
        """
        async with self._session_factory() as db:
            identity = await self._authenticate(db, request.principal, NO_SESSION)
            # The policy chain runs before the server row is loaded, so a call
            # naming an unregistered *and* unbound server is reported as unbound
            # rather than as unregistered. That ordering is the pre-proxy
            # behavior and is deliberately preserved.
            await self._authorize(
                McpCallContext(
                    operation=McpOperation.call_tool,
                    principal=request.principal,
                    identity=identity,
                    server_id=request.server_id,
                    tool_name=request.tool_name,
                    arguments=request.arguments,
                ),
                db,
            )
            server = await SqlMCPServerRepository(db, tenant_id=identity.tenant_id).get(
                request.server_id
            )
            if server is None:
                raise McpServerUnknownError(
                    f"MCP server {request.server_id!r} is not registered"
                )
            connection = await self._resolve_connection(
                server,
                self._build_resolver(db, identity.tenant_id),
                operation=McpOperation.call_tool,
            )
            server_name = server.name
        # The session is closed: the call below may take up to two minutes.
        try:
            return await mcp_client.call_server_tool(
                connection, request.tool_name, request.arguments
            )
        except McpConnectionError as exc:
            logger.warning("MCP server %s unreachable: %s", server_name, exc.reason)
            raise McpUpstreamError(
                f"MCP server {server_name!r} unreachable: {exc.reason}"
            ) from exc

    async def _query(
        self, base: ServerToolListing, connection: McpConnection | None
    ) -> ServerToolListing:
        """Query one server's tool catalog for a listing.

        Args:
            base: The entry identifying the server, already carrying an
                ``error`` when the connection could not be built.
            connection: The server's connection spec, or ``None`` when it could
                not be built.

        Returns:
            The entry with either its tools or its error filled in.
        """
        if connection is None:
            return base
        try:
            tools = await mcp_client.list_server_tools(connection)
        except McpConnectionError as exc:
            logger.warning(
                "MCP server %s unreachable: %s", base.server_name, exc.reason
            )
            return _with_error(base, f"unreachable: {exc.reason}")
        return ServerToolListing(
            server_id=base.server_id, server_name=base.server_name, tools=list(tools)
        )

    async def _authenticate(
        self, db: AsyncSession, principal: McpPrincipal, message: str
    ) -> McpIdentity:
        """Authenticate the caller, restating a failure in the operation's terms.

        Args:
            db: The proxy's open database session.
            principal: The caller's claimed identity.
            message: Caller-facing message to report an authentication failure
                as, which differs per operation.

        Returns:
            The verified identity.

        Raises:
            McpAuthenticationError: If the authenticator rejects the principal.
        """
        try:
            return await self._authenticator.authenticate(principal, db)
        except McpAuthenticationError as exc:
            raise McpAuthenticationError(message) from exc

    async def _authorize(self, ctx: McpCallContext, db: AsyncSession) -> None:
        """Consult every registered policy in order, stopping at the first denial.

        Args:
            ctx: The operation being attempted.
            db: The proxy's open database session.

        Raises:
            McpPolicyDeniedError: If any policy vetoes the operation.
        """
        for policy in self._policies:
            await policy.authorize(ctx, db)

    def _build_resolver(self, db: AsyncSession, tenant_id: str) -> SecretResolver:
        """Build the secret resolver a connection's placeholders expand through.

        Credential injection is the proxy's job: this is the one method that
        changes when per-caller credentials replace a server's stored headers.

        Args:
            db: The proxy's open database session.
            tenant_id: Tenant the resolved secrets must belong to.

        Returns:
            A resolver backed by the session's secret repository.
        """
        return SecretResolver(
            SqlSecretRepository(db, tenant_id=tenant_id),
            get_secret_cipher(),
            get_vault_client(),
        )

    async def _resolve_connection(
        self,
        server: MCPServer,
        resolver: SecretResolver,
        *,
        operation: McpOperation,
    ) -> McpConnection:
        """Build a registered server's connection spec, expanding its secrets.

        Args:
            server: The registered server row.
            resolver: Resolver for its ``${secret:NAME/KEY}`` placeholders.
            operation: Which operation is being served. Affects only the wording
                of the raised error, which the two operations report to their
                callers differently.

        Returns:
            The connection spec.

        Raises:
            McpServerUnusableError: If a referenced secret cannot be resolved, or
                the row is missing the field its transport requires.
        """
        try:
            return await mcp_client.resolve_connection(server, resolver)
        except SecretResolutionError as exc:
            logger.warning(
                "Secret %s resolution failed for MCP server %s: %s",
                exc.secret_name,
                server.name,
                exc.reason,
            )
            if operation is McpOperation.list_tools:
                message = f"cannot resolve secret {exc.secret_name!r} in headers"
            else:
                message = (
                    f"cannot resolve secret {exc.secret_name!r} in the headers "
                    f"of MCP server {server.name!r}"
                )
            raise McpServerUnusableError(message) from exc
        except McpConnectionError as exc:
            logger.warning("MCP server %s is not usable: %s", server.name, exc.reason)
            reason = (
                exc.reason
                if operation is McpOperation.list_tools
                else f"MCP server {server.name!r} is not usable: {exc.reason}"
            )
            raise McpServerUnusableError(reason) from exc


@lru_cache(maxsize=1)
def get_mcp_proxy() -> McpProxy:
    """Return the process-wide MCP proxy singleton.

    Defined here rather than in ``dependencies/singletons.py`` for the same
    reason :func:`infrastructure.vault_client.get_vault_client` is:
    :mod:`infrastructure.mcp_tools` must import it without pulling in the
    ``dependencies`` package, which would cycle back through
    :mod:`infrastructure.agent`. The import below is local for the same kind of
    reason -- :mod:`infrastructure.mcp_policies` imports this module.

    Returns:
        The shared proxy, built with the default policy chain.
    """
    from infrastructure.mcp_policies import default_policies

    return McpProxy(policies=default_policies())
