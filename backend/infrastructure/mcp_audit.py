"""The database-backed audit sink for MCP tool-call decisions.

Kept out of :mod:`infrastructure.mcp_proxy` for the same reason
:mod:`infrastructure.mcp_policies` is: writing a row means importing
:mod:`repositories`, and the proxy stays free of those imports so its public
surface remains the plain value objects an HTTP handler would rebuild.

What lands in a row is described in :mod:`models.mcp_tool_invocation`. The part
worth restating here is the ordering: the signature and the bytes it covers are
recorded together, so the record can be re-verified later against the root CA's
public half alone.
"""

import base64

from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.mcp_certificate import arguments_digest as hash_arguments
from infrastructure.mcp_proxy import McpCallContext
from models.mcp_tool_invocation import McpAuditDecision, McpToolInvocationCreate
from models.user import SYSTEM_USER_ID
from repositories.mcp_tool_invocation import SqlMcpToolInvocationRepository


class SqlMcpAuditSink:
    """Appends each decision to ``mcp_tool_invocations``."""

    async def record(
        self,
        ctx: McpCallContext,
        db: AsyncSession,
        *,
        decision: McpAuditDecision,
        reason: str | None,
    ) -> None:
        """Write one decision record.

        Args:
            ctx: The operation that was decided on.
            db: The proxy's open database session.
            decision: Whether the call was allowed.
            reason: The refusal message when denied, else ``None``.
        """
        presented = ctx.principal.credential
        verified = ctx.identity.credential
        binding = verified.claims.binding if verified is not None else None
        payload = McpToolInvocationCreate(
            session_id=ctx.principal.session_id,
            workflow_execution_id=ctx.identity.execution_id,
            workflow_task_id=binding.task_id if binding is not None else None,
            approval_id=binding.approval_id if binding is not None else None,
            certificate_serial=(
                verified.claims.serial_number if verified is not None else None
            ),
            mcp_server_id=ctx.server_id or "",
            tool_name=ctx.tool_name or "",
            decision=decision,
            denial_reason=reason,
            arguments_digest=hash_arguments(ctx.arguments or {}),
            signature=(
                base64.b64encode(presented.signature).decode("ascii")
                if presented is not None
                else None
            ),
            nonce=presented.nonce if presented is not None else None,
            signed_at=presented.timestamp if presented is not None else None,
        )
        # The acting user owns the record. A run always has one; the seeded
        # system user is the fallback so a missing acting user cannot make the
        # audit row unwritable.
        repo = SqlMcpToolInvocationRepository(db, tenant_id=ctx.identity.tenant_id)
        await repo.record(payload, user_id=ctx.identity.user_id or SYSTEM_USER_ID)
