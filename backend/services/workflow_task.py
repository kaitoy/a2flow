"""Use case service for WorkflowTask resources.

Wraps the :class:`WorkflowTaskRepository` with the business rules the router
needs: raising :class:`NotFoundError` when a task is missing and authorizing
every operation against the task's parent workflow execution. Reading a task
(``get``) is open to the execution's initiator, a designated approver of it, a
super admin, or a plain admin (read-only, tenant-scoped); creating, updating,
or deleting one is restricted to the initiator, a designated approver, or a
super admin -- a plain admin cannot mutate tasks, mirroring
``WorkflowExecutionService.resolve_agent``'s exclusion of admins from driving
an execution's agent. Changing a task's ``status`` is further restricted
when the task has a linked ``Approval`` (``Approval.workflow_task_id``): only
the execution initiator or an eligible approver of that Approval may do so --
the named ``approver``, or a member of its ``approver_group_id`` holding the
``approver`` role -- not merely any approver of the execution, mirroring
``ApprovalService.resolve``'s no-bypass rule.

Every write that can change the set of unfinished tasks also re-runs the shared
completion bookkeeping in :mod:`services.workflow_execution_completion`, so a
run driven through these endpoints ends up in the same terminal state as one
driven by the agent's own task tools. A write that starts or finishes a task
likewise settles its MCP tool certificate (:meth:`WorkflowTaskService._settle_certificate`),
for the same reason: a task started from here has to end up able to call its
tools, exactly as one the agent started does.
"""

from collections.abc import Collection

from models.user import User
from models.workflow_task import (
    WorkflowTaskCreate,
    WorkflowTaskRead,
    WorkflowTaskUpdate,
)
from repositories import (
    ApprovalRepository,
    WorkflowExecutionRepository,
    WorkflowTaskRepository,
)
from repositories.exceptions import (
    ForbiddenError,
    ForeignKeyViolationError,
    NotFoundError,
)
from services.approver_groups import ApproverGroupResolver
from services.mcp_tool_certificate import McpToolCertificateService
from services.notification_dispatch import NotificationDispatcher
from services.workflow_execution_access import WorkflowExecutionAccessPolicy
from services.workflow_execution_completion import evaluate_completion


