"""Use case service for WorkflowTask resources.

Wraps the :class:`WorkflowTaskRepository` with the business rules the router
needs: raising :class:`NotFoundError` when a task is missing and authorizing
every operation against the task's parent workflow execution. A run's task list
is fixed at execute time (copied from the workflow's published templates), so
this service exposes only ``get`` and ``update`` -- there is no create or delete
path, and ``update`` touches only ``status`` / ``error_kind`` / ``error_message``
(titles, descriptions, dependency edges and tool bindings are immutable once a
task exists). Reading a task (``get``) is open to the execution's initiator, a
designated approver of it, a super admin, or a plain admin (read-only,
tenant-scoped); updating one is restricted to the initiator, a designated
approver, or a super admin -- a plain admin cannot mutate tasks, mirroring
``WorkflowExecutionService.resolve_agent``'s exclusion of admins from driving
an execution's agent. Changing a task's ``status`` is further restricted: a
caller who is only a designated approver of the run may advance a task only
while it sits within the scope of an approval addressed to them (the task an
approval names, and every task downstream of it up to the next approval --
:mod:`infrastructure.approval_scope`). The initiator may change any task's
status; a ``super_admin`` may only for a task no approval governs, mirroring
``ApprovalService.resolve``'s no-bypass rule once an approval is in play. The
execution agent's ``update_workflow_task`` tool applies the same rule to the
chat-driven path.

A status change that can finish the parent run also re-runs the shared
completion bookkeeping in :mod:`services.workflow_execution_completion`, so a
run driven through this endpoint ends up in the same terminal state as one
driven by the agent's own task tools. A write that starts or finishes a task
likewise settles its MCP tool certificate (:meth:`WorkflowTaskService._settle_certificate`),
for the same reason: a task started from here has to end up able to call its
tools, exactly as one the agent started does.
"""

from collections.abc import Collection

from infrastructure.approval_scope import (
    active_approval_by_task,
    governing_approvals,
    may_change_governed_task_status,
)
from models.user import Role, User, has_any_role
from models.workflow_task import (
    WorkflowTaskRead,
    WorkflowTaskUpdate,
)
from repositories.approval import ApprovalRepository
from repositories.exceptions import (
    ForbiddenError,
    NotFoundError,
)
from repositories.workflow_execution import WorkflowExecutionRepository
from repositories.workflow_task import WorkflowTaskRepository
from services.approver_groups import ApproverGroupResolver
from services.mcp_tool_certificate import McpToolCertificateService
from services.notification_dispatch import NotificationDispatcher
from services.workflow_execution_access import WorkflowExecutionAccessPolicy
from services.workflow_execution_completion import evaluate_completion

#: Upper bound on how many of a run's tasks the approval-scope check reads.
#: Mirrors ``infrastructure.mcp_policies._MAX_TASKS``.
_MAX_TASKS = 1000


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
            approvals: Repository used to read the run's approvals so the
                status-change guard can tell which approval governs the task
                being advanced and who its designated approver is.
            notifications: Dispatcher the shared completion bookkeeping uses to
                emit the one-shot ``execution_completed`` notification.
            approver_groups: Resolver backing the status-change guard when a
                governing approval is addressed to a group rather than one user.
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

    async def _evaluate_completion(
        self, execution_id: str, acting_user_id: str
    ) -> None:
        """Re-evaluate whether the parent run has finished after a task write.

        Delegates to the rule shared with the agent's task tools so a run
        driven through the REST endpoints reaches the same terminal ``status``,
        ``finished_at``, and completion notification as one driven by the agent.

        Args:
            execution_id: Primary key of the task's parent workflow execution.
            acting_user_id: The caller performing the write, recorded on any
                task the shared rule skips as a blocked dependent of a failed
                one.
        """
        await evaluate_completion(
            executions=self._execution_repo,
            tasks=self._repo,
            notifications=self._notifications,
            execution_id=execution_id,
            acting_user_id=acting_user_id,
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
        """Restrict a ``status`` transition to the initiator or an eligible approver.

        A participant who is only a designated approver of the run may advance a
        task only while it sits within the scope of an approval addressed to
        them -- the named ``approver``, or a member of its ``approver_group_id``
        holding the ``approver`` role. The run's initiator may change any task's
        status; a ``super_admin`` may only for a task no approval governs, since
        once an approval is in play the "only the addressee decides" invariant
        holds for them too, matching ``ApprovalService.resolve``.

        "Governs" follows :mod:`infrastructure.approval_scope`: an approval
        covers the task it names and every task downstream of it up to the next
        approval, so approving one step lets the covered steps that follow it be
        advanced without each carrying an approval of its own. The execution
        agent's ``update_workflow_task`` tool applies the same rule to the
        chat-driven path.

        Args:
            task: The task whose ``status`` is being changed.
            caller: The authenticated user performing the update.

        Raises:
            ForbiddenError: If the caller is neither the execution initiator nor
                an eligible approver of an approval covering the task (nor, for a
                task no approval governs, a super admin).
        """
        tasks = await self._repo.list(
            limit=_MAX_TASKS,
            offset=0,
            workflow_execution_id=task.workflow_execution_id,
        )
        approvals = await self._approvals.list_for_execution(task.workflow_execution_id)
        governing = governing_approvals(tasks, active_approval_by_task(approvals))
        execution = await self._execution_repo.get(task.workflow_execution_id)
        if may_change_governed_task_status(
            caller_id=caller.id,
            initiator_id=execution.initiator_id if execution is not None else "",
            caller_is_super_admin=has_any_role(caller.roles, Role.super_admin),
            governing_approval_ids=governing.get(task.id, frozenset()),
            approvals_by_id={approval.id: approval for approval in approvals},
            caller_approver_group_ids=await self._approver_groups.group_ids_for(caller),
        ):
            return
        raise ForbiddenError(
            "Only the execution initiator, or an approver an approval covering "
            "this task is addressed to, can change this task's status"
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

    async def update(
        self, task_id: str, data: WorkflowTaskUpdate, *, caller: User
    ) -> WorkflowTaskRead:
        """Apply a partial update to a WorkflowTask.

        Only ``status`` / ``error_kind`` / ``error_message`` are updatable — a
        run's task list is fixed at execute time, so titles, descriptions,
        dependency edges and tool bindings cannot be changed here (nor can a
        task be created or deleted through the REST API). Changing ``status`` is
        further restricted to the execution initiator or an eligible approver of
        an approval covering the task, on top of the general execution-access
        check — see :meth:`_assert_status_change_allowed`.

        Once the write lands, the parent run's completion is re-evaluated, so a
        run finished through this endpoint reaches the same terminal state as
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
                or is changing ``status`` on a task outside the scope of any
                approval addressed to them.
        """
        task = await self._get_or_404(task_id)
        await self._assert_execution_write_access(task.workflow_execution_id, caller)
        if data.status is not None and data.status != task.status:
            await self._assert_status_change_allowed(task, caller)
        updated = await self._repo.update(task_id, data, user_id=caller.id)
        await self._settle_certificate(updated, caller)
        await self._evaluate_completion(updated.workflow_execution_id, caller.id)
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
