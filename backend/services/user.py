"""Use case service for User resources.

Wraps the :class:`UserRepository` with the business rules the routers need:
hashing passwords before persistence (so the repository only ever stores a
bcrypt hash), raising :class:`NotFoundError` when a user is missing, and
authorizing writes — admins may edit anyone, a non-admin may only edit their
own ``avatar_config`` (the self-service account page), and only a super admin
may grant or revoke the ``super_admin`` role or assign/change a user's
``tenant_id``. A ``super_admin`` is platform-scoped by definition and may
never carry a ``tenant_id``, regardless of who performs the write.
"""

from collections.abc import Sequence

from infrastructure.password import hash_password
from models.user import Role, User, UserCreate, UserUpdate, has_role
from repositories import UserRepository
from repositories.exceptions import ForbiddenError, NotFoundError, UserValidationError
from repositories.query import FilterSpec, SortSpec

#: Fields a non-admin user may update on their own record via ``PATCH``.
#: Matches what the self-service ``/account`` page sends (avatar customization
#: only); everything else requires the ``admin`` role.
_SELF_SERVICE_FIELDS = frozenset({"avatar_config"})


def _reject_super_admin_tenant_conflict(
    roles: Sequence[str] | None, tenant_id: str | None
) -> None:
    """Reject an effective role/tenant combination that tenant-scopes a super admin.

    Runs independent of the acting user's role — a super admin is
    platform-scoped and must never carry a ``tenant_id``, even when a super
    admin performs the write. This is the fast, friendly-error path (HTTP 422
    with a clear message); the same invariant is also enforced at the
    database level by the ``ck_users_super_admin_no_tenant`` CHECK constraint
    (:class:`~models.user.User`), which is the actual guarantee under
    concurrent writes — mirrors how the self-loop guards in
    ``repositories/workflow_task.py`` relate to their own DB constraints.

    Args:
        roles: The user's effective roles after the write.
        tenant_id: The user's effective tenant_id after the write.

    Raises:
        UserValidationError: If ``roles`` includes ``super_admin`` and
            ``tenant_id`` is not ``None``.
    """
    if tenant_id is not None and Role.super_admin in (roles or []):
        raise UserValidationError("A super admin cannot be assigned a tenant")


class UserService:
    """Application service orchestrating User operations."""

    def __init__(self, repo: UserRepository) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing User persistence.
        """
        self._repo = repo

    async def get(self, user_id: str) -> User:
        """Return the User with the given ID.

        Args:
            user_id: Identifier of the user to fetch.

        Returns:
            The matching User.

        Raises:
            NotFoundError: If no user exists with the given ID.
        """
        user = await self._repo.get(user_id)
        if user is None:
            raise NotFoundError("User", user_id)
        return user

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
    ) -> list[User]:
        """Return a page of User records.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.

        Returns:
            The requested page of users.
        """
        return await self._repo.list(
            limit=limit, offset=offset, sort=sort, filters=filters
        )

    async def create(self, data: UserCreate, *, acting_user: User) -> User:
        """Create a new User, hashing the supplied password before persistence.

        The route itself is gated behind the ``admin`` role; this method adds
        the escalation guard: only a super admin may create a user that holds
        the ``super_admin`` role.

        Args:
            data: Fields for the new user (with a plaintext password).
            acting_user: The authenticated user creating the record.

        Returns:
            The created User.

        Raises:
            ForbiddenError: If the new user would hold ``super_admin`` and the
                acting user is not a super admin, or if a ``tenant_id`` is
                supplied and the acting user is not a super admin.
            UserValidationError: If the new user would hold ``super_admin``
                and also carry a ``tenant_id``.
        """
        if Role.super_admin in data.roles and not has_role(
            acting_user, Role.super_admin
        ):
            raise ForbiddenError("Only a super admin can grant the super_admin role")
        if data.tenant_id is not None and not has_role(acting_user, Role.super_admin):
            raise ForbiddenError("Only a super admin can assign a tenant")
        _reject_super_admin_tenant_conflict(data.roles, data.tenant_id)
        hashed = data.model_copy(update={"password": hash_password(data.password)})
        return await self._repo.create(hashed, user_id=acting_user.id)

    async def update(
        self, target_id: str, data: UserUpdate, *, acting_user: User
    ) -> User:
        """Apply a partial update to a User, authorizing the acting user.

        An ``admin`` (or ``super_admin``) may update any user and any field,
        except that granting or revoking the ``super_admin`` role requires the
        acting user to be a super admin. Any other caller may update only
        their own record, and only its self-service fields
        (:data:`_SELF_SERVICE_FIELDS` — the avatar customization edited from
        the ``/account`` page).

        A blank or omitted password leaves the stored password unchanged; a
        non-empty password is hashed before persistence.

        Args:
            target_id: Identifier of the user to update.
            data: Fields to update (password optional).
            acting_user: The authenticated user performing the update.

        Returns:
            The updated User.

        Raises:
            NotFoundError: If no user exists with the given ID.
            ForbiddenError: If the acting user is not allowed to apply this
                update (non-admin editing another user or a non-self-service
                field, a non-super-admin changing ``super_admin``, or a
                non-super-admin changing ``tenant_id`` to a different value).
            UserValidationError: If the update would leave the target holding
                ``super_admin`` while also carrying a ``tenant_id``.
        """
        target = await self.get(target_id)
        update = data.model_dump(exclude_unset=True)
        if has_role(acting_user, Role.admin):
            if data.roles is not None and not has_role(acting_user, Role.super_admin):
                had_super = Role.super_admin in (target.roles or [])
                gets_super = Role.super_admin in data.roles
                if had_super != gets_super:
                    raise ForbiddenError(
                        "Only a super admin can grant or revoke the super_admin role"
                    )
            if (
                "tenant_id" in update
                and update["tenant_id"] != target.tenant_id
                and not has_role(acting_user, Role.super_admin)
            ):
                raise ForbiddenError("Only a super admin can change a user's tenant")
            effective_roles = data.roles if data.roles is not None else target.roles
            effective_tenant_id = update.get("tenant_id", target.tenant_id)
            _reject_super_admin_tenant_conflict(effective_roles, effective_tenant_id)
        elif target_id != acting_user.id or not set(update) <= _SELF_SERVICE_FIELDS:
            raise ForbiddenError(
                "Only admins can update other users or non-self-service fields"
            )
        password = update.get("password")
        if password:
            update["password"] = hash_password(password)
        else:
            update.pop("password", None)
        return await self._repo.update(
            target_id, UserUpdate(**update), user_id=acting_user.id
        )

    async def delete(self, user_id: str) -> None:
        """Delete a User.

        Args:
            user_id: Identifier of the user to delete.

        Raises:
            NotFoundError: If no user exists with the given ID.
        """
        await self._repo.delete(user_id)
