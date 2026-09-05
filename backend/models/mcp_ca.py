"""The internal certificate authority that signs MCP approval certificates.

A2Flow issues one short-lived X.509 certificate per approved workflow task (see
:mod:`models.mcp_tool_certificate`) and requires it on every MCP ``call_tool``
that belongs to an approved task. Those certificates need an issuer, and this
table holds it: a self-signed root whose private key never leaves the backend.

**One root for the whole platform, not one per tenant.** A tenant-scoped CA
would add a key per tenant without adding a boundary: verification already
compares the tenant recorded in the certificate's ``subjectAltName`` binding
URN against the tenant the gateway independently derived from the ADK session id
(:func:`repositories.tenant_bootstrap.resolve_workflow_execution_tenant`), so a
certificate minted for tenant A is rejected in tenant B on the binding check
regardless of which key signed it. Splitting the CA would only multiply the
key material an attacker could target, so the row is platform-scoped —
inheriting :class:`~models.base.BaseEntity` alone, the same shape as
:class:`models.system_settings.SystemSettings`.

``private_key_encrypted`` follows the write-only pattern of
:attr:`models.system_settings.SystemSettings.smtp_password`: Fernet ciphertext
produced by :func:`infrastructure.secret_cipher.get_secret_cipher`, encrypted in
:mod:`infrastructure.mcp_ca` and never by the repository, and never serialized
to any client. There is no read DTO because no route exposes a CA row; the
public half is reachable through ``certificate_pem`` alone.

Rotation is deliberately out of scope for this version. The ``active`` flag and
the ``ca_id`` foreign key on :class:`models.mcp_tool_certificate.McpToolCertificate`
exist so a superseded root can be retired while the certificates it signed stay
verifiable, but nothing writes a second row yet.
"""

from datetime import datetime

from pydantic import field_serializer
from pydantic.alias_generators import to_camel
from sqlalchemy import Index, text
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity, TZDateTime, iso_z
from models.constraints import ShortText

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)


class McpCertificateAuthorityCreate(SQLModel):
    """Fields needed to persist a freshly generated root CA.

    Written only by :mod:`infrastructure.mcp_ca`; there is no API route that
    accepts this payload.
    """

    model_config = _alias_config

    #: Subject/issuer common name of the self-signed root.
    common_name: ShortText
    #: PEM-encoded self-signed root certificate. Public material.
    certificate_pem: str
    #: Fernet ciphertext of the PEM-encoded PKCS#8 private key. Never serialized.
    private_key_encrypted: str
    not_before: datetime
    not_after: datetime


class MCPCertificateAuthority(McpCertificateAuthorityCreate, BaseEntity, table=True):
    """The platform's self-signed root CA for MCP approval certificates.

    Not tenant-scoped: one root serves every tenant (see the module docstring).
    At most one row has ``active`` true, enforced by the partial unique index
    ``uq_mcp_certificate_authorities_active``, which is what makes
    "generate the root on first use" safe under concurrent startup on multiple
    replicas — the loser of the race gets an ``IntegrityError`` and re-reads.
    """

    __tablename__ = "mcp_certificate_authorities"
    __table_args__ = (
        # Partial rather than a plain unique index: retired roots keep their
        # rows so the certificates they signed stay verifiable, but only one
        # may be active. Declared here as well as in the Alembic revision
        # because tests build their schema with ``SQLModel.metadata.create_all``
        # and would otherwise run without the constraint the race relies on.
        Index(
            "uq_mcp_certificate_authorities_active",
            "active",
            unique=True,
            sqlite_where=text("active"),
            postgresql_where=text("active"),
        ),
    )

    not_before: datetime = Field(sa_type=TZDateTime)
    not_after: datetime = Field(sa_type=TZDateTime)
    #: Whether this root is the one new certificates are signed with. Retired
    #: roots stay in the table so the certificates they signed remain verifiable.
    active: bool = Field(default=True)

    @field_serializer("not_before", "not_after", when_used="json")
    def _serialize_validity(self, dt: datetime) -> str:
        """Serialize the validity window as ISO-8601 with a Z suffix."""
        return iso_z(dt)
