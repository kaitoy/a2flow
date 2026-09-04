"""The X.509 certificate that authorizes one workflow task's MCP tool calls.

:class:`infrastructure.mcp_policies.TaskCertificatePolicy` requires one on
**every** proxied ``call_tool``: without a valid certificate the call is denied,
which is what makes tool authority a server rule rather than an instruction the
agent is asked to follow. A row is created by
:class:`services.mcp_tool_certificate.McpToolCertificateService` through one of
two paths, recorded in :attr:`McpToolCertificate.grant_kind`:

``approval``
    An approver decided ``approved`` on an approval naming the task. The
    certificate is minted at that moment and ``approval_id`` names the decision.

``initiator``
    Nobody was asked to approve the task, so the run's own initiator -- the
    person who executed the workflow -- grants its bound tools to themselves.
    The certificate is minted when the task goes ``in_progress``, and
    ``approval_id`` is ``NULL``.

Which path applies is not the agent's choice: a task that has an approval
attached can only be authorized by that approval's certificate, so a run cannot
take out an initiator grant first and then request the approval it was meant to
wait for. ``granted_by`` records the human behind either path -- the deciding
approver, or the run's initiator.

The certificate's ``subjectAltName`` carries the tools the grant covers,
snapshotted from the task's ``tool_bindings`` at issuance (see
:mod:`infrastructure.mcp_certificate` for the URN grammar). That snapshot is the
point, and it is what makes both paths equally binding: a run's tasks and their
``tool_bindings`` come from the workflow's published templates copied at execute
time and the execution agent cannot edit them, and even a later edit to the
workflow cannot re-issue a certificate already granted, so nothing widens what a
task may call once its grant is set.

``private_key_encrypted`` follows the write-only pattern of
:attr:`models.system_settings.SystemSettings.smtp_password`: Fernet ciphertext,
encrypted in the service and never by the repository, never serialized to a
client. Responses use :class:`McpToolCertificateRead`, which replaces it with
the public claims read back out of the certificate.

Revocation is recorded here but is not the only stop: verification also
re-reads the approval's current status and the task's current status on every
call, so an approval reversed after issuance is refused even if nothing got
around to stamping ``revoked_at``. The column exists so the audit trail shows
*why* a certificate stopped being usable, and so the common cases short-circuit
before the more expensive checks.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import field_serializer
from pydantic.alias_generators import to_camel
from sqlalchemy import CheckConstraint, Index, text
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, TZDateTime, iso_z, iso_z_or_none
from models.tenant_scoped import TenantScoped
from models.workflow_task import ToolBinding

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class CertificateGrant(StrEnum):
    """Where a certificate's authority came from.

    Declared in the order the two paths rank by scrutiny, since
    ``repositories/query.py`` sorts an enum column by declaration position: an
    approval a human weighed sorts before a grant the initiator gave themselves,
    which is the order an auditor scanning the list wants.
    """

    #: An approver decided ``approved`` on an approval naming the task.
    #: ``approval_id`` names that decision.
    approval = "approval"

    #: The run's initiator granted the task's bound tools to themselves, because
    #: nobody was asked to approve the task. ``approval_id`` is ``NULL``.
    initiator = "initiator"


class RevocationReason(StrEnum):
    """Why a certificate stopped being usable before its ``not_after``.

    Two members, one per thing that actually revokes: the work a certificate
    authorized finishing, and an initiator grant being displaced by a real
    approval. An approval cannot be reversed after the fact (it leaves
    ``pending`` exactly once), and a finished run is a run whose tasks have each
    already finished, so neither needs its own reason.
    """

    #: The task the certificate authorizes reached a terminal status
    #: (``completed``, ``failed``, or ``skipped``).
    task_finished = "task_finished"

    #: An approval was attached to the task the certificate authorizes, so the
    #: initiator's own grant stepped aside for the approver's. Only ever stamped
    #: on a ``grant_kind="initiator"`` certificate.
    superseded_by_approval = "superseded_by_approval"


class McpToolCertificateCreate(SQLModel):
    """Fields needed to persist a freshly signed tool certificate.

    Written only by :class:`services.mcp_tool_certificate.McpToolCertificateService`;
    no API route accepts this payload.
    """

    model_config = _alias_config

    #: Which of the two issuance paths minted this certificate.
    grant_kind: CertificateGrant
    #: The decision this certificate carries, or ``None`` for an initiator
    #: grant. Kept consistent with ``grant_kind`` by
    #: ``ck_mcp_tool_certificates_grant_shape``.
    approval_id: str | None = None
    #: The human the authority came from: the deciding approver, or the run's
    #: initiator. Recorded here rather than derived so a single column answers
    #: "who authorized this" for both paths.
    granted_by: str
    workflow_execution_id: str
    workflow_task_id: str
    ca_id: str
    #: Decimal string of the X.509 serial. Stored as text because a 20-byte
    #: serial does not fit a 64-bit integer column.
    serial_number: str
    certificate_pem: str
    #: Fernet ciphertext of the leaf's PKCS#8 private key. Never serialized.
    private_key_encrypted: str
    not_before: datetime
    not_after: datetime


class McpToolCertificate(
    McpToolCertificateCreate, TenantScoped, BaseEntity, table=True
):
    """The certificate authorizing one task's MCP tool calls.

    At most one **live** certificate per approval, enforced by the partial
    unique index ``uq_mcp_tool_certificates_live``, and at most one live
    *initiator* grant per task, enforced by
    ``uq_mcp_tool_certificates_live_initiator``. Both are partial rather than
    plain unique constraints so a revoked certificate stays in the table: the
    audit trail has to keep showing that authority was granted and when it
    stopped counting, and a re-issue after revocation must still be possible.

    The two indexes do not overlap. ``approval_id`` is ``NULL`` on every
    initiator grant, and NULLs never collide in a unique index on either
    dialect, so those rows pass straight through the first one and are caught by
    the second instead.

    Re-issuing an *approval* grant does not happen today -- an approval leaves
    ``pending`` exactly once, so a revoked certificate is the end of that
    approval's authority -- but the index is partial anyway so that adding a
    rework-and-re-approve flow later is a service-layer change rather than a
    migration. An initiator grant genuinely is re-issued: a task returned to
    ``pending`` and started again gets a fresh one once its first was revoked.
    """

    __tablename__ = "mcp_tool_certificates"
    __table_args__ = (
        Index(
            "uq_mcp_tool_certificates_live",
            "approval_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
        Index(
            "uq_mcp_tool_certificates_live_initiator",
            "workflow_task_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL AND approval_id IS NULL"),
            sqlite_where=text("revoked_at IS NULL AND approval_id IS NULL"),
        ),
        CheckConstraint(
            "(grant_kind = 'approval' AND approval_id IS NOT NULL)"
            " OR (grant_kind = 'initiator' AND approval_id IS NULL)",
            name="ck_mcp_tool_certificates_grant_shape",
        ),
    )

    #: Named ``grant_kind`` rather than ``grant`` because ``GRANT`` is a
    #: reserved word in SQL: leaving it unquoted would depend on every dialect
    #: and every hand-written constraint quoting it the same way.
    grant_kind: CertificateGrant
    approval_id: str | None = Field(
        default=None, foreign_key="approvals.id", ondelete="CASCADE"
    )
    #: RESTRICT, matching the audit user FKs on :class:`~models.base.BaseEntity`:
    #: the person a grant is attributed to cannot be hard-deleted out from under
    #: the certificate recording it.
    granted_by: str = Field(foreign_key="users.id", ondelete="RESTRICT")
    workflow_execution_id: str = Field(
        foreign_key="workflow_executions.id", ondelete="CASCADE", index=True
    )
    workflow_task_id: str = Field(
        foreign_key="workflow_tasks.id", ondelete="CASCADE", index=True
    )
    #: RESTRICT, not CASCADE: a root that signed a certificate must stay in the
    #: table so the certificate remains verifiable.
    ca_id: str = Field(
        foreign_key="mcp_certificate_authorities.id", ondelete="RESTRICT"
    )
    serial_number: str = Field(unique=True, index=True)
    not_before: datetime = Field(sa_type=TZDateTime)
    not_after: datetime = Field(sa_type=TZDateTime)
    revoked_at: datetime | None = Field(default=None, sa_type=TZDateTime)
    revocation_reason: RevocationReason | None = Field(default=None)

    @field_serializer("not_before", "not_after", when_used="json")
    def _serialize_validity(self, dt: datetime) -> str:
        """Serialize the validity window as ISO-8601 with a Z suffix."""
        return iso_z(dt)

    @field_serializer("revoked_at", when_used="json")
    def _serialize_revoked_at(self, dt: datetime | None) -> str | None:
        """Serialize the revocation instant, passing ``None`` through."""
        return iso_z_or_none(dt)


class McpToolCertificateRead(BaseEntity):
    """Read view of a tool certificate, excluding the private key.

    ``allowed_tools`` is parsed back out of the certificate rather than stored
    alongside it, so the API can never report a grant that differs from what the
    signed certificate actually says.
    """

    model_config = _alias_config

    tenant_id: str
    grant_kind: CertificateGrant
    #: Declared without a default even though it is nullable: a default would
    #: make it *optional* in the generated OpenAPI schema, and the endpoint
    #: always sends the key -- it is the value that can be null, for an
    #: initiator grant. Same reasoning as ``allowed_tools`` below.
    approval_id: str | None
    granted_by: str
    workflow_execution_id: str
    workflow_task_id: str
    ca_id: str
    serial_number: str
    not_before: datetime
    not_after: datetime
    revoked_at: datetime | None = None
    revocation_reason: RevocationReason | None = None
    #: The tools this certificate grants, read back out of it.
    #: Required, not defaulted: a defaulted field becomes optional in the
    #: generated OpenAPI schema, which would make every frontend consumer
    #: null-check a list the endpoint always sends.
    allowed_tools: list[ToolBinding]

    @field_serializer("not_before", "not_after", when_used="json")
    def _serialize_validity(self, dt: datetime) -> str:
        """Serialize the validity window as ISO-8601 with a Z suffix."""
        return iso_z(dt)

    @field_serializer("revoked_at", when_used="json")
    def _serialize_revoked_at(self, dt: datetime | None) -> str | None:
        """Serialize the revocation instant, passing ``None`` through."""
        return iso_z_or_none(dt)

    @classmethod
    def from_certificate(
        cls,
        certificate: McpToolCertificate,
        *,
        allowed_tools: list[ToolBinding],
    ) -> "McpToolCertificateRead":
        """Build the read view, dropping the private key and the PEM.

        Args:
            certificate: The persisted certificate row.
            allowed_tools: Grants parsed from the certificate by
                :func:`infrastructure.mcp_certificate.extract_claims`.

        Returns:
            A read view carrying the public claims only.
        """
        return cls(
            **certificate.model_dump(
                exclude={"private_key_encrypted", "certificate_pem"}
            ),
            allowed_tools=allowed_tools,
        )