class WorkflowTaskService:
    """Application service orchestrating WorkflowTask operations."""

    def __init__(
        self,
        repo: WorkflowTaskRepository,
        execution_repo: WorkflowExecutionRepository,
        access: WorkflowExecutionAccessPolicy,
        approvals: ApprovalRepository,
        notifications: NotificationDispatcher,
        approver_groups: ApproverGroupResolver,
        certificates: McpToolCertificateService,
    ) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing WorkflowTask persistence.
            execution_repo: Repository used to resolve a task's parent execution for
                the access check.
            access: Policy restricting task operations to the execution initiator,
                the execution's designated approvers, admins (read-only), and
                super admins.
            approvals: Repository used to look up whether a task being updated
                has a linked Approval and, if so, its designated approver, to
                restrict ``status`` changes on such tasks.
            notifications: Dispatcher the shared completion bookkeeping uses to
                emit the one-shot ``execution_completed`` notification.
            approver_groups: Resolver backing the status-change guard when the
                linked Approval is addressed to a group rather than one user.
            certificates: Service issuing a task's MCP tool certificate when it
                starts and revoking it when it finishes, so a run driven through
                these endpoints carries the same signed authority as one the
                agent drives itself.
        """
        self._repo = repo
        self._execution_repo = execution_repo
        self._access = access
        self._approvals = approvals
        self._approver_groups = approver_groups
        self._notifications = notifications
        self._certificates = certificates

    async def _evaluate_completion(self, execution_id: str) -> None:
        """Re-evaluate whether the parent run has finished after a task write.

        Delegates to the rule shared with the agent's task tools so a run
        driven through the REST endpoints reaches the same terminal ``status``,
        ``finished_at``, and completion notification as one driven by the agent.

        Args:
            execution_id: Primary key of the task's parent workflow execution.
        """
        await evaluate_completion(
            executions=self._execution_repo,
            tasks=self._repo,
            notifications=self._notifications,
            execution_id=execution_id,
        )

    async def _get_or_404(self, task_id: str) -> WorkflowTaskRead:
        """Return the WorkflowTask with the given ID, without authorization.

        Args:
            task_id: Identifier of the task to fetch.

        Returns:
            The matching WorkflowTask.

        Raises:
            NotFoundError: If no task exists with the given ID.
        """
        task = await self._repo.get(task_id)
        if task is None:
            raise NotFoundError("WorkflowTask", task_id)
        return task

    async def _assert_execution_access(
        self, execution_id: str, caller: User, caller_roles: Collection[str]
    ) -> None:
        """Authorize the caller to read a task's parent workflow execution.

        Read-only: also admits a plain admin in the caller's tenant. Used by
        :meth:`get` only -- :meth:`create`/:meth:`update`/:meth:`delete` go
        through :meth:`_assert_execution_write_access` instead, which does
        not.

        Args:
            execution_id: Identifier of the parent workflow execution.
            caller: The authenticated user performing the task operation.
            caller_roles: The caller's effective roles, including any
                inherited from their groups.

        Raises:
            NotFoundError: If the parent execution does not exist (so a missing
                parent surfaces as 404 before any 403).
            ForbiddenError: If the caller is neither the execution initiator, a
                designated approver of the execution, nor holds ``admin`` or
                ``super_admin``.
        """
        execution = await self._execution_repo.get(execution_id)
        if execution is None:
            raise NotFoundError("WorkflowExecution", execution_id)
        await self._access.assert_read_access(
            execution_id, execution.initiator_id, caller, caller_roles
        )

    async def _assert_execution_write_access(
        self, execution_id: str, caller: User
    ) -> None:
        """Authorize the caller to create, update, or delete a task.

        Stricter than :meth:`_assert_execution_access`: a plain admin does
        not pass here, only the execution initiator, a designated approver,
        or a super admin -- mirroring ``WorkflowExecutionService.resolve_agent``.

        Args:
            execution_id: Identifier of the parent workflow execution.
            caller: The authenticated user performing the task mutation.

        Raises:
            NotFoundError: If the parent execution does not exist (so a missing
                parent surfaces as 404 before any 403).
            ForbiddenError: If the caller is neither the execution initiator, a
                designated approver of the execution, nor a super admin.
        """
        execution = await self._execution_repo.get(execution_id)
        if execution is None:
            raise NotFoundError("WorkflowExecution", execution_id)
        await self._access.assert_access(execution_id, execution.initiator_id, caller)

    async def _assert_status_change_allowed(
        self, task: WorkflowTaskRead, caller: User
    ) -> None:
        """Restrict a ``status`` transition on a task with a linked Approval.

        Only applies when the task has a linked Approval carrying a
        destination -- a named ``approver``, or an ``approver_group_id`` whose
        eligible members stand in for one. Tasks without such an approval keep
        the broader rule already enforced
        by :meth:`_assert_execution_write_access`. No ``super_admin`` bypass, for
        consistency with ``ApprovalService.resolve``'s no-bypass rule — this
        check protects the same "only the addressee decides" invariant,
        reachable here via the task's ``status`` field instead of the
        Approval's own ``status`` field.

        Args:
            task: The task whose ``status`` is being changed.
            caller: The authenticated user performing the update.

        Raises:
            ForbiddenError: If the caller is neither the execution initiator nor
                an eligible approver of the linked Approval.
        """
        approval = await self._approvals.get_for_task(task.id)
        if approval is None:
            return
        if approval.approver is None and approval.approver_group_id is None:
            return
        if approval.approver is not None and caller.id == approval.approver:
            return
        if approval.approver_group_id is not None:
            eligible = await self._approver_groups.group_ids_for(caller)
            if approval.approver_group_id in eligible:
                return
        execution = await self._execution_repo.get(task.workflow_execution_id)
        if execution is not None and caller.id == execution.initiator_id:
            return
        raise ForbiddenError(
            "Only the execution initiator or an eligible approver of the linked "
            "approval can change this task's status"
        )

    async def get(
        self, task_id: str, *, caller: User, caller_roles: Collection[str]
    ) -> WorkflowTaskRead:
        """Return the WorkflowTask with the given ID.

        Read-only: also passes a plain ``admin`` in the caller's tenant --
        see :meth:`_assert_execution_access`.

        Args:
            task_id: Identifier of the task to fetch.
            caller: The authenticated user requesting the task.
            caller_roles: The caller's effective roles, including any
                inherited from their groups.

        Returns:
            The matching WorkflowTask.

        Raises:
            NotFoundError: If no task exists with the given ID.
            ForbiddenError: If the caller may not read the task's execution.
        """
        task = await self._get_or_404(task_id)
        await self._assert_execution_access(
            task.workflow_execution_id, caller, caller_roles
        )
        return task

    async def create(
        self, data: WorkflowTaskCreate, *, caller: User
    ) -> WorkflowTaskRead:
        """Create a new WorkflowTask.

        A missing parent execution surfaces as a foreign-key violation (HTTP
        422), matching the pre-authorization behavior of the repository's own
        FK check, rather than the 404 used when the execution appears in the
        URL path.

        Args:
            data: Fields for the new task, including its parent execution.
            caller: The authenticated user creating the task.

        Returns:
            The created WorkflowTask.

        Raises:
            ForeignKeyViolationError: If the parent execution does not exist.
            ForbiddenError: If the caller may not act on the parent execution
                (a plain admin who is not the initiator or a designated
                approver is rejected, same as :meth:`update`/:meth:`delete`).
        """
        execution = await self._execution_repo.get(data.workflow_execution_id)
        if execution is None:
            raise ForeignKeyViolationError(
                "WorkflowExecution", data.workflow_execution_id
            )
        await self._access.assert_access(
            data.workflow_execution_id, execution.initiator_id, caller
        )
        created = await self._repo.create(data, user_id=caller.id)
        # A task can be created already ``in_progress``, which is the same edge
        # :meth:`update` handles -- it just happens at insert time instead.
        await self._certificates.issue_for_started_task(
            created, execution, user_id=caller.id
        )
        return created

    async def update(
        self, task_id: str, data: WorkflowTaskUpdate, *, caller: User
    ) -> WorkflowTaskRead:
        """Apply a partial update to a WorkflowTask.

        Changing ``status`` on a task with a linked Approval is further
        restricted to the execution initiator or that Approval's designated
        approver, on top of the general execution-access check — see
        :meth:`_assert_status_change_allowed`.

        Once the write lands, the parent run's completion is re-evaluated, so a
        run finished through these endpoints reaches the same terminal state as
        one finished by the agent.

        Args:
            task_id: Identifier of the task to update.
            data: Fields to update.
            caller: The authenticated user performing the update.

        Returns:
            The updated WorkflowTask.

        Raises:
            NotFoundError: If no task exists with the given ID.
            ForbiddenError: If the caller may not act on the task's execution
                (a plain admin is rejected, see :meth:`_assert_execution_write_access`),
                or is changing ``status`` on a task whose linked Approval
                designates someone else as approver.
        """
        task = await self._get_or_404(task_id)
        await self._assert_execution_write_access(task.workflow_execution_id, caller)
        if data.status is not None and data.status != task.status:
            await self._assert_status_change_allowed(task, caller)
        updated = await self._repo.update(task_id, data, user_id=caller.id)
        await self._settle_certificate(updated, caller)
        await self._evaluate_completion(updated.workflow_execution_id)
        return updated

    async def _settle_certificate(self, task: WorkflowTaskRead, caller: User) -> None:
        """Bring the task's tool certificate in line with the status it now has.

        A task that has just started needs one before it can call anything; a
        task that has just finished no longer needs the one it had. Both edges
        are handled here so the two callers below do not each have to remember
        which way the write went, and so a run driven through the REST endpoints
        ends up with the same certificates as one the agent drives through its
        own task tools.

        Args:
            task: The task as it stands after the write.
            caller: The authenticated user who performed the write.
        """
        execution = await self._execution_repo.get(task.workflow_execution_id)
        if execution is not None:
            await self._certificates.issue_for_started_task(
                task, execution, user_id=caller.id
            )
        await self._certificates.revoke_if_task_finished(task, user_id=caller.id)

    async def delete(self, task_id: str, *, caller: User) -> None:
        """Delete a WorkflowTask.

        Deleting the last non-terminal task of a run can finish it, so the
        parent run's completion is re-evaluated afterwards.

        Args:
            task_id: Identifier of the task to delete.
            caller: The authenticated user performing the deletion.

        Raises:
            NotFoundError: If no task exists with the given ID.
            ForbiddenError: If the caller may not act on the task's execution
                (a plain admin is rejected, see :meth:`_assert_execution_write_access`).
        """
        task = await self._get_or_404(task_id)
        await self._assert_execution_write_access(task.workflow_execution_id, caller)
        await self._repo.delete(task_id)
        await self._evaluate_completion(task.workflow_execution_id)
