"""WorkflowPublishedVersion repository: Protocol interface and SQLModel-backed implementation.

Holds the snapshots of a workflow taken at publish time — one row per publish,
numbered by ``version``. Everything that means "the published snapshot"
(:meth:`~SqlWorkflowPublishedVersionRepository.get`, ``get_many``,
``list_templates``) reads only the latest row, through
:func:`models.workflow_published_version.latest_version_clause`; the rest of the
history is reached through ``list_versions`` and ``get_version``. There is no
``delete``: the rows disappear with their workflow through the
``ON DELETE CASCADE`` foreign key.

:meth:`SqlWorkflowPublishedVersionRepository.list_templates` reads *into* the
snapshot's JSON ``templates`` column, because a non-``developer`` browsing a
``modified`` workflow's task templates gets that list instead of the live rows
and must still be able to page, filter, and sort it. That work belongs in the
database like every other list query -- doing it in Python would break paging
and let two filter implementations drift apart -- so the JSON array is expanded
into rows by the dialect's own table-valued function. Only two things differ
between dialects, and :meth:`_template_query` is the one place that knows it.
"""

from collections.abc import Sequence
from typing import Any, Protocol

from sqlalchemy import Integer, Text, column, func, literal, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import col, select

from models.workflow_published_version import (
    WorkflowPublishedVersion,
    WorkflowPublishedVersionTemplate,
    WorkflowVersionRead,
    latest_version_clause,
)
from models.workflow_task_template import (
    WorkflowTaskTemplate,
    WorkflowTaskTemplateRead,
)
from repositories._integrity import commit_or_translate_user_fk
from repositories._scoped import TenantScopedRepository
from repositories.query import (
    ColumnOverride,
    FilterSpec,
    SortSpec,
    apply_filters,
    apply_sort,
)


