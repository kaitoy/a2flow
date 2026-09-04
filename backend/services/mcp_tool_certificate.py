"""Issuing and revoking the certificate that carries a task's tool authority.

:class:`infrastructure.mcp_policies.TaskCertificatePolicy` requires a valid
certificate on **every** MCP ``call_tool``, so every task that is going to call
a tool needs one. A task gets exactly one, when it goes ``in_progress``, and who
granted it is decided by :mod:`infrastructure.approval_scope`:

**An approval governs the task** -- it is the nearest approval at or above the
task in the run's dependency graph. Then the certificate is that approval's,
``granted_by`` the approver who decided it. Until every approval governing the
task is granted, no certificate is issued at all and the task can call nothing.

**No approval governs it.** Then the run's initiator grants the task's bound
tools to themselves, ``granted_by`` the initiator.

Both cases run through :meth:`McpToolCertificateService.issue_for_started_task`.
:meth:`McpToolCertificateService.issue` is the other end of the same rule: when
an approval is granted, any task it governs that is *already* ``in_progress``
-- waiting on exactly that decision -- is issued its certificate there and then,
since nothing else will start it again.

Issuing at task start rather than at the decision is what lets one approval
cover a long chain of tasks: each covered task's certificate gets its own
validity window, so the chain does not have to finish inside the window opened
by the approver's click.

The tools a certificate grants are read from the task's ``tool_bindings`` **at
issuance** and signed into the certificate's ``subjectAltName``. That snapshot
is the point of the whole mechanism, and it applies to both paths equally: a
run's tasks and their ``tool_bindings`` are copied from the workflow's published
templates at execute time, the execution agent cannot edit them, and
:class:`services.workflow_task.WorkflowTaskService` refuses to change them on a
task an approval governs -- so nothing widens what a task may call once its
grant is set. Tools have to be bound into the template *before* the workflow is
published.

The two grantors never both authorize one task. Requesting an approval stands
down every grant already held by the tasks it now governs
(:meth:`McpToolCertificateService.supersede_grants_for`), and issuance refuses
to hand a task an initiator grant while an approval governs it. The policy layer
re-checks the same rule at call time, so neither bookkeeping step is what the
guarantee rests on.

Failure to issue never fails the write that triggered it. If the task has
vanished between an approval's decision and this call, the approval still
stands and no certificate exists -- which leaves the task unable to call any
tool, the safe direction. A warning is logged so the gap is visible rather than
silent.
"""

import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.x509.oid import NameOID
from sqlmodel.ext.asyncio.session import AsyncSession

from config import get_settings
from infrastructure.approval_scope import active_approval_by_task, governing_approvals
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

