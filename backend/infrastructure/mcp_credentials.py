"""The caller side of the approval-certificate exchange: presenting one.

:mod:`infrastructure.mcp_proxy` and :mod:`infrastructure.mcp_policies` are the
*verifier*. This module is the *presenter*: it finds the certificate that
covers the call the agent is about to make, signs a proof-of-possession
challenge with that certificate's private key, and hands both to the proxy.

**Why it lives outside the proxy.** Today verifier and presenter run in one
process against one database, so the split is a boundary in the code rather
than in the deployment -- and the proof of possession accordingly proves
nothing an attacker who owns this process could not also forge. The split is
still where the value is: it is the shape the system takes when the proxy is
lifted to an HTTP endpoint, at which point this module is what remains on the
agent's side of the wire and the signature starts carrying real weight. Keeping
the two apart now means that lift does not have to disentangle them.

**The LLM never sees any of this.** No certificate, key, signature, or nonce
appears in a tool argument or a tool result. The model asks to call a tool; the
authority that lets it happen is attached underneath, out of its reach, and it
learns only whether the call was allowed.

**Choosing among a run's certificates.** The agent tool knows a session id and
a target tool, not a task id. So the provider takes every live certificate in
the run and prefers one whose signed grant covers the target. When none does it
still presents one, so the denial the caller gets back says "that tool is not
granted" rather than the far less useful "no certificate".
"""

import logging
import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure import database
from infrastructure.mcp_ca import (
    McpCaError,
    certificate_from_pem,
    private_key_from_pem,
)
from infrastructure.mcp_certificate import (
    CertificateVerificationError,
    extract_claims,
    pop_digest,
    sign_pop_digest,
)
from infrastructure.mcp_proxy import McpClientCredential
from infrastructure.secret_cipher import SecretCipher, get_secret_cipher
from models.approval_certificate import ApprovalCertificate
from repositories.approval_certificate import SqlApprovalCertificateRepository
from repositories.tenant_bootstrap import resolve_workflow_execution_tenant

logger = logging.getLogger(__name__)

#: Bytes of randomness in the per-call nonce.
_NONCE_BYTES = 16

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


@asynccontextmanager
async def _default_session() -> AsyncIterator[AsyncSession]:
    """Open a session on the application engine.

    Referenced through the :mod:`infrastructure.database` module rather than by
    importing ``engine`` directly so a test can monkeypatch ``database.engine``
    -- the same reason :class:`infrastructure.mcp_proxy.McpProxy` does it.
    """
    async with AsyncSession(database.engine) as session:
        yield session


class ApprovalCredentialProvider:
    """Builds the credential a proxied tool call presents, when one exists."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory | None = None,
        cipher: SecretCipher | None = None,
    ) -> None:
        """Initialize the provider.

        Args:
            session_factory: Opens the database session used to find the
                certificate. Defaults to a session on the application engine.
            cipher: Decrypts the stored private key. Defaults to the
                process-wide cipher.
        """
        self._session_factory = session_factory or _default_session
        self._cipher = cipher or get_secret_cipher()

    async def credential_for(
        self,
        *,
        session_id: str,
        mcp_server_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> McpClientCredential | None:
        """Return the credential backing this call, or ``None`` if there is none.

        Returning ``None`` is not a failure: a task with no approval attached
        has no certificate, and the policy layer allows those calls under the
        ordinary tool-binding rule. It is the policy layer, not this one, that
        decides whether a missing credential is fatal.

        Args:
            session_id: The ADK session the call belongs to.
            mcp_server_id: Id of the registered MCP server being called.
            tool_name: Name of the tool being called.
            arguments: The call's arguments, covered by the signature.

        Returns:
            The credential to present, or ``None``.
        """
        certificate = await self._find(session_id, mcp_server_id, tool_name)
        if certificate is None:
            return None

        try:
            key = private_key_from_pem(
                self._cipher.decrypt(certificate.private_key_encrypted)
            )
        except (ValueError, McpCaError):
            # A rotated Fernet key or a corrupt row. Presenting nothing gets a
            # clean denial from the policy layer; the detail stays in the log
            # rather than travelling back to the model.
            logger.warning(
                "Cannot load the private key of approval certificate %s; "
                "proceeding without a credential",
                certificate.id,
                exc_info=True,
            )
            return None

        nonce = secrets.token_urlsafe(_NONCE_BYTES)
        timestamp = datetime.now(UTC)
        digest = pop_digest(
            session_id=session_id,
            mcp_server_id=mcp_server_id,
            tool_name=tool_name,
            arguments=arguments,
            nonce=nonce,
            timestamp=timestamp,
        )
        return McpClientCredential(
            certificate_pem=certificate.certificate_pem,
            signature=sign_pop_digest(key, digest),
            nonce=nonce,
            timestamp=timestamp,
        )

    async def _find(
        self, session_id: str, mcp_server_id: str, tool_name: str
    ) -> ApprovalCertificate | None:
        """Pick the run's live certificate that best covers the target tool.

        Args:
            session_id: The ADK session the call belongs to.
            mcp_server_id: Id of the registered MCP server being called.
            tool_name: Name of the tool being called.

        Returns:
            The chosen certificate, or ``None`` when the session maps to no run
            or the run has no live certificate.
        """
        async with self._session_factory() as db:
            resolved = await resolve_workflow_execution_tenant(db, session_id)
            if resolved is None:
                return None
            execution_id, tenant_id = resolved
            repo = SqlApprovalCertificateRepository(db, tenant_id=tenant_id)
            candidates = await repo.list_live_for_execution(execution_id)

        if not candidates:
            return None
        for candidate in candidates:
            try:
                claims = extract_claims(certificate_from_pem(candidate.certificate_pem))
            except (McpCaError, CertificateVerificationError):
                logger.warning(
                    "Approval certificate %s is unreadable; skipping it when "
                    "choosing a credential",
                    candidate.id,
                    exc_info=True,
                )
                continue
            if claims.grants(mcp_server_id, tool_name):
                return candidate
        return candidates[0]


@lru_cache(maxsize=1)
def get_approval_credential_provider() -> ApprovalCredentialProvider:
    """Return the process-wide credential provider.

    Cached here rather than in :mod:`dependencies.singletons` for the same
    reason :func:`infrastructure.mcp_proxy.get_mcp_proxy` is: the agent tool
    path must reach it without importing the dependencies package, which would
    cycle back through :mod:`infrastructure.agent`.

    Note for tests: this is ``lru_cache``d, so a test that needs a different
    session factory or cipher must construct
    :class:`ApprovalCredentialProvider` directly or call
    ``get_approval_credential_provider.cache_clear()``.
    """
    return ApprovalCredentialProvider()