class WorkflowPublishedVersionRepository(Protocol):
    """Interface for WorkflowPublishedVersion persistence operations."""

    async def get(self, workflow_id: str) -> WorkflowPublishedVersion | None: ...

    async def get_many(
        self, workflow_ids: Sequence[str]
    ) -> dict[str, WorkflowPublishedVersion]: ...

    async def list_templates(
        self,
        workflow_id: str,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[WorkflowPublishedVersionTemplate]: ...

    async def list_versions(
        self,
        workflow_id: str,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[WorkflowPublishedVersion]: ...

    async def get_version(
        self, workflow_id: str, version: int
    ) -> WorkflowPublishedVersion | None: ...

    async def create(
        self,
        workflow_id: str,
        *,
        name: str,
        description: str | None,
        templates: list[dict[str, Any]],
        user_id: str,
    ) -> WorkflowPublishedVersion: ...


class SqlWorkflowPublishedVersionRepository(
    TenantScopedRepository[WorkflowPublishedVersion]
):
    """SQLModel-backed implementation of WorkflowPublishedVersionRepository.

    The parent workflow's existence is not re-validated here: the only caller
    is the publish use case, which has already resolved the workflow through
    its own tenant-scoped repository.
    """

    model = WorkflowPublishedVersion

    async def _get_scoped(self, workflow_id: str) -> WorkflowPublishedVersion | None:
        """Return the latest snapshot row of ``workflow_id`` within the current tenant."""
        stmt = select(WorkflowPublishedVersion).where(
            WorkflowPublishedVersion.workflow_id == workflow_id,
            latest_version_clause(WorkflowPublishedVersion),
        )
        stmt = self._scoped(stmt)
        result = await self._db.exec(stmt)
        return result.first()

    async def get(self, workflow_id: str) -> WorkflowPublishedVersion | None:
        """Return the workflow's latest published snapshot, or ``None`` if never published."""
        return await self._get_scoped(workflow_id)

    async def get_many(
        self, workflow_ids: Sequence[str]
    ) -> dict[str, WorkflowPublishedVersion]:
        """Return the latest snapshots of the given workflows, keyed by workflow id.

        Exists so projecting a page of workflows into the published view a
        non-``developer`` sees costs one query rather than one per row.

        Args:
            workflow_ids: The workflows whose snapshots to read. Ids without a
                snapshot are simply absent from the result.

        Returns:
            The snapshots found, keyed by ``workflow_id``.
        """
        if not workflow_ids:
            return {}
        stmt = select(WorkflowPublishedVersion).where(
            col(WorkflowPublishedVersion.workflow_id).in_(list(workflow_ids)),
            latest_version_clause(WorkflowPublishedVersion),
        )
        stmt = self._scoped(stmt)
        result = await self._db.exec(stmt)
        return {v.workflow_id: v for v in result.all()}

    def _template_query(
        self, workflow_id: str
    ) -> tuple[Any, Any, dict[str, ColumnOverride], Any]:
        """Build the expanded-array FROM clause for this dialect's JSON support.

        The snapshot stores its task templates as one JSON array, so listing
        them means turning that array into rows. PostgreSQL and SQLite spell
        that differently, and this is the only place that difference lives:

        =============== ================================== =======================
        \\               PostgreSQL                         SQLite
        =============== ================================== =======================
        expand          ``jsonb_array_elements(...)``       ``json_each(...)``
                        ``WITH ORDINALITY``
        read a field    ``value ->> 'title'``               ``json_extract(value,``
                                                            ``'$.title')``
        stored order    the ordinality column               the ``key`` column
        =============== ================================== =======================

        Both expand a column of the row being joined to, so the PostgreSQL side
        is marked ``LATERAL`` explicitly; SQLite has no such keyword and needs
        none. Either way the element is joined on a true condition rather than
        left as a second FROM item, which is the same thing to the database but
        keeps SQLAlchemy's cartesian-product linter quiet.

        Args:
            workflow_id: The workflow whose snapshot to expand. Also supplies
                the value of the ``workflow_id`` field, which the snapshot
                itself does not store.

        Returns:
            The expanded FROM element, the expression yielding one template's
            JSON payload, the per-field overrides to hand
            :func:`~repositories.query.apply_filters` and
            :func:`~repositories.query.apply_sort`, and the expression holding
            the template's position in the stored array.
        """
        templates = col(WorkflowPublishedVersion.templates)
        if self._db.get_bind().dialect.name == "postgresql":
            elem = (
                func.jsonb_array_elements(templates)
                .table_valued(column("value", JSONB), with_ordinality="ordinality")
                .render_derived()
                .lateral()
            )
            payload = elem.c.value
            ordinal = elem.c.ordinality

            def field(camel: str) -> Any:
                return payload[camel].astext
        else:
            elem = func.json_each(templates).table_valued(
                column("value", Text), column("key", Integer)
            )
            payload = elem.c.value
            ordinal = elem.c.key

            def field(camel: str) -> Any:
                return func.json_extract(payload, f"$.{camel}", type_=Text)

        overrides = {
            name: ColumnOverride(expression=field(camel), json_text=True)
            for name, camel in (
                ("id", "id"),
                ("title", "title"),
                ("description", "description"),
                ("created_at", "createdAt"),
                ("updated_at", "updatedAt"),
                ("created_by", "createdBy"),
                ("updated_by", "updatedBy"),
            )
        }
        # Not stored per template -- every element of this snapshot belongs to
        # the workflow being listed, so the value is a constant here.
        overrides["workflow_id"] = ColumnOverride(expression=literal(workflow_id))
        return elem, payload, overrides, ordinal

    async def list_templates(
        self,
        workflow_id: str,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[WorkflowPublishedVersionTemplate]:
        """Return a page of the task templates held by a workflow's latest snapshot.

        Paging, filtering, and sorting run in the database against the JSON
        array itself, so they mean exactly what they mean on the live rows in
        ``repositories.workflow_task_template``: the same ``model`` and
        ``readable`` pair decides which fields are addressable, so ``tenantId``
        stays unfilterable and ``dependsOnIds`` stays unknown, as they are
        there.

        A workflow with no snapshot yields an empty page rather than falling
        back to its live templates. This method exists to keep unpublished work
        out of a caller's hands, so having nothing to show is the safe answer.

        Args:
            workflow_id: The workflow whose snapshot to read.
            limit: Maximum number of templates to return.
            offset: Number of templates to skip.
            sort: Ordering instructions; empty means the stored order, which is
                the order the templates were published in.
            filters: Field filters applied to the query.

        Returns:
            The requested page of published task templates.

        Raises:
            QueryValidationError: If a spec names an unaddressable field, an
                unknown operator, or an uncoercible value.
        """
        elem, payload, overrides, ordinal = self._template_query(workflow_id)
        stmt = (
            select(payload)
            .select_from(WorkflowPublishedVersion)
            .join(elem, true())
            .where(
                WorkflowPublishedVersion.workflow_id == workflow_id,
                latest_version_clause(WorkflowPublishedVersion),
            )
        )
        stmt = self._scoped(stmt)
        stmt = apply_filters(
            stmt,
            WorkflowTaskTemplate,
            filters,
            readable=WorkflowTaskTemplateRead,
            columns=overrides,
        )
        stmt = apply_sort(
            stmt,
            WorkflowTaskTemplate,
            sort,
            default=[ordinal.asc()],
            readable=WorkflowTaskTemplateRead,
            columns=overrides,
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return [_parse_template(row) for row in result.all()]

    async def list_versions(
        self,
        workflow_id: str,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[WorkflowPublishedVersion]:
        """Return a page of a workflow's version history, newest first by default.

        ``templates`` is not addressable: ``readable`` is
        :class:`~models.workflow_published_version.WorkflowVersionRead`, which
        leaves it out.

        Args:
            workflow_id: The workflow whose history to list.
            limit: Maximum number of versions to return.
            offset: Number of versions to skip.
            sort: Ordering instructions; empty means ``version`` descending.
            filters: Field filters applied to the query.

        Returns:
            The requested page of snapshots.

        Raises:
            QueryValidationError: If a spec names an unaddressable field, an
                unknown operator, or an uncoercible value.
        """
        stmt = select(WorkflowPublishedVersion).where(
            WorkflowPublishedVersion.workflow_id == workflow_id
        )
        stmt = self._scoped(stmt)
        stmt = apply_filters(
            stmt, WorkflowPublishedVersion, filters, readable=WorkflowVersionRead
        )
        stmt = apply_sort(
            stmt,
            WorkflowPublishedVersion,
            sort,
            default=[col(WorkflowPublishedVersion.version).desc()],
            readable=WorkflowVersionRead,
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def get_version(
        self, workflow_id: str, version: int
    ) -> WorkflowPublishedVersion | None:
        """Return one numbered snapshot of a workflow, or ``None`` if there is none.

        Args:
            workflow_id: The workflow the snapshot belongs to.
            version: The snapshot's version number.

        Returns:
            The snapshot, or ``None``.
        """
        stmt = select(WorkflowPublishedVersion).where(
            WorkflowPublishedVersion.workflow_id == workflow_id,
            WorkflowPublishedVersion.version == version,
        )
        result = await self._db.exec(self._scoped(stmt))
        return result.first()

    async def create(
        self,
        workflow_id: str,
        *,
        name: str,
        description: str | None,
        templates: list[dict[str, Any]],
        user_id: str,
    ) -> WorkflowPublishedVersion:
        """Record the workflow's current state as its next published version.

        The new row is numbered one past the workflow's latest, so it becomes
        the current published snapshot. Two concurrent publishes of the same
        workflow would pick the same number; the unique constraint on
        ``(workflow_id, version)`` rejects the second rather than letting them
        collide.

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
        latest = await self._get_scoped(workflow_id)
        version = WorkflowPublishedVersion(
            workflow_id=workflow_id,
            version=latest.version + 1 if latest else 1,
            name=name,
            description=description,
            templates=templates,
            tenant_id=tenant_id,
            created_by=user_id,
            updated_by=user_id,
        )
        self._db.add(version)
        await commit_or_translate_user_fk(self._db, user_id=user_id)
        await self._db.refresh(version)
        return version


def _parse_template(row: Any) -> WorkflowPublishedVersionTemplate:
    """Restore one expanded snapshot template from whatever the dialect returned.

    PostgreSQL hands back a decoded ``jsonb`` object; SQLite's ``json_each``
    hands back the element's JSON text.

    Args:
        row: One expanded array element.

    Returns:
        The template as a typed object.
    """
    if isinstance(row, str):
        return WorkflowPublishedVersionTemplate.model_validate_json(row)
    return WorkflowPublishedVersionTemplate.model_validate(row)
