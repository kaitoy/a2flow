"""MCP tool certificate repository: Protocol interface and SQLModel implementation.

Tenant-scoped like every other resource repository: the filter is applied
explicitly on each query rather than through an ORM listener, because the MCP
gateway and the agent tools open their own sessions outside FastAPI's request
scope where a request-scoped listener would silently not apply.

There is no ``update`` beyond :meth:`SqlMcpToolCertificateRepository.revoke`.
A certificate's contents are signed, so the only thing that can change after
issuance is whether it still counts.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.mcp_tool_certificate import (
    McpToolCertificate,
    McpToolCertificateCreate,
    McpToolCertificateRead,
    RevocationReason,
)
from repositories._integrity import commit_or_translate_user_fk
from repositories.exceptions import NotFoundError
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort


class McpToolCertificateRepository(Protocol):
    """Interface for approval-certificate persistence operations."""

    async def get(self, certificate_id: str) -> McpToolCertificate | None: ...

    async def list_for_approval(self, approval_id: str) -> list[McpToolCertificate]: ...

    async def get_by_serial(self, serial_number: str) -> McpToolCertificate | None: ...

    async def get_live_for_task(
        self, workflow_task_id: str
    ) -> McpToolCertificate | None: ...

    async def list_live_for_task(
        self, workflow_task_id: str
    ) -> list[McpToolCertificate]: ...

    async def list_live_for_execution(
        self, workflow_execution_id: str
    ) -> list[McpToolCertificate]: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[McpToolCertificate]: ...

    async def create(
        self, data: McpToolCertificateCreate, *, user_id: str
    ) -> McpToolCertificate: ...

    async def revoke(
        self, certificate_id: str, reason: RevocationReason, *, user_id: str
    ) -> McpToolCertificate: ...


class SqlMcpToolCertificateRepository:
    """SQLModel-backed implementation of McpToolCertificateRepository."""

    def __init__(self, session: AsyncSession, *, tenant_id: str | None) -> None:
        """Store the session and the tenant these operations are scoped to.

        Args:
            session: The request-scoped (or job-scoped) database session.
            tenant_id: Tenant every query is filtered by.
        """
        self._db = session
        self._tenant_id = tenant_id

    def _require_tenant(self) -> str:
        """Return ``self._tenant_id``, raising if this instance has no concrete tenant.

        Only a write method should call this -- see
        ``repositories.agent_skill.SqlAgentSkillRepository._require_tenant``.
        """
        if self._tenant_id is None:
            raise RuntimeError(
                f"{type(self).__name__} mutation requires a concrete tenant_id"
            )
        return self._tenant_id

    async def _get_scoped(self, certificate_id: str) -> McpToolCertificate | None:
        """Fetch one certificate by id, filtered by tenant.

        Uses a filtered ``select`` rather than ``session.get`` so a
        cross-tenant id returns ``None`` (surfacing as a 404) instead of a row
        the caller may not see.
        """
        stmt = select(McpToolCertificate).where(McpToolCertificate.id == certificate_id)
        if self._tenant_id is not None:
            stmt = stmt.where(McpToolCertificate.tenant_id == self._tenant_id)
        result = await self._db.exec(stmt)
        return result.first()

    async def get(self, certificate_id: str) -> McpToolCertificate | None:
        """Return a certificate by id within the tenant, or ``None``.

        Args:
            certificate_id: The certificate's primary key.

        Returns:
            The row, or ``None`` when it does not exist in this tenant.
        """
        return await self._get_scoped(certificate_id)

    async def list_for_approval(self, approval_id: str) -> list[McpToolCertificate]:
        """Return every certificate issued under one approval, revoked or not.

        Plural because an approval covers the task it names *and* every task
        downstream of it up to the next approval (see
        :mod:`infrastructure.approval_scope`), and each of those tasks is
        granted its own certificate when it starts. The set therefore grows as
        the run advances.

        Revoked rows are included: an approver looking at a spent approval
        should still see what it authorized, not an empty panel.

        Args:
            approval_id: The approval the certificates were issued under.

        Returns:
            The rows, newest first, or an empty list when nothing has been
            issued under the approval yet.
        """
        result = await self._db.exec(
            select(McpToolCertificate)
            .where(
                McpToolCertificate.approval_id == approval_id,
                McpToolCertificate.tenant_id == self._tenant_id,
            )
            .order_by(col(McpToolCertificate.created_at).desc())
        )
        return list(result.all())

    async def get_by_serial(self, serial_number: str) -> McpToolCertificate | None:
        """Return the certificate with the given X.509 serial.

        This is how verification gets from a presented certificate to the row
        recording whether it has been revoked.

        Args:
            serial_number: Decimal serial string.

        Returns:
            The row, or ``None`` when no certificate in this tenant has it.
        """
        result = await self._db.exec(
            select(McpToolCertificate).where(
                McpToolCertificate.serial_number == serial_number,
                McpToolCertificate.tenant_id == self._tenant_id,
            )
        )
        return result.first()

    async def get_live_for_task(
        self, workflow_task_id: str
    ) -> McpToolCertificate | None:
        """Return the task's un-revoked certificate, if it has one.

        Args:
            workflow_task_id: The task the certificate authorizes.

        Returns:
            The un-revoked row, or ``None``. Expiry is deliberately not filtered
            here: an expired certificate should surface as "expired" during
            verification rather than as "no certificate at all", which is a
            different and more confusing failure for whoever reads the log.
        """
        result = await self._db.exec(
            select(McpToolCertificate).where(
                McpToolCertificate.workflow_task_id == workflow_task_id,
                McpToolCertificate.tenant_id == self._tenant_id,
                McpToolCertificate.revoked_at == None,  # noqa: E711
            )
        )
        return result.first()

    async def list_live_for_task(
        self, workflow_task_id: str
    ) -> list[McpToolCertificate]:
        """Return every un-revoked certificate a task currently holds.

        Plural where :meth:`get_live_for_task` is singular, because the partial
        unique indexes forbid two live grants of the *same* kind rather than two
        live grants: a task can briefly carry its run initiator's own grant
        alongside an approver's. The stand-down path
        (:meth:`services.mcp_tool_certificate.McpToolCertificateService.supersede_grants_for`)
        needs to see all of them, since a task whose governing approval has
        changed must not keep authority granted under the previous one.

        Args:
            workflow_task_id: The task the certificates authorize.

        Returns:
            The un-revoked rows, oldest first.
        """
        result = await self._db.exec(
            select(McpToolCertificate)
            .where(
                McpToolCertificate.workflow_task_id == workflow_task_id,
                McpToolCertificate.tenant_id == self._tenant_id,
                McpToolCertificate.revoked_at == None,  # noqa: E711
            )
            .order_by(col(McpToolCertificate.created_at))
        )
        return list(result.all())

    async def list_live_for_execution(
        self, workflow_execution_id: str
    ) -> list[McpToolCertificate]:
        """Return every un-revoked certificate issued within one run.

        Backs the caller-side lookup in
        :mod:`infrastructure.mcp_credentials`, which has a session id and a
        target tool but no task id: it picks whichever of the run's live
        certificates grants that tool.

        Args:
            workflow_execution_id: The run to collect certificates for.

        Returns:
            The un-revoked rows, oldest first.
        """
        result = await self._db.exec(
            select(McpToolCertificate)
            .where(
                McpToolCertificate.workflow_execution_id == workflow_execution_id,
                McpToolCertificate.tenant_id == self._tenant_id,
                McpToolCertificate.revoked_at == None,  # noqa: E711
            )
            .order_by(col(McpToolCertificate.created_at))
        )
        return list(result.all())

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[McpToolCertificate]:
        """Return a page of the tenant's certificates, newest first by default.

        Backs the admin audit list, which spans every approval rather than
        starting from one -- unlike the other read methods here, each of which
        answers a question the verification path asks about a specific approval,
        task, run, or serial.

        ``readable=McpToolCertificateRead`` keeps ``certificate_pem`` and
        ``private_key_encrypted`` out of the filter and sort surface: they are
        absent from that schema, so a client cannot use "which rows match" as a
        blind oracle on key material it never receives (see
        :func:`repositories.query._resolve_column`).

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of certificates.
        """
        stmt = select(McpToolCertificate)
        if self._tenant_id is not None:
            stmt = stmt.where(McpToolCertificate.tenant_id == self._tenant_id)
        stmt = apply_filters(
            stmt, McpToolCertificate, filters, readable=McpToolCertificateRead
        )
        stmt = apply_sort(
            stmt,
            McpToolCertificate,
            sort,
            default=[col(McpToolCertificate.created_at).desc()],
            readable=McpToolCertificateRead,
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(
        self, data: McpToolCertificateCreate, *, user_id: str
    ) -> McpToolCertificate:
        """Persist a freshly signed certificate.

        Args:
            data: The signed certificate, encrypted key, and validity window.
            user_id: The acting user, recorded as ``created_by``/``updated_by``.

        Returns:
            The persisted row.

        Raises:
            ForeignKeyViolationError: If the acting user does not exist.
        """
        certificate = McpToolCertificate(
            **data.model_dump(),
            tenant_id=self._require_tenant(),
            created_by=user_id,
            updated_by=user_id,
        )
        self._db.add(certificate)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(certificate)
        return certificate

    async def revoke(
        self, certificate_id: str, reason: RevocationReason, *, user_id: str
    ) -> McpToolCertificate:
        """Mark a certificate revoked, stamping the reason and the instant.

        Revoking an already-revoked certificate leaves the original
        ``revoked_at`` and reason in place: the first revocation is the one that
        actually stopped it being usable, and overwriting it would lose that.

        Args:
            certificate_id: The certificate to revoke.
            reason: Why it stopped being usable.
            user_id: The acting user, recorded as ``updated_by``.

        Returns:
            The revoked row.

        Raises:
            NotFoundError: If no such certificate exists in this tenant.
            ForeignKeyViolationError: If the acting user does not exist.
        """
        self._require_tenant()
        certificate = await self._get_scoped(certificate_id)
        if certificate is None:
            raise NotFoundError("McpToolCertificate", certificate_id)
        if certificate.revoked_at is None:
            certificate.revoked_at = datetime.now(UTC)
            certificate.revocation_reason = reason
        certificate.updated_by = user_id
        self._db.add(certificate)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(certificate)
        return certificate
