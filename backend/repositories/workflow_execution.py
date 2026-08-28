"""WorkflowExecution repository: Protocol interface and SQLModel-backed implementation."""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.approval import Approval
from models.workflow_execution import (
    WorkflowExecution,
    WorkflowExecutionCreate,
    WorkflowExecutionStatus,
)
from repositories._integrity import commit_or_translate_user_fk
from repositories.exceptions import NotFoundError
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort


class WorkflowExecutionRepository(Protocol):
    """Interface for WorkflowExecution persistence operations."""

    async def get(self, execution_id: str) -> WorkflowExecution | None: ...

    async def get_by_session_id(self, session_id: str) -> WorkflowExecution | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        visible_to_user_id: str | None = None,
        visible_to_group_ids: Sequence[str] = (),
    ) -> list[WorkflowExecution]: ...

    async def create(
        self,
        data: WorkflowExecutionCreate,
        *,
        workflow_id: str,
        user_id: str,
        is_draft: bool = False,
        tool_mocks: Sequence[dict[str, Any]] = (),
    ) -> WorkflowExecution: ...

    async def next_tool_mock_ordinal(self, execution_id: str, key: str) -> int: ...

    async def commit_shas_for_skill(self, agent_skill_id: str) -> set[str]: ...

    async def mark_finished(
        self,
        execution_id: str,
        *,
        status: WorkflowExecutionStatus,
        finished_at: datetime,
    ) -> None: ...

    async def delete(self, execution_id: str) -> None: ...


