"""Issuing and revoking the certificate that carries a task's tool authority.

:class:`infrastructure.mcp_policies.TaskCertificatePolicy` requires a valid
certificate on **every** MCP ``call_tool``, so every task that is going to call
a tool needs one. There are two ways to get one, and this module owns both:

:meth:`McpToolCertificateService.issue`
    An approver decided ``approved`` on an approval naming the task. Minted at
    that moment, ``granted_by`` the approver who decided.

:meth:`McpToolCertificateService.issue_for_started_task`
    Nobody was asked to approve the task, so the run's initiator grants its
    bound tools to themselves. Minted when the task goes ``in_progress``,
    ``granted_by`` the initiator.

The tools a certificate grants are read from the task's ``tool_bindings`` **at
issuance** and signed into the certificate's ``subjectAltName``. That snapshot
is the point of the whole mechanism, and it applies to both paths equally: a
run's tasks and their ``tool_bindings`` are copied from the workflow's published
templates at execute time and the execution agent cannot edit them, and even a
later edit to the workflow cannot re-issue a certificate already granted, so
nothing widens what a task may call once its grant is set. Tools have to be
bound into the template *before* the workflow is published.

The two paths never both authorize one task. Requesting an approval for a task
revokes the initiator grant it already had
(:meth:`McpToolCertificateService.supersede_initiator_grant`), and
:meth:`issue_for_started_task` declines to issue for a task that has an
approval. The policy layer re-checks the same rule at call time, so neither
bookkeeping step is what the guarantee rests on.

Failure to issue never fails the write that triggered it. If the task has
vanished between an approval's decision and this call, the approval still
stands and no certificate exists -- which leaves the task unable to call any
tool, the safe direction. A warning is logged so the gap is visible rather than
silent.
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.x509.oid import NameOID
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.mcp_ca import (
    certificate_to_pem,
    generate_key,
    load_or_create_root_ca,
    private_key_to_pem,
    sign_leaf_certificate,
)
from infrastructure.mcp_certificate import (
    CertificateBinding,
    build_binding_urn,
    build_tool_urn,
    extract_claims,
)
from infrastructure.secret_cipher import SecretCipher, get_secret_cipher
from models.approval import Approval, ApprovalStatus
from models.mcp_tool_certificate import (
    CertificateGrant,
    McpToolCertificate,
    McpToolCertificateCreate,
    McpToolCertificateRead,
    RevocationReason,
)
from models.workflow_execution import WorkflowExecution
from models.workflow_task import ToolBinding, WorkflowTaskRead, WorkflowTaskStatus
from repositories.approval import ApprovalRepository, SqlApprovalRepository
from repositories.exceptions import NotFoundError
from repositories.mcp_ca import (
    McpCertificateAuthorityRepository,
    SqlMcpCertificateAuthorityRepository,
)
from repositories.mcp_server import SqlMCPServerRepository
from repositories.mcp_tool_certificate import (
    McpToolCertificateRepository,
    SqlMcpToolCertificateRepository,
)
from repositories.query import FilterSpec, SortSpec
from repositories.user import SqlUserRepository
from repositories.user_group import SqlUserGroupRepository
from repositories.workflow_execution import SqlWorkflowExecutionRepository
from repositories.workflow_task import SqlWorkflowTaskRepository, WorkflowTaskRepository

logger = logging.getLogger(__name__)

#: Task statuses that end the work a certificate authorized.
TERMINAL_TASK_STATUSES = frozenset(
    {
        WorkflowTaskStatus.completed,
        WorkflowTaskStatus.failed,
        WorkflowTaskStatus.skipped,
    }
)


def build_mcp_tool_certificate_service(
    db: AsyncSession, *, tenant_id: str
) -> "McpToolCertificateService":
    """Wire a certificate service to an already-open session.

    For callers outside FastAPI's dependency-injection scope -- the ADK agent
    tools, which open their own session on the module-level engine. The same
    shape as :func:`services.notification_dispatch.build_notification_dispatcher`,
    and for the same reason: those tools need the whole service now that
    starting a task issues a certificate, not just the repository they used to
    revoke through.

    Args:
        db: The caller's open database session.
        tenant_id: Tenant every repository below is scoped to.

    Returns:
        A service ready to issue and revoke within that tenant.
    """
    executions = SqlWorkflowExecutionRepository(db, tenant_id=tenant_id)
    groups = SqlUserGroupRepository(db, SqlUserRepository(db), tenant_id=tenant_id)
    return McpToolCertificateService(
        SqlMcpToolCertificateRepository(db, tenant_id=tenant_id),
        SqlWorkflowTaskRepository(
            db,
            executions,
            SqlMCPServerRepository(db, tenant_id=tenant_id),
            tenant_id=tenant_id,
        ),
        SqlMcpCertificateAuthorityRepository(db),
        get_secret_cipher(),
        SqlApprovalRepository(db, executions, groups, tenant_id=tenant_id),
    )


class McpToolCertificateService:
    """Application service issuing and revoking MCP tool certificates."""

    def __init__(
        self,
        certificates: McpToolCertificateRepository,
        tasks: WorkflowTaskRepository,
        authorities: McpCertificateAuthorityRepository,
        cipher: SecretCipher,
        approvals: ApprovalRepository,
    ) -> None:
        """Initialize the service.

        Args:
            certificates: Repository providing certificate persistence.
            tasks: Repository the granted tool set is read from.
            authorities: Repository the signing root is loaded through.
            cipher: Cipher the leaf's private key is encrypted with before it
                is persisted.
            approvals: Repository used to tell the two issuance paths apart --
                a task with an approval attached is the approver's to authorize,
                never the initiator's.
        """
        self._certificates = certificates
        self._approvals = approvals
        self._tasks = tasks
        self._authorities = authorities
        self._cipher = cipher

    async def issue(
        self, approval: Approval, *, user_id: str
    ) -> McpToolCertificate | None:
        """Issue the certificate for a newly granted approval.

        A no-op returning ``None`` when the approval is not ``approved`` or
        names no task: neither grants any tool authority. A task left in the
        first case can call nothing until its approval is granted, which is the
        whole point of asking; a task in the second was never gated by this
        approval at all and takes its authority from
        :meth:`issue_for_started_task` instead.

        Args:
            approval: The resolved approval.
            user_id: The acting user, recorded as ``created_by``/``updated_by``.

        Returns:
            The issued certificate, or ``None`` when nothing was issued.
        """
        if approval.status != ApprovalStatus.approved:
            return None
        if approval.workflow_task_id is None:
            return None

        task = await self._tasks.get(approval.workflow_task_id)
        if task is None:
            logger.warning(
                "Approval %s was granted but its task %s no longer exists; no "
                "certificate issued, so the task cannot call any MCP tool",
                approval.id,
                approval.workflow_task_id,
            )
            return None

        live = await self._certificates.get_live_for_approval(approval.id)
        if live is not None:
            # ``resolve`` also runs when an approver only edits their comment on
            # an already-approved request. Returning the standing certificate
            # keeps that from silently rotating the key and the granted tool set
            # under a task that is already running against them.
            return live

        # The approver's grant displaces any grant the initiator had already
        # given themselves for this task, so the audit trail shows one live
        # authority at a time rather than two overlapping ones.
        await self.supersede_initiator_grant(task.id, user_id=user_id)

        return await self._sign_and_store(
            task=task,
            tenant_id=approval.tenant_id,
            binding=CertificateBinding(
                tenant_id=approval.tenant_id,
                execution_id=approval.workflow_execution_id,
                task_id=task.id,
                approval_id=approval.id,
            ),
            grant_kind=CertificateGrant.approval,
            approval_id=approval.id,
            granted_by=user_id,
            # Anchored on the decision, not on now: the window an approval buys
            # is measured from when the human granted it.
            not_before=approval.decided_at or datetime.now(UTC),
            user_id=user_id,
        )

    async def issue_for_started_task(
        self,
        task: WorkflowTaskRead,
        execution: WorkflowExecution,
        *,
        user_id: str,
    ) -> McpToolCertificate | None:
        """Issue the run initiator's own grant for a task that just started.

        This is what lets a task nobody was asked to approve call the tools it
        binds: the person who executed the workflow authorizes them, at the
        moment the task goes ``in_progress``, over exactly the bindings the task
        carries right then. Adding a binding afterwards does not extend the
        grant -- the certificate is signed and cannot be re-issued while it
        stands, which is the same freeze an approval-backed certificate imposes.

        Four conditions have to hold, and any of them failing is an ordinary
        ``None``, not an error:

        1. The task is ``in_progress``. Nothing else needs tool authority.
        2. It has no live certificate yet, so a repeated write -- an agent that
           re-sends ``in_progress``, or a title edit on a running task -- does
           not rotate the key and the grant underneath a task already calling
           against them.
        3. It has no approval attached. That task's authority is the approver's
           to grant, and issuing here would let a run get ahead of the decision
           it was told to wait for.
        4. It binds at least one tool. A task binding none can call nothing
           anyway (``InProgressToolBindingPolicy`` refuses first), so a
           certificate for it would be a row, a keypair, and an audit entry that
           authorize nothing.

        Args:
            task: The task as it stands after the write that started it.
            execution: The run it belongs to, supplying the tenant and the
                initiator the grant is attributed to.
            user_id: The acting user, recorded as ``created_by``/``updated_by``.
                Not necessarily the initiator -- an approver driving someone
                else's run through the REST endpoints is also a legitimate
                caller -- which is why ``granted_by`` is read off the execution.

        Returns:
            The issued certificate, or ``None`` when nothing was issued.
        """
        if task.status != WorkflowTaskStatus.in_progress:
            return None
        if not task.tool_bindings:
            return None
        if await self._certificates.get_live_for_task(task.id) is not None:
            return None
        if await self._approvals.get_for_task(task.id) is not None:
            return None

        return await self._sign_and_store(
            task=task,
            tenant_id=execution.tenant_id,
            binding=CertificateBinding(
                tenant_id=execution.tenant_id,
                execution_id=execution.id,
                task_id=task.id,
                initiator_id=execution.initiator_id,
            ),
            grant_kind=CertificateGrant.initiator,
            approval_id=None,
            granted_by=execution.initiator_id,
            # Anchored on now, unlike the approval path: there is no earlier
            # decision to measure the window from -- the task starting *is* the
            # moment the authority is taken.
            not_before=datetime.now(UTC),
            user_id=user_id,
        )

    async def _sign_and_store(
        self,
        *,
        task: WorkflowTaskRead,
        tenant_id: str,
        binding: CertificateBinding,
        grant_kind: CertificateGrant,
        approval_id: str | None,
        granted_by: str,
        not_before: datetime,
        user_id: str,
    ) -> McpToolCertificate:
        """Sign a leaf over the task's current bindings and persist it.

        The half both issuance paths share: everything from "which tools, whose
        authority, valid from when" onwards is identical, and keeping it in one
        place is what stops an initiator grant from drifting into a weaker
        certificate than an approval-backed one.

        Args:
            task: The task whose ``tool_bindings`` become the signed grant.
            tenant_id: Tenant the certificate belongs to.
            binding: The single binding URN's contents, already naming its
                grantor.
            grant_kind: Which issuance path this is.
            approval_id: The approval backing the grant, or ``None``.
            granted_by: The human the authority is attributed to.
            not_before: Start of the validity window.
            user_id: The acting user, recorded as ``created_by``/``updated_by``.

        Returns:
            The persisted certificate.
        """
        sans: list[x509.GeneralName] = [
            x509.UniformResourceIdentifier(build_binding_urn(binding))
        ]
        sans.extend(
            x509.UniformResourceIdentifier(
                build_tool_urn(item.mcp_server_id, item.tool_name)
            )
            for item in task.tool_bindings
        )
        not_after = not_before + timedelta(
            seconds=get_settings().mcp_tool_cert_ttl_seconds
        )

        ca = await load_or_create_root_ca(self._authorities)
        leaf_key = generate_key()
        leaf = sign_leaf_certificate(
            ca,
            public_key=leaf_key.public_key(),
            subject=x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, task.id),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, tenant_id),
                ]
            ),
            sans=sans,
            not_before=not_before,
            not_after=not_after,
        )

        certificate = await self._certificates.create(
            McpToolCertificateCreate(
                grant_kind=grant_kind,
                approval_id=approval_id,
                granted_by=granted_by,
                workflow_execution_id=binding.execution_id,
                workflow_task_id=task.id,
                ca_id=ca.ca_id,
                serial_number=str(leaf.serial_number),
                certificate_pem=certificate_to_pem(leaf),
                private_key_encrypted=self._cipher.encrypt(
                    private_key_to_pem(leaf_key)
                ),
                not_before=not_before,
                not_after=not_after,
            ),
            user_id=user_id,
        )
        # Read back off the freshly refreshed row rather than off the arguments:
        # the insert above committed, and a caller whose session expires on
        # commit would turn this log line into lazy IO outside the greenlet.
        logger.info(
            "Issued %s tool certificate %s (serial %s) for task %s granting %d tool(s)",
            certificate.grant_kind.value,
            certificate.id,
            certificate.serial_number,
            certificate.workflow_task_id,
            len(task.tool_bindings),
        )
        return certificate

    async def revoke_if_task_finished(
        self, task: WorkflowTaskRead, *, user_id: str
    ) -> None:
        """Revoke a task's certificate once the task reaches a terminal status.

        Safety does not depend on this running. A finished task is no longer
        ``in_progress``, so ``InProgressToolBindingPolicy`` already refuses its
        calls; what revoking adds is that the audit trail records *why* the
        certificate stopped counting, and that a certificate's lifetime matches
        the work it authorized rather than its full TTL.

        It is also what lets a task be started again: the live-grant checks in
        :meth:`issue_for_started_task` are what would otherwise keep a task
        returned to ``pending`` and restarted from getting a fresh certificate
        over its new bindings.

        Args:
            task: The task as it stands after the write.
            user_id: The acting user, recorded as ``updated_by``.
        """
        if task.status not in TERMINAL_TASK_STATUSES:
            return
        await self.revoke_for_task(
            task.id, RevocationReason.task_finished, user_id=user_id
        )

    async def supersede_initiator_grant(
        self, workflow_task_id: str, *, user_id: str
    ) -> None:
        """Revoke a task's initiator grant, if it has one, for an approval's sake.

        Called from both ends of the race between starting a task and requesting
        an approval for it: when an approval is created for a task already
        running under its initiator's own grant, and again when that approval is
        granted. Approval-backed certificates on the task are deliberately left
        alone -- this only stands the initiator's grant down.

        The gate does not depend on it. ``TaskCertificatePolicy`` refuses an
        initiator grant for any task that has an approval attached, whether or
        not the row was stamped. What this adds is that the audit trail shows
        one live authority per task instead of two overlapping ones.

        Args:
            workflow_task_id: The task whose initiator grant should stand down.
            user_id: The acting user, recorded as ``updated_by``.
        """
        certificate = await self._certificates.get_live_initiator_for_task(
            workflow_task_id
        )
        if certificate is None:
            return
        await self._certificates.revoke(
            certificate.id, RevocationReason.superseded_by_approval, user_id=user_id
        )

    async def revoke_for_task(
        self, workflow_task_id: str, reason: RevocationReason, *, user_id: str
    ) -> None:
        """Revoke a task's live certificate, if it has one.

        Called when a task reaches a terminal status: the authority it was
        granted -- by an approver or by the run's initiator -- is spent once the
        work it authorized is done.

        Args:
            workflow_task_id: The task whose certificate should stop counting.
            reason: Why it stopped.
            user_id: The acting user, recorded as ``updated_by``.
        """
        certificate = await self._certificates.get_live_for_task(workflow_task_id)
        if certificate is None:
            return
        await self._certificates.revoke(certificate.id, reason, user_id=user_id)

    async def read_for_approval(self, approval_id: str) -> McpToolCertificateRead:
        """Return the public view of an approval's certificate.

        The granted tools are parsed back out of the signed certificate rather
        than read from a separate column, so the API can never report a grant
        that differs from what the certificate actually says.

        Args:
            approval_id: The approval whose certificate to read.

        Returns:
            The read view, including the granted tools.

        Raises:
            NotFoundError: If the approval has no certificate.
            CertificateVerificationError: If the stored certificate is
                unparseable or carries claims that do not fit the grammar.
        """
        certificate = await self._certificates.get_latest_for_approval(approval_id)
        if certificate is None:
            raise NotFoundError("McpToolCertificate", approval_id)
        return _to_read(certificate)

    async def read(self, certificate_id: str) -> McpToolCertificateRead:
        """Return the public view of one certificate by its own id.

        Backs the admin audit surface, which reaches a certificate directly
        rather than through the approval it was issued for.

        Args:
            certificate_id: The certificate's primary key.

        Returns:
            The read view, including the granted tools.

        Raises:
            NotFoundError: If no certificate exists with that ID in the acting
                tenant.
            CertificateVerificationError: If the stored certificate is
                unparseable or carries claims that do not fit the grammar.
        """
        certificate = await self._certificates.get(certificate_id)
        if certificate is None:
            raise NotFoundError("McpToolCertificate", certificate_id)
        return _to_read(certificate)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[McpToolCertificateRead]:
        """Return a page of the acting tenant's certificates as read views.

        Every row's granted tools are parsed back out of its signed certificate,
        exactly as :meth:`read_for_approval` does for one. That means a page of
        rows costs a page of X.509 parses, which is the price of the guarantee
        the single read already makes: the API cannot report a grant that
        differs from what was actually signed.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of read views.

        Raises:
            CertificateVerificationError: If a stored certificate is unparseable
                or carries claims that do not fit the grammar.
        """
        certificates = await self._certificates.list(
            limit=limit, offset=offset, sort=sort, filters=filters
        )
        return [_to_read(certificate) for certificate in certificates]


def _to_read(certificate: McpToolCertificate) -> McpToolCertificateRead:
    """Build a certificate's public view, parsing its grants out of the PEM.

    The granted tools are read back from the signed certificate rather than from
    a column, so a response can never report a grant that differs from what the
    certificate says. The private key and the PEM itself are dropped by
    :meth:`models.mcp_tool_certificate.McpToolCertificateRead.from_certificate`.

    Args:
        certificate: The persisted certificate row.

    Returns:
        The read view, including the granted tools in a stable order.

    Raises:
        CertificateVerificationError: If the stored certificate is unparseable
            or carries claims that do not fit the grammar.
    """
    claims = extract_claims(
        x509.load_pem_x509_certificate(certificate.certificate_pem.encode("ascii"))
    )
    allowed = [
        ToolBinding(mcp_server_id=server_id, tool_name=tool_name)
        for server_id, tool_name in sorted(claims.allowed_tools)
    ]
    return McpToolCertificateRead.from_certificate(certificate, allowed_tools=allowed)
