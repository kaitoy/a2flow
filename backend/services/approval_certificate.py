"""Issuing and revoking the certificate that carries an approval's authority.

One certificate per approval, minted the moment an approver decides
``approved`` on an approval that names a workflow task, and required from then
on by :class:`infrastructure.mcp_policies.ApprovedTaskCertificatePolicy` on
every MCP ``call_tool` that belongs to that task.

The tools the certificate grants are read from the task's ``tool_bindings``
**at decision time** and signed into the certificate's ``subjectAltName``. That
snapshot is the point of the whole mechanism: the execution agent can rewrite a
task's bindings mid-run through ``update_workflow_task``, but it cannot
re-issue the certificate, so rewriting them cannot widen what it may call.

Failure to issue never fails the approval. If the task has vanished between the
decision and this call, the approval still stands and no certificate exists --
which leaves the task unable to call any tool, the safe direction. A warning is
logged so the gap is visible rather than silent.
"""

import logging
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.x509.oid import NameOID

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
from infrastructure.secret_cipher import SecretCipher
from models.approval import Approval, ApprovalStatus
from models.approval_certificate import (
    ApprovalCertificate,
    ApprovalCertificateCreate,
    ApprovalCertificateRead,
    RevocationReason,
)
from models.workflow_task import ToolBinding, WorkflowTaskRead, WorkflowTaskStatus
from repositories.approval_certificate import ApprovalCertificateRepository
from repositories.exceptions import NotFoundError
from repositories.mcp_ca import McpCertificateAuthorityRepository
from repositories.workflow_task import WorkflowTaskRepository

logger = logging.getLogger(__name__)

#: Task statuses that end the work an approval authorized.
TERMINAL_TASK_STATUSES = frozenset(
    {
        WorkflowTaskStatus.completed,
        WorkflowTaskStatus.failed,
        WorkflowTaskStatus.skipped,
    }
)


async def revoke_if_task_finished(
    certificates: ApprovalCertificateRepository,
    task: WorkflowTaskRead,
    *,
    user_id: str,
) -> None:
    """Revoke a task's certificate once the task reaches a terminal status.

    A free function rather than a method because both callers -- the REST
    service and the agent's task tool -- hold a certificate repository but not
    the full :class:`ApprovalCertificateService`, whose other collaborators are
    only needed for issuing.

    Safety does not depend on this running. A finished task is no longer
    ``in_progress``, so ``InProgressToolBindingPolicy`` already refuses its
    calls; what revoking adds is that the audit trail records *why* the
    certificate stopped counting, and that a certificate's lifetime matches the
    work it authorized rather than its full TTL.

    Args:
        certificates: Repository providing certificate persistence.
        task: The task as it stands after the write.
        user_id: The acting user, recorded as ``updated_by``.
    """
    if task.status not in TERMINAL_TASK_STATUSES:
        return
    certificate = await certificates.get_live_for_task(task.id)
    if certificate is None:
        return
    await certificates.revoke(
        certificate.id, RevocationReason.task_finished, user_id=user_id
    )


class ApprovalCertificateService:
    """Application service issuing and revoking approval certificates."""

    def __init__(
        self,
        certificates: ApprovalCertificateRepository,
        tasks: WorkflowTaskRepository,
        authorities: McpCertificateAuthorityRepository,
        cipher: SecretCipher,
    ) -> None:
        """Initialize the service.

        Args:
            certificates: Repository providing certificate persistence.
            tasks: Repository the granted tool set is read from.
            authorities: Repository the signing root is loaded through.
            cipher: Cipher the leaf's private key is encrypted with before it
                is persisted.
        """
        self._certificates = certificates
        self._tasks = tasks
        self._authorities = authorities
        self._cipher = cipher

    async def issue(
        self, approval: Approval, *, user_id: str
    ) -> ApprovalCertificate | None:
        """Issue the certificate for a newly granted approval.

        A no-op returning ``None`` when the approval is not ``approved`` or
        names no task: those approvals grant no tool authority, and the tasks
        they concern stay under the plain tool-binding policy.

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

        binding = CertificateBinding(
            tenant_id=approval.tenant_id,
            execution_id=approval.workflow_execution_id,
            task_id=task.id,
            approval_id=approval.id,
        )
        sans: list[x509.GeneralName] = [
            x509.UniformResourceIdentifier(build_binding_urn(binding))
        ]
        sans.extend(
            x509.UniformResourceIdentifier(
                build_tool_urn(item.mcp_server_id, item.tool_name)
            )
            for item in task.tool_bindings
        )

        settings = get_settings()
        # Anchored on the decision, not on now: the window an approval buys is
        # measured from when the human granted it.
        not_before = approval.decided_at or datetime.now(UTC)
        not_after = not_before + timedelta(
            seconds=settings.mcp_approval_cert_ttl_seconds
        )

        ca = await load_or_create_root_ca(self._authorities)
        leaf_key = generate_key()
        leaf = sign_leaf_certificate(
            ca,
            public_key=leaf_key.public_key(),
            subject=x509.Name(
                [
                    x509.NameAttribute(NameOID.COMMON_NAME, task.id),
                    x509.NameAttribute(NameOID.ORGANIZATION_NAME, approval.tenant_id),
                ]
            ),
            sans=sans,
            not_before=not_before,
            not_after=not_after,
        )

        certificate = await self._certificates.create(
            ApprovalCertificateCreate(
                approval_id=approval.id,
                workflow_execution_id=approval.workflow_execution_id,
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
        # Read back off the freshly refreshed row rather than off ``approval``:
        # the insert above committed, and a caller whose session expires on
        # commit would turn this log line into lazy IO outside the greenlet.
        logger.info(
            "Issued approval certificate %s (serial %s) for approval %s granting %d tool(s)",
            certificate.id,
            certificate.serial_number,
            certificate.approval_id,
            len(task.tool_bindings),
        )
        return certificate

    async def revoke_for_task(
        self, workflow_task_id: str, reason: RevocationReason, *, user_id: str
    ) -> None:
        """Revoke a task's live certificate, if it has one.

        Called when a task reaches a terminal status: the authority an approval
        granted is spent once the work it authorized is done.

        Args:
            workflow_task_id: The task whose certificate should stop counting.
            reason: Why it stopped.
            user_id: The acting user, recorded as ``updated_by``.
        """
        certificate = await self._certificates.get_live_for_task(workflow_task_id)
        if certificate is None:
            return
        await self._certificates.revoke(certificate.id, reason, user_id=user_id)

    async def read_for_approval(self, approval_id: str) -> ApprovalCertificateRead:
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
            raise NotFoundError("ApprovalCertificate", approval_id)
        claims = extract_claims(
            x509.load_pem_x509_certificate(certificate.certificate_pem.encode("ascii"))
        )
        allowed = [
            ToolBinding(mcp_server_id=server_id, tool_name=tool_name)
            for server_id, tool_name in sorted(claims.allowed_tools)
        ]
        return ApprovalCertificateRead.from_certificate(
            certificate, allowed_tools=allowed
        )
