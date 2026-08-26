"""WorkflowPublishedVersion repository: Protocol interface and SQLModel-backed implementation.

Holds the snapshot of a workflow taken at publish time — at most one row per
workflow, replaced wholesale by every publish. There is no ``delete``: the row
disappears with its workflow through the ``ON DELETE CASCADE`` foreign key.
"""

from typing import Any, Protocol

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.workflow_published_version import WorkflowPublishedVersion
from repositories._integrity import commit_or_translate_user_fk


class WorkflowPublishedVersionRepository(Protocol):
    """Interface for WorkflowPublishedVersion persistence operations."""

    async def get(self, workflow_id: str) -> WorkflowPublishedVersion | None: ...

    async def upsert(
        self,
        workflow_id: str,
        *,
        name: str,
        description: str | None,
        templates: list[dict[str, Any]],
        user_id: str,
    ) -> WorkflowPublishedVersion: ...


class SqlWorkflowPublishedVersionRepository:
    """SQLModel-backed implementation of WorkflowPublishedVersionRepository.

    The parent workflow's existence is not re-validated here: the only caller
    is the publish use case, which has already resolved the workflow through
    its own tenant-scoped repository.
    """

    def __init__(self, session: AsyncSession, *, tenant_id: str | None) -> None:
        """Store the session and the tenant every query is scoped to."""
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

    async def _get_scoped(self, workflow_id: str) -> WorkflowPublishedVersion | None:
        """Return the snapshot row of ``workflow_id`` within the current tenant."""
        stmt = select(WorkflowPublishedVersion).where(
            WorkflowPublishedVersion.workflow_id == workflow_id
        )
        if self._tenant_id is not None:
            stmt = stmt.where(WorkflowPublishedVersion.tenant_id == self._tenant_id)
        result = await self._db.exec(stmt)
        return result.first()

    async def get(self, workflow_id: str) -> WorkflowPublishedVersion | None:
        """Return the workflow's last published snapshot, or ``None`` if never published."""
        return await self._get_scoped(workflow_id)

    async def upsert(
        self,
        workflow_id: str,
        *,
        name: str,
        description: str | None,
        templates: list[dict[str, Any]],
        user_id: str,
    ) -> WorkflowPublishedVersion:
        """Record the workflow's current state as its published snapshot.

        Replaces the previous snapshot when one exists, so a workflow never
        accumulates more than one row.

        Args:
            workflow_id: Identifier of the workflow being published.
            name: The workflow's name at publish time.
            description: The workflow's description at publish time.
            templates: The serialized task templates (see
                :func:`models.workflow_published_version.dump_templates`).
            user_id: ID of the user publishing the workflow.

        Returns:
            The stored snapshot.
        """
        tenant_id = self._require_tenant()
        version = await self._get_scoped(workflow_id)
        if version is None:
            version = WorkflowPublishedVersion(
                workflow_id=workflow_id,
                name=name,
                description=description,
                templates=templates,
                tenant_id=tenant_id,
                created_by=user_id,
                updated_by=user_id,
            )
        else:
            version.name = name
            version.description = description
            version.templates = templates
            version.updated_by = user_id
        self._db.add(version)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(version)
        return version
