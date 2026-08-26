"""ApprovalCertificate repository: Protocol interface and SQLModel implementation.

Tenant-scoped like every other resource repository: the filter is applied
explicitly on each query rather than through an ORM listener, because the MCP
proxy and the agent tools open their own sessions outside FastAPI's request
scope where a request-scoped listener would silently not apply.

There is no ``update`` beyond :meth:`SqlApprovalCertificateRepository.revoke`.
A certificate's contents are signed, so the only thing that can change after
issuance is whether it still counts.
"""

from datetime import UTC, datetime
from typing import Protocol

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.approval_certificate import (
    ApprovalCertificate,
    ApprovalCertificateCreate,
    RevocationReason,
)
from repositories._integrity import commit_or_translate_user_fk
from repositories.exceptions import NotFoundError


class ApprovalCertificateRepository(Protocol):
    """Interface for approval-certificate persistence operations."""

    async def get(self, certificate_id: str) -> ApprovalCertificate | None: ...

    async def get_live_for_approval(
        self, approval_id: str
    ) -> ApprovalCertificate | None: ...

    async def get_latest_for_approval(
        self, approval_id: str
    ) -> ApprovalCertificate | None: ...

    async def get_by_serial(self, serial_number: str) -> ApprovalCertificate | None: ...

    async def get_live_for_task(
        self, workflow_task_id: str
    ) -> ApprovalCertificate | None: ...

    async def list_live_for_execution(
        self, workflow_execution_id: str
    ) -> list[ApprovalCertificate]: ...

    async def create(
        self, data: ApprovalCertificateCreate, *, user_id: str
    ) -> ApprovalCertificate: ...

    async def revoke(
        self, certificate_id: str, reason: RevocationReason, *, user_id: str
    ) -> ApprovalCertificate: ...


class SqlApprovalCertificateRepository:
    """SQLModel-backed implementation of ApprovalCertificateRepository."""

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

    async def _get_scoped(self, certificate_id: str) -> ApprovalCertificate | None:
        """Fetch one certificate by id, filtered by tenant.

        Uses a filtered ``select`` rather than ``session.get`` so a
        cross-tenant id returns ``None`` (surfacing as a 404) instead of a row
        the caller may not see.
        """
        stmt = select(ApprovalCertificate).where(
            ApprovalCertificate.id == certificate_id
        )
        if self._tenant_id is not None:
            stmt = stmt.where(ApprovalCertificate.tenant_id == self._tenant_id)
        result = await self._db.exec(stmt)
        return result.first()

    async def get(self, certificate_id: str) -> ApprovalCertificate | None:
        """Return a certificate by id within the tenant, or ``None``.

        Args:
            certificate_id: The certificate's primary key.

        Returns:
            The row, or ``None`` when it does not exist in this tenant.
        """
        return await self._get_scoped(certificate_id)

    async def get_live_for_approval(
        self, approval_id: str
    ) -> ApprovalCertificate | None:
        """Return the approval's un-revoked certificate, if it has one.

        At most one can exist, enforced by the partial unique index
        ``uq_approval_certificates_live``.

        Args:
            approval_id: The approval the certificate was issued for.

        Returns:
            The un-revoked row, or ``None``. Expiry is not filtered here; see
            :meth:`get_live_for_task` for why.
        """
        result = await self._db.exec(
            select(ApprovalCertificate).where(
                ApprovalCertificate.approval_id == approval_id,
                ApprovalCertificate.tenant_id == self._tenant_id,
                ApprovalCertificate.revoked_at == None,  # noqa: E711
            )
        )
        return result.first()

    async def get_latest_for_approval(
        self, approval_id: str
    ) -> ApprovalCertificate | None:
        """Return the approval's most recently issued certificate, revoked or not.

        Backs the read endpoint: an approver looking at a spent approval should
        still see which tools it granted, not an empty panel.

        Args:
            approval_id: The approval the certificate was issued for.

        Returns:
            The newest row, or ``None`` when the approval has no certificate.
        """
        result = await self._db.exec(
            select(ApprovalCertificate)
            .where(
                ApprovalCertificate.approval_id == approval_id,
                ApprovalCertificate.tenant_id == self._tenant_id,
            )
            .order_by(col(ApprovalCertificate.created_at).desc())
        )
        return result.first()

    async def get_by_serial(self, serial_number: str) -> ApprovalCertificate | None:
        """Return the certificate with the given X.509 serial.

        This is how verification gets from a presented certificate to the row
        recording whether it has been revoked.

        Args:
            serial_number: Decimal serial string.

        Returns:
            The row, or ``None`` when no certificate in this tenant has it.
        """
        result = await self._db.exec(
            select(ApprovalCertificate).where(
                ApprovalCertificate.serial_number == serial_number,
                ApprovalCertificate.tenant_id == self._tenant_id,
            )
        )
        return result.first()

    async def get_live_for_task(
        self, workflow_task_id: str
    ) -> ApprovalCertificate | None:
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
            select(ApprovalCertificate).where(
                ApprovalCertificate.workflow_task_id == workflow_task_id,
                ApprovalCertificate.tenant_id == self._tenant_id,
                ApprovalCertificate.revoked_at == None,  # noqa: E711
            )
        )
        return result.first()

    async def list_live_for_execution(
        self, workflow_execution_id: str
    ) -> list[ApprovalCertificate]:
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
            select(ApprovalCertificate)
            .where(
                ApprovalCertificate.workflow_execution_id == workflow_execution_id,
                ApprovalCertificate.tenant_id == self._tenant_id,
                ApprovalCertificate.revoked_at == None,  # noqa: E711
            )
            .order_by(col(ApprovalCertificate.created_at))
        )
        return list(result.all())

    async def create(
        self, data: ApprovalCertificateCreate, *, user_id: str
    ) -> ApprovalCertificate:
        """Persist a freshly signed certificate.

        Args:
            data: The signed certificate, encrypted key, and validity window.
            user_id: The acting user, recorded as ``created_by``/``updated_by``.

        Returns:
            The persisted row.

        Raises:
            ForeignKeyViolationError: If the acting user does not exist.
        """
        certificate = ApprovalCertificate(
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
    ) -> ApprovalCertificate:
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
            raise NotFoundError("ApprovalCertificate", certificate_id)
        if certificate.revoked_at is None:
            certificate.revoked_at = datetime.now(UTC)
            certificate.revocation_reason = reason
        certificate.updated_by = user_id
        self._db.add(certificate)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(certificate)
        return certificate
