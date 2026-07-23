"""Use case service for User resources.

Wraps the :class:`UserRepository` with the business rules the routers need:
hashing passwords before persistence (so the repository only ever stores a
bcrypt hash), raising :class:`NotFoundError` when a user is missing, and
authorizing writes — admins may edit anyone, a non-admin may only edit their
own ``avatar_config`` (the self-service account page), and only a super admin
may grant or revoke the ``super_admin`` role or assign a user's ``tenant_id``.
A ``super_admin`` is platform-scoped by definition and may never carry a
``tenant_id``; every other user must carry one (a non-super-admin actor who
omits it on create is silently scoped to their own tenant instead). Once a
``tenant_id`` is non-null it can never change, for any actor.

``User`` is not a ``TenantScoped`` model (see ``models/tenant_scoped.py``), so
unlike every other resource it has no repository-level tenant filter. Instead
this service enforces the boundary itself: :func:`_assert_tenant_visible`
restricts a non-super-admin actor to users sharing their own concrete tenant
for every read/write that targets an existing user (``get``, and transitively
``update``/``delete``, plus ``list``'s query filter) — a cross-tenant
reference surfaces as :class:`NotFoundError`, not :class:`ForbiddenError`, so
existence in another tenant is never leaked. A ``super_admin`` actor is
exempt, same as every other role check in this module, and so is a
platform-scoped *target* (``tenant_id is None`` — a ``super_admin`` or the
system user), matching the existing precedent that any admin may view or
edit a super_admin's profile fields.
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


def _require_tenant_for_non_super_admin(
    roles: Sequence[str] | None, tenant_id: str | None
) -> None:
    """Reject an effective role/tenant combination that leaves a non-super-admin without a tenant.

    Every user other than a ``super_admin`` (and the seeded system user, which
    never goes through this service) must belong to a tenant — see
    ``ck_users_non_super_admin_requires_tenant`` (:class:`~models.user.User`)
    for the matching database-level guarantee.

    Args:
        roles: The user's effective roles after the write.
        tenant_id: The user's effective tenant_id after the write.

    Raises:
        UserValidationError: If ``roles`` does not include ``super_admin`` and
            ``tenant_id`` is ``None``.
    """
    if tenant_id is None and Role.super_admin not in (roles or []):
        raise UserValidationError("A non-super-admin user must be assigned a tenant")


def _assert_tenant_visible(acting_user: User, target: User) -> None:
    """Reject access to a user belonging to a different, concrete tenant.

    The boundary is between two actual tenants only: a platform-scoped
    target (``target.tenant_id is None`` -- a ``super_admin`` or the seeded
    system user) is exempt, matching the existing precedent that any admin
    may view or edit a super_admin's profile fields (role changes are
    separately gated in :meth:`UserService.update`). A ``super_admin`` actor
    is likewise exempt, matching every other role check in this module. Any
    other actor (including one with the ``admin`` role) may only see users
    sharing their own tenant.

    Args:
        acting_user: The authenticated user making the request.
        target: The user record being accessed.

    Raises:
        NotFoundError: If neither exemption applies and ``target.tenant_id``
            differs from ``acting_user.tenant_id`` -- reported as "not
            found" rather than "forbidden" so a cross-tenant reference never
            confirms the target's existence.
    """
    if has_role(acting_user, Role.super_admin) or target.tenant_id is None:
        return
    if target.tenant_id != acting_user.tenant_id:
        raise NotFoundError("User", target.id)


class UserService:
    """Application service orchestrating User operations."""

    def __init__(self, repo: UserRepository) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing User persistence.
        """
        self._repo = repo

    async def get(self, user_id: str, *, acting_user: User) -> User:
        """Return the User with the given ID.

        Args:
            user_id: Identifier of the user to fetch.
            acting_user: The authenticated user making the request; must be a
                super admin or share the target's tenant.

        Returns:
            The matching User.

        Raises:
            NotFoundError: If no user exists with the given ID, or if it
                exists but is outside ``acting_user``'s tenant (see
                :func:`_assert_tenant_visible`).
        """
        user = await self._repo.get(user_id)
        if user is None:
            raise NotFoundError("User", user_id)
        _assert_tenant_visible(acting_user, user)
        return user

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        acting_user: User,
        acting_tenant_id: str,
    ) -> list[User]:
        """Return a page of User records visible to the acting user.

        A non-super-admin actor is restricted to users in their own tenant: a
        matching ``tenantId:eq:`` filter is appended to ``filters``, so it
        combines with (never widens) whatever the caller supplied. A super
        admin is instead scoped to the tenant they are currently acting as
        (``acting_tenant_id``, resolved from the ``X-Tenant-Id`` header via
        the app bar's tenant switcher -- see ``CurrentTenantIdDep``), plus
        every ``super_admin`` user platform-wide regardless of tenant; this
        OR-scope can't be expressed as a ``FilterSpec`` (AND-only), so it's
        applied by the repository via ``visible_tenant_id`` instead.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query.
            acting_user: The authenticated user making the request.
            acting_tenant_id: The tenant the request is scoped to -- the
                caller's own tenant, or, for a super admin, the tenant
                currently selected via the app bar's tenant switcher.

        Returns:
            The requested page of users.
        """
        if has_role(acting_user, Role.super_admin):
            return await self._repo.list(
                limit=limit,
                offset=offset,
                sort=sort,
                filters=filters,
                visible_tenant_id=acting_tenant_id,
            )
        filters = (
            *filters,
            FilterSpec(field="tenantId", op="eq", value=acting_user.tenant_id or ""),
        )
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
                and also carry a ``tenant_id``, or would hold neither
                ``super_admin`` nor a ``tenant_id``.
        """
        if Role.super_admin in data.roles and not has_role(
            acting_user, Role.super_admin
        ):
            raise ForbiddenError("Only a super admin can grant the super_admin role")
        if data.tenant_id is not None and not has_role(acting_user, Role.super_admin):
            raise ForbiddenError("Only a super admin can assign a tenant")
        if data.tenant_id is None and not has_role(acting_user, Role.super_admin):
            # A non-super-admin actor can't supply a tenant_id explicitly (see
            # above), yet every non-super-admin user must carry one — silently
            # scope the new user to the acting admin's own tenant instead of
            # requiring an "assign tenant" privilege they don't have.
            data = data.model_copy(update={"tenant_id": acting_user.tenant_id})
        _reject_super_admin_tenant_conflict(data.roles, data.tenant_id)
        _require_tenant_for_non_super_admin(data.roles, data.tenant_id)
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
            NotFoundError: If no user exists with the given ID, or if it
                exists but is outside ``acting_user``'s tenant (see
                :func:`_assert_tenant_visible`).
            ForbiddenError: If the acting user is not allowed to apply this
                update (non-admin editing another user or a non-self-service
                field, a non-super-admin changing ``super_admin``, or a
                non-super-admin assigning a tenant to a currently tenant-less
                target).
            UserValidationError: If the update would leave the target holding
                ``super_admin`` while also carrying a ``tenant_id``, would
                leave the target holding neither ``super_admin`` nor a
                ``tenant_id``, or would change a ``tenant_id`` the target
                already has.
        """
        target = await self.get(target_id, acting_user=acting_user)
        update = data.model_dump(exclude_unset=True)
        if has_role(acting_user, Role.admin):
            if data.roles is not None and not has_role(acting_user, Role.super_admin):
                had_super = Role.super_admin in (target.roles or [])
                gets_super = Role.super_admin in data.roles
                if had_super != gets_super:
                    raise ForbiddenError(
                        "Only a super admin can grant or revoke the super_admin role"
                    )
            if "tenant_id" in update and update["tenant_id"] != target.tenant_id:
                if target.tenant_id is not None:
                    # Immutable once assigned, for every actor including a
                    # super admin — no reassignment, and no clearing back to
                    # null (e.g. as part of promoting the target to
                    # super_admin).
                    raise UserValidationError(
                        "A user's tenant cannot be changed once assigned"
                    )
                if not has_role(acting_user, Role.super_admin):
                    raise ForbiddenError("Only a super admin can assign a tenant")
            effective_roles = data.roles if data.roles is not None else target.roles
            effective_tenant_id = update.get("tenant_id", target.tenant_id)
            _reject_super_admin_tenant_conflict(effective_roles, effective_tenant_id)
            _require_tenant_for_non_super_admin(effective_roles, effective_tenant_id)
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

    async def delete(self, user_id: str, *, acting_user: User) -> None:
        """Delete a User.

        Args:
            user_id: Identifier of the user to delete.
            acting_user: The authenticated user performing the deletion; must
                be a super admin or share the target's tenant.

        Raises:
            NotFoundError: If no user exists with the given ID, or if it
                exists but is outside ``acting_user``'s tenant (see
                :func:`_assert_tenant_visible`).
        """
        await self.get(user_id, acting_user=acting_user)
        await self._repo.delete(user_id)