class SqlWorkflowExecutionRepository:
    """SQLModel-backed implementation of WorkflowExecutionRepository."""

    def __init__(self, session: AsyncSession, *, tenant_id: str | None) -> None:
        """Store the SQLModel async session and the tenant these queries are scoped to."""
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

    async def _get_scoped(self, execution_id: str) -> WorkflowExecution | None:
        """Return the WorkflowExecution with the given ID within the current tenant, or ``None``."""
        stmt = select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
        if self._tenant_id is not None:
            stmt = stmt.where(WorkflowExecution.tenant_id == self._tenant_id)
        result = await self._db.exec(stmt)
        return result.first()

    async def get(self, execution_id: str) -> WorkflowExecution | None:
        """Return the WorkflowExecution with the given ID, or ``None`` if missing."""
        return await self._get_scoped(execution_id)

    async def get_by_session_id(self, session_id: str) -> WorkflowExecution | None:
        """Return the WorkflowExecution for the given ADK session id, or ``None``.

        The ADK session id (the AG-UI thread id) is stored on
        :attr:`WorkflowExecution.session_id`, which is distinct from the primary
        key. WorkflowTask records reference the primary key, so agent tools use
        this lookup to map the workflow session they run in back to its
        WorkflowExecution PK.

        Args:
            session_id: The ADK session id to look up.

        Returns:
            The matching WorkflowExecution, or ``None`` if no execution has that
            session id.
        """
        stmt = (
            select(WorkflowExecution)
            .where(
                col(WorkflowExecution.session_id) == session_id,
                WorkflowExecution.tenant_id == self._tenant_id,
            )
            .limit(1)
        )
        result = await self._db.exec(stmt)
        return result.first()

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        visible_to_user_id: str | None = None,
        visible_to_group_ids: Sequence[str] = (),
    ) -> list[WorkflowExecution]:
        """Return WorkflowExecutions, defaulting to ``created_at`` descending (newest first).

        Args:
            limit: Maximum number of records.
            offset: Number of records to skip.
            sort: Sort specifications; defaults to ``created_at`` descending.
            filters: Filter specifications applied as a conjunction.
            visible_to_user_id: If given, restricts results to executions this
                user initiated or is a designated approver of (any approval
                status); ``None`` (the default) returns every execution in the
                tenant, unscoped.
            visible_to_group_ids: The groups the caller counts as an eligible
                approver for, already role-filtered by
                :class:`services.approver_groups.ApproverGroupResolver`. An
                execution holding an approval addressed to one of them is
                visible for the same reason a directly addressed one is.
                Ignored when ``visible_to_user_id`` is ``None``.

        Returns:
            The matching executions.
        """
        stmt = select(WorkflowExecution)
        if self._tenant_id is not None:
            stmt = stmt.where(WorkflowExecution.tenant_id == self._tenant_id)
        if visible_to_user_id is not None:
            addressed_to = [col(Approval.approver) == visible_to_user_id]
            if visible_to_group_ids:
                addressed_to.append(
                    col(Approval.approver_group_id).in_(list(visible_to_group_ids))
                )
            stmt = stmt.where(
                or_(
                    col(WorkflowExecution.initiator_id) == visible_to_user_id,
                    col(WorkflowExecution.id).in_(
                        select(Approval.workflow_execution_id).where(
                            or_(*addressed_to),
                            Approval.tenant_id == self._tenant_id,
                        )
                    ),
                )
            )
        stmt = apply_filters(
            stmt, WorkflowExecution, filters, readable=WorkflowExecution
        )
        stmt = apply_sort(
            stmt,
            WorkflowExecution,
            sort,
            default=[col(WorkflowExecution.created_at).desc()],
            readable=WorkflowExecution,
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(
        self,
        data: WorkflowExecutionCreate,
        *,
        workflow_id: str,
        user_id: str,
        is_draft: bool = False,
        tool_mocks: Sequence[dict[str, Any]] = (),
    ) -> WorkflowExecution:
        """Persist a new WorkflowExecution with audit fields populated.

        Args:
            data: The API-supplied snapshot of workflow and skill metadata.
            workflow_id: The workflow this run belongs to.
            user_id: The acting user, written to the audit columns.
            is_draft: Whether the workflow was still ``draft`` when the run
                started — a pre-publish test run. Server-set, like
                ``workflow_id``; recorded so ``repositories/metrics.py`` can
                exclude the run from the operations metrics.
            tool_mocks: Snapshot of the tool mocks this run should apply, taken
                at start time so later edits to the mock records cannot change
                how the run behaves. Server-set for the same reason as
                ``is_draft``, and only ever non-empty for a draft run.

        Returns:
            The persisted WorkflowExecution.
        """
        execution = WorkflowExecution.model_validate(
            {
                **data.model_dump(),
                "workflow_id": workflow_id,
                "is_draft": is_draft,
                "tool_mocks": list(tool_mocks),
                "tenant_id": self._require_tenant(),
                "created_by": user_id,
                "updated_by": user_id,
            }
        )
        self._db.add(execution)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(execution)
        return execution

    async def next_tool_mock_ordinal(self, execution_id: str, key: str) -> int:
        """Increment and return the call count for one mocked tool of a run.

        The counter is what selects a mock's per-ordinal response, so it has to
        survive the process: an agent run spans many HTTP requests and may move
        between replicas. It is stored on the run rather than in memory for that
        reason, and committed immediately so the next call sees it.

        Concurrent calls within one run cannot race: agent runs for a session are
        serialized by the advisory lock in :mod:`infrastructure.locks`.

        Args:
            execution_id: Primary key of the run whose counter to advance.
            key: ``"<server_id or 'builtin'>:<tool_name>"``, identifying the
                mocked tool within the run.

        Returns:
            The 1-based ordinal of this call.

        Raises:
            NotFoundError: If no execution exists with the given ID in this tenant.
        """
        self._require_tenant()
        execution = await self._get_scoped(execution_id)
        if execution is None:
            raise NotFoundError("WorkflowExecution", execution_id)
        # Rebound rather than mutated in place: SQLAlchemy does not track
        # mutation of a plain JSON column's contents, so an in-place increment
        # would never be flushed.
        counts = dict(execution.tool_mock_calls)
        ordinal = counts.get(key, 0) + 1
        counts[key] = ordinal
        execution.tool_mock_calls = counts
        self._db.add(execution)
        await self._db.commit()
        return ordinal

    async def commit_shas_for_skill(self, agent_skill_id: str) -> set[str]:
        """Return every skill revision that executions of this skill are pinned to.

        These are the revisions a prune of the skill store must keep: each one
        is the code some WorkflowExecution started against and will keep loading
        on its next agent run. Rows predating the revisioned store have a NULL
        sha and contribute nothing.

        Args:
            agent_skill_id: Identifier of the skill whose executions to scan.

        Returns:
            The set of pinned commit shas.
        """
        stmt = select(WorkflowExecution.agent_skill_commit_sha).where(
            col(WorkflowExecution.agent_skill_id) == agent_skill_id,
            col(WorkflowExecution.agent_skill_commit_sha).is_not(None),
            WorkflowExecution.tenant_id == self._tenant_id,
        )
        result = await self._db.exec(stmt)
        return {sha for sha in result.all() if sha is not None}

    async def mark_finished(
        self,
        execution_id: str,
        *,
        status: WorkflowExecutionStatus,
        finished_at: datetime,
    ) -> None:
        """Stamp a run's terminal status and completion time.

        ``status`` and ``finished_at`` are server-managed, so they are written
        only here and never through the generic create/update path — the same
        arrangement as :meth:`repositories.workflow.SqlWorkflowRepository.mark_design_edited`.

        The write is idempotent: a run whose ``finished_at`` is already set is
        left untouched, so a later task write cannot move a recorded completion
        time. A missing (or cross-tenant) execution is a no-op rather than an
        error, because the caller is the best-effort completion evaluation that
        runs after every task write.

        Args:
            execution_id: Primary key of the execution to stamp.
            status: The terminal status to record.
            finished_at: The moment the run finished.
        """
        self._require_tenant()
        execution = await self._get_scoped(execution_id)
        if execution is None or execution.finished_at is not None:
            return
        execution.status = status
        execution.finished_at = finished_at
        self._db.add(execution)
        await self._db.commit()

    async def delete(self, execution_id: str) -> None:
        """Delete the WorkflowExecution with the given ID, raising NotFoundError if missing."""
        self._require_tenant()
        execution = await self._get_scoped(execution_id)
        if execution is None:
            raise NotFoundError("WorkflowExecution", execution_id)
        await self._db.delete(execution)
        await self._db.commit()
