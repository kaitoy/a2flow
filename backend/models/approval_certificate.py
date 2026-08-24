"""The X.509 certificate issued when an approval on a workflow task is granted.

One row per approval, created by :class:`services.approval_certificate.ApprovalCertificateService`
the moment an approver decides ``approved`` on an approval that names a task.
:class:`infrastructure.mcp_policies.ApprovedTaskCertificatePolicy` then requires
it on every MCP ``call_tool`` that belongs to that task: without a valid
certificate the call is denied, which is what makes the approval gate a server
rule rather than an instruction the agent is asked to follow.

The certificate's ``subjectAltName`` carries the tools the approval granted,
snapshotted from the task's ``tool_bindings`` at decision time (see
:mod:`infrastructure.mcp_certificate` for the URN grammar). That snapshot is the
point: the execution agent can rewrite a task's bindings mid-run through
``update_workflow_task``, but it cannot re-issue the certificate, so rewriting
them cannot widen what it may call.

``private_key_encrypted`` follows the write-only pattern of
:attr:`models.system_settings.SystemSettings.smtp_password`: Fernet ciphertext,
encrypted in the service and never by the repository, never serialized to a
client. Responses use :class:`ApprovalCertificateRead`, which replaces it with
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
from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, TZDateTime, iso_z, iso_z_or_none
from models.tenant_scoped import TenantScoped
from models.workflow_task import ToolBinding

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class RevocationReason(StrEnum):
    """Why a certificate stopped being usable before its ``not_after``.

    One member today, because one thing actually revokes: the work the approval
    authorized finishing. An approval cannot be reversed after the fact (it
    leaves ``pending`` exactly once), and a finished run is a run whose tasks
    have each already finished, so neither needs its own reason.
    """

    #: The task the certificate authorizes reached a terminal status
    #: (``completed``, ``failed``, or ``skipped``).
    task_finished = "task_finished"


class ApprovalCertificateCreate(SQLModel):
    """Fields needed to persist a freshly signed approval certificate.

    Written only by :class:`services.approval_certificate.ApprovalCertificateService`;
    no API route accepts this payload.
    """

    model_config = _alias_config

    approval_id: str
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


class ApprovalCertificate(
    ApprovalCertificateCreate, TenantScoped, BaseEntity, table=True
):
    """The certificate issued for one granted approval.

    At most one **live** certificate per approval, enforced by the partial
    unique index ``uq_approval_certificates_live``. It is partial rather than a
    plain unique constraint so a revoked certificate stays in the table: the
    audit trail has to keep showing that authority was granted and when it
    stopped counting, and a re-issue after revocation must still be possible.

    Nothing re-issues today -- an approval leaves ``pending`` exactly once, so a
    revoked certificate is the end of that approval's authority -- but the index
    is partial anyway so that adding a rework-and-re-approve flow later is a
    service-layer change rather than a migration.
    """

    __tablename__ = "approval_certificates"
    __table_args__ = (
        Index(
            "uq_approval_certificates_live",
            "approval_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
    )

    approval_id: str = Field(foreign_key="approvals.id", ondelete="CASCADE")
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


class ApprovalCertificateRead(BaseEntity):
    """Read view of an approval certificate, excluding the private key.

    ``allowed_tools`` is parsed back out of the certificate rather than stored
    alongside it, so the API can never report a grant that differs from what the
    signed certificate actually says.
    """

    model_config = _alias_config

    tenant_id: str
    approval_id: str
    workflow_execution_id: str
    workflow_task_id: str
    ca_id: str
    serial_number: str
    not_before: datetime
    not_after: datetime
    revoked_at: datetime | None = None
    revocation_reason: RevocationReason | None = None
    #: The tools this approval granted, read back out of the certificate.
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
        certificate: ApprovalCertificate,
        *,
        allowed_tools: list[ToolBinding],
    ) -> "ApprovalCertificateRead":
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