#: Upper bound on how many of a run's tasks one issuance decision reads. Mirrors
#: ``infrastructure.mcp_policies._MAX_TASKS``, which caps the same whole-run scan
#: on the enforcement side.
_MAX_TASKS = 1000

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
            approvals: Repository the run's approvals are read from, so
                :mod:`infrastructure.approval_scope` can tell the two issuance
                paths apart -- a task an approval governs is the approver's to
                authorize, never the initiator's.
        """
        self._certificates = certificates
        self._approvals = approvals
        self._tasks = tasks
        self._authorities = authorities
        self._cipher = cipher

    async def _run_scope(
        self, execution_id: str
    ) -> tuple[list[WorkflowTaskRead], dict[str, frozenset[str]], dict[str, Approval]]:
        """Load one run's task graph and work out which approval governs what.

        Two queries for the whole run, not one per task: both callers below need
        the same answer for several tasks at once.

        Args:
            execution_id: The run to resolve.

        Returns:
            The run's tasks, the governing-approval ids keyed by task id, and
            the run's approvals keyed by their own id.
        """
        tasks = await self._tasks.list(
            limit=_MAX_TASKS, offset=0, workflow_execution_id=execution_id
        )
        approvals = await self._approvals.list_for_execution(execution_id)
        governing = governing_approvals(tasks, active_approval_by_task(approvals))
        return tasks, governing, {approval.id: approval for approval in approvals}

    @staticmethod
    def _governing_of(
        task_id: str,
        governing: Mapping[str, frozenset[str]],
        approvals_by_id: Mapping[str, Approval],
    ) -> list[Approval] | None:
        """Resolve a task's governing approval ids to their rows.

        Args:
            task_id: The task to resolve for.
            governing: Governing-approval ids keyed by task id.
            approvals_by_id: The run's approvals keyed by their own id.

        Returns:
            The governing approvals, empty when none governs the task -- or
            ``None`` when an id has no row behind it, which can only mean the
            approval vanished between the two queries and is treated as a
            refusal rather than as "ungoverned".
        """
        approval_ids = governing.get(task_id, frozenset())
        approvals = [
            approvals_by_id[approval_id]
            for approval_id in approval_ids
            if approval_id in approvals_by_id
        ]
        return approvals if len(approvals) == len(approval_ids) else None

    async def issue(
        self, approval: Approval, *, user_id: str
    ) -> list[McpToolCertificate]:
        """Issue certificates for the tasks a newly granted approval unblocks.

        Returns an empty list when the approval is not ``approved`` or names no
        task: neither grants any tool authority. A task left in the first case
        can call nothing until its approval is granted, which is the whole point
        of asking.

        Only tasks already ``in_progress`` are issued for. The rest of the
        approval's scope has not started yet, and each will be granted its own
        certificate when it does (:meth:`issue_for_started_task`) -- which is
        what keeps one approval's authority from having to fit inside a single
        certificate's validity window.

        Idempotent: ``resolve`` also runs when an approver merely edits their
        comment on an already-granted request, and a task already holding this
        approval's certificate keeps it rather than having its key and granted
        tool set silently rotated underneath it.

        Args:
            approval: The resolved approval.
            user_id: The acting user, recorded as ``created_by``/``updated_by``.

        Returns:
            The certificates newly issued, empty when none was -- including on a
            repeat call, whose covered tasks all already hold theirs.
        """
        if approval.status != ApprovalStatus.approved:
            return []
        if approval.workflow_task_id is None:
            return []

        tasks, governing, approvals_by_id = await self._run_scope(
            approval.workflow_execution_id
        )
        covered = [
            task for task in tasks if approval.id in governing.get(task.id, frozenset())
        ]
        if not covered:
            logger.warning(
                "Approval %s was granted but governs no task of run %s; no "
                "certificate issued, so nothing it was meant to authorize can "
                "call an MCP tool",
                approval.id,
                approval.workflow_execution_id,
            )
            return []

        issued: list[McpToolCertificate] = []
        for task in covered:
            certificate = await self._issue_for_task(
                task,
                tenant_id=approval.tenant_id,
                execution_id=approval.workflow_execution_id,
                initiator_id=None,
                governing=governing,
                approvals_by_id=approvals_by_id,
                user_id=user_id,
            )
            if certificate is not None:
                issued.append(certificate)
        return issued

    async def issue_for_started_task(
        self,
        task: WorkflowTaskRead,
        execution: WorkflowExecution,
        *,
        user_id: str,
    ) -> McpToolCertificate | None:
        """Issue the grant a task needs when it starts, from whoever may give it.

        This is the ordinary path: at the moment a task goes ``in_progress`` it
        is granted exactly the tools it binds right then, on the authority of
        the nearest approval above it in the run's graph -- or, when no approval
        governs it, on the run initiator's own.

        Four conditions have to hold, and any of them failing is an ordinary
        ``None``, not an error:

        1. The task is ``in_progress``. Nothing else needs tool authority.
        2. It already holds a certificate from the authority that would grant it
           now, so a repeated write -- an agent that re-sends ``in_progress``,
           or a title edit on a running task -- does not rotate the key and the
           grant underneath a task already calling against them.
        3. Every approval governing it is granted. While one is still undecided
           (or was rejected) the task is gated, and issuing here would let a run
           get ahead of the decision it was told to wait for.
        4. It binds at least one tool. A task binding none can call nothing
           anyway (``InProgressToolBindingPolicy`` refuses first), so a
           certificate for it would be a row, a keypair, and an audit entry that
           authorize nothing.

        Args:
            task: The task as it stands after the write that started it.
            execution: The run it belongs to, supplying the tenant and the
                initiator an ungoverned task's grant is attributed to.
            user_id: The acting user, recorded as ``created_by``/``updated_by``.
                Not necessarily the grantor -- an approver driving someone
                else's run through the REST endpoints is also a legitimate
                caller -- which is why ``granted_by`` is read off the execution
                or off the approval instead.

        Returns:
            The newly signed certificate, or ``None`` when nothing was issued.
        """
        if task.status != WorkflowTaskStatus.in_progress:
            return None
        if not task.tool_bindings:
            return None

        _, governing, approvals_by_id = await self._run_scope(execution.id)
        return await self._issue_for_task(
            task,
            tenant_id=execution.tenant_id,
            execution_id=execution.id,
            initiator_id=execution.initiator_id,
            governing=governing,
            approvals_by_id=approvals_by_id,
            user_id=user_id,
        )

    async def _issue_for_task(
        self,
        task: WorkflowTaskRead,
        *,
        tenant_id: str,
        execution_id: str,
        initiator_id: str | None,
        governing: Mapping[str, frozenset[str]],
        approvals_by_id: Mapping[str, Approval],
        user_id: str,
    ) -> McpToolCertificate | None:
        """Give one task the certificate its current authority allows, if any.

        The single place that answers "what may this task hold right now", so
        the two entry points above cannot drift into granting different things.
        A task holding a certificate from an authority that no longer applies --
        its run initiator's, after an approval claimed it; an outer approval's,
        after a nearer one was requested -- has that certificate revoked here
        before the new one is signed, so the record shows one live authority per
        task rather than two overlapping ones.

        Args:
            task: The task to grant.
            tenant_id: Tenant the run belongs to.
            execution_id: The run the task belongs to.
            initiator_id: The run's initiator, or ``None`` when the caller did
                not resolve the run row. An ungoverned task cannot be granted
                without it, and is skipped.
            governing: Governing-approval ids keyed by task id.
            approvals_by_id: The run's approvals keyed by their own id.
            user_id: The acting user, recorded as ``created_by``/``updated_by``.

        Returns:
            The newly signed certificate, or ``None`` when nothing was issued --
            including when the task already holds one from the same authority,
            which is left exactly as it stands.
        """
        if task.status != WorkflowTaskStatus.in_progress or not task.tool_bindings:
            return None
        gate = self._governing_of(task.id, governing, approvals_by_id)
        if gate is None:
            return None
        if any(approval.status != ApprovalStatus.approved for approval in gate):
            return None
        # A merge can be governed by several approvals at once, and a
        # certificate names exactly one grantor. The oldest is chosen so the
        # attribution is deterministic rather than dependent on query order;
        # the policy layer independently re-checks that *every* governing
        # approval still stands, so which one is named does not weaken the gate.
        approval = min(gate, key=lambda item: item.id) if gate else None
        if approval is None and initiator_id is None:
            return None

        live = await self._certificates.list_live_for_task(task.id)
        approval_id = approval.id if approval is not None else None
        if any(certificate.approval_id == approval_id for certificate in live):
            # The task already holds this authority's grant. Signing another
            # would rotate the key and the frozen tool set underneath a task
            # that may already be calling against them.
            return None
        for certificate in live:
            await self._certificates.revoke(
                certificate.id,
                RevocationReason.superseded_by_approval,
                user_id=user_id,
            )

        if approval is not None:
            binding = CertificateBinding(
                tenant_id=tenant_id,
                execution_id=execution_id,
                task_id=task.id,
                approval_id=approval.id,
            )
            grant_kind = CertificateGrant.approval
            granted_by = approval.decided_by or user_id
        else:
            # ``initiator_id`` is not None here -- checked above.
            binding = CertificateBinding(
                tenant_id=tenant_id,
                execution_id=execution_id,
                task_id=task.id,
                initiator_id=initiator_id,
            )
            grant_kind = CertificateGrant.initiator
            granted_by = initiator_id or ""

        return await self._sign_and_store(
            task=task,
            tenant_id=tenant_id,
            binding=binding,
            grant_kind=grant_kind,
            approval_id=approval_id,
            granted_by=granted_by,
            # Anchored on now for both grantors: the task starting is the moment
            # the authority is taken, and measuring an approval's window from
            # its decision instead would make a long chain of covered tasks race
            # a single TTL.
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

    async def supersede_grants_for(
        self, workflow_task_ids: Sequence[str], *, user_id: str
    ) -> None:
        """Stand down every grant the given tasks hold, for a new approval's sake.

        Called when an approval is requested: from that moment the approval
        governs its own task and everything downstream of it up to the next
        approval, and whatever authority those tasks were running on no longer
        speaks for them. That is the run initiator's own grant for a task that
        had already started, and equally an *outer* approval's grant for a task
        a nearer request has just claimed.

        The gate does not depend on it. ``TaskCertificatePolicy`` re-derives the
        governing approval on every call and refuses a certificate that does not
        match it, whether or not the row was stamped. What this adds is that the
        audit trail shows one live authority per task instead of two overlapping
        ones.

        Args:
            workflow_task_ids: The tasks whose grants should stand down.
            user_id: The acting user, recorded as ``updated_by``.
        """
        for task_id in workflow_task_ids:
            for certificate in await self._certificates.list_live_for_task(task_id):
                await self._certificates.revoke(
                    certificate.id,
                    RevocationReason.superseded_by_approval,
                    user_id=user_id,
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

    async def list_for_approval(self, approval_id: str) -> list[McpToolCertificateRead]:
        """Return the public view of every certificate issued under an approval.

        Plural because an approval covers the task it names *and* every task
        downstream of it up to the next approval, each of which is granted its
        own certificate when it starts -- so the set grows as the run advances,
        and is empty until the first covered task starts. An empty result is an
        ordinary state, not a missing record, which is why this does not raise.

        The granted tools are parsed back out of each signed certificate rather
        than read from a separate column, so the API can never report a grant
        that differs from what the certificate actually says.

        Args:
            approval_id: The approval whose certificates to read.

        Returns:
            The read views, newest first, including the granted tools.

        Raises:
            CertificateVerificationError: If a stored certificate is
                unparseable or carries claims that do not fit the grammar.
        """
        certificates = await self._certificates.list_for_approval(approval_id)
        return [_to_read(certificate) for certificate in certificates]

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
