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
existence in another tenant is never leaked. Only a ``super_admin`` actor is
exempt, same as every other role check in this module — a platform-scoped
*target* (``tenant_id is None`` — a ``super_admin`` or the system user) gets
no separate exemption, so a plain ``admin`` can never view, edit, or delete a
``super_admin``'s record; only the ``super_admin`` itself or another
``super_admin`` actor can.
"""

from collections.abc import Collection, Sequence

from infrastructure.password import hash_password
from models.user import (
    SYSTEM_USER_ID,
    ResolvedUserName,
    Role,
    User,
    UserCreate,
    UserUpdate,
    has_any_role,
)
from repositories import EffectiveRoleRepository, UserRepository
from repositories.exceptions import ForbiddenError, NotFoundError, UserValidationError
from repositories.query import FilterSpec, SortSpec

#: Fields a non-admin user may update on their own record via ``PATCH``.
#: Matches what the self-service ``/profile`` page sends (avatar customization
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


def _reject_super_admin_role_combination(roles: Sequence[str] | None) -> None:
    """Reject an effective roles list that combines super_admin with any other role.

    Runs independent of the acting user's role, mirroring
    :func:`_reject_super_admin_tenant_conflict` — ``super_admin`` already
    bypasses every other role via :func:`has_any_role`, so holding one alongside
    it is redundant at best and confusing at worst. This is the fast,
    friendly-error path (HTTP 422); the same invariant is also enforced at
    the database level by the ``ck_users_super_admin_exclusive`` CHECK
    constraint (:class:`~models.user.User`), for concurrent-write safety.

    Args:
        roles: The user's effective roles after the write.

    Raises:
        UserValidationError: If ``roles`` includes ``super_admin`` together
            with any other role.
    """
    role_set = set(roles or [])
    if Role.super_admin in role_set and len(role_set) > 1:
        raise UserValidationError("A super admin cannot hold any other role")


def _assert_tenant_visible(acting_user: User, target: User) -> None:
    """Reject access to a user outside the acting user's own tenant.

    Only a ``super_admin`` actor is exempt from the tenant boundary, matching
    every other role check in this module. Every non-super-admin user
    (``admin`` included) is guaranteed by ``ck_users_non_super_admin_requires_tenant``
    (:class:`~models.user.User`) to carry a concrete, non-null ``tenant_id``,
    so a platform-scoped target (``target.tenant_id is None`` -- a
    ``super_admin`` or the seeded system user) always fails the comparison
    below for such an actor: a ``super_admin`` target can therefore only be
    viewed, edited, or deleted by itself (via the ``super_admin`` exemption)
    or by another ``super_admin`` actor, never by a plain ``admin``.

    Args:
        acting_user: The authenticated user making the request.
        target: The user record being accessed.

    Raises:
        NotFoundError: If the acting user is not a super admin and
            ``target.tenant_id`` differs from ``acting_user.tenant_id`` --
            reported as "not found" rather than "forbidden" so a cross-tenant
            (or platform-scoped) reference never confirms the target's
            existence.
    """
    # Direct roles, not effective ones: this asks only about ``super_admin``,
    # which a user group can never grant.
    if has_any_role(acting_user.roles, Role.super_admin):
        return
    if target.tenant_id != acting_user.tenant_id:
        raise NotFoundError("User", target.id)


#: Display name reported for a ``super_admin`` the caller may not see
#: individually. Every super admin collapses to this one string, so a record
#: they own reads as something other than a bare UUID without disclosing which
#: of them it was.
_MASKED_SUPER_ADMIN_NAME = "Super Admin"

#: Display name reported for the seeded system user, which is platform-scoped
#: and therefore invisible to every non-super-admin caller (see
#: :func:`_assert_tenant_visible`). It matches the seeded record's own name, so
#: a super admin and a tenant user read the same label.
_MASKED_SYSTEM_USER_NAME = "System User"


def _visible_display_name(acting_user: User, target: User) -> str | None:
    """Return the display name ``acting_user`` may see for ``target``.

    Applies the same tenant boundary as :meth:`UserService.get`. A target the
    acting user cannot see individually still gets a name when it is the
    seeded system user or a ``super_admin`` -- a fixed placeholder that
    identifies the *kind* of account without naming the individual.

    Args:
        acting_user: The authenticated user making the request.
        target: The user record whose name is being resolved.

    Returns:
        ``"First Last"`` when the target is visible, a placeholder when it is
        an invisible system user or super admin, or ``None`` when the caller
        may not learn anything about it (the client then falls back to
        displaying the raw id).
    """
    try:
        _assert_tenant_visible(acting_user, target)
    except NotFoundError:
        if target.id == SYSTEM_USER_ID:
            return _MASKED_SYSTEM_USER_NAME
        # An empty ``allowed`` makes has_any_role a plain "is a super admin?"
        # test. Direct roles: a user group can never grant ``super_admin``.
        if has_any_role(target.roles):
            return _MASKED_SUPER_ADMIN_NAME
        return None
    return f"{target.first_name} {target.last_name}".strip()


class UserService:
    """Application service orchestrating User operations."""

    def __init__(
        self, repo: UserRepository, effective_roles: EffectiveRoleRepository
    ) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing User persistence.
            effective_roles: Repository resolving the roles users inherit from
                their groups, used to populate :attr:`UserRead.group_roles`.
                Deliberately not tenant-scoped — see
                :mod:`repositories.effective_roles`.
        """
        self._repo = repo
        self._effective_roles = effective_roles

    async def group_roles_for(self, users: Sequence[User]) -> dict[str, list[str]]:
        """Return the group-inherited roles of each user, resolved in one query.

        Feeds :meth:`models.user.UserRead.from_user` so a response reports the
        inherited half of a user's roles alongside their direct grants. Batched
        so a list endpoint stays at one membership query per page.

        Args:
            users: The users about to be serialized.

        Returns:
            A mapping of user id to their sorted inherited roles. Every id in
            ``users`` is present; a user in no group maps to an empty list.
        """
        inherited = await self._effective_roles.group_roles_for_users(
            [user.id for user in users]
        )
        return {user.id: sorted(inherited.get(user.id, frozenset())) for user in users}

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

    async def resolve_names(
        self, ids: Sequence[str], *, acting_user: User
    ) -> list[ResolvedUserName]:
        """Resolve user ids to the display names ``acting_user`` may see.

        The batch counterpart of :meth:`get` for the single purpose of
        rendering a name: it exists so a client showing many user references
        at once (an audit footer, a list of workflow initiators) resolves them
        in one request instead of one per id. Soft-deleted users and the
        seeded system user resolve here, unlike in :meth:`list`, because the
        records they own outlive them.

        The tenant boundary is the same as :meth:`get`'s -- see
        :func:`_visible_display_name` for how an invisible target is masked or
        dropped. Ids are de-duplicated, and unknown ones are simply absent
        from the result rather than raising, so one stale reference does not
        cost the caller every other name in the batch.

        Args:
            ids: User identifiers to resolve; duplicates and empty strings are
                ignored.
            acting_user: The authenticated user making the request.

        Returns:
            One entry per resolvable id, in unspecified order.
        """
        unique = list(dict.fromkeys(user_id for user_id in ids if user_id))
        resolved: list[ResolvedUserName] = []
        for user in await self._repo.get_many(unique):
            name = _visible_display_name(acting_user, user)
            if name is not None:
                resolved.append(ResolvedUserName(id=user.id, display_name=name))
        return resolved

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
        if has_any_role(acting_user.roles, Role.super_admin):
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
                and also carry a ``tenant_id``, would hold neither
                ``super_admin`` nor a ``tenant_id``, or would hold
                ``super_admin`` together with another role.
        """
        if Role.super_admin in data.roles and not has_any_role(
            acting_user.roles, Role.super_admin
        ):
            raise ForbiddenError("Only a super admin can grant the super_admin role")
        if data.tenant_id is not None and not has_any_role(
            acting_user.roles, Role.super_admin
        ):
            raise ForbiddenError("Only a super admin can assign a tenant")
        if data.tenant_id is None and not has_any_role(
            acting_user.roles, Role.super_admin
        ):
            # A non-super-admin actor can't supply a tenant_id explicitly (see
            # above), yet every non-super-admin user must carry one — silently
            # scope the new user to the acting admin's own tenant instead of
            # requiring an "assign tenant" privilege they don't have.
            data = data.model_copy(update={"tenant_id": acting_user.tenant_id})
        _reject_super_admin_tenant_conflict(data.roles, data.tenant_id)
        _require_tenant_for_non_super_admin(data.roles, data.tenant_id)
        _reject_super_admin_role_combination(data.roles)
        hashed = data.model_copy(update={"password": hash_password(data.password)})
        return await self._repo.create(hashed, user_id=acting_user.id)

    async def update(
        self,
        target_id: str,
        data: UserUpdate,
        *,
        acting_user: User,
        acting_roles: Collection[str],
    ) -> User:
        """Apply a partial update to a User, authorizing the acting user.

        An ``admin`` may update any field of any user sharing their own
        tenant, except that granting or revoking the ``super_admin`` role
        requires the acting user to be a super admin. A ``super_admin``
        target is never visible to a plain ``admin`` (see
        :func:`_assert_tenant_visible`), so it can only be updated by itself
        or by another ``super_admin`` actor, who may update any user and any
        field. Any other caller may update only their own record, and only
        its self-service fields (:data:`_SELF_SERVICE_FIELDS` — the avatar
        customization edited from the ``/profile`` page).

        A blank or omitted password leaves the stored password unchanged; a
        non-empty password is hashed before persistence.

        Args:
            target_id: Identifier of the user to update.
            data: Fields to update (password optional).
            acting_user: The authenticated user performing the update.
            acting_roles: The acting user's effective roles — direct grants
                plus everything inherited from their groups — so an ``admin``
                held only through a group still takes the admin path below.

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
                ``tenant_id``, would change a ``tenant_id`` the target
                already has, or would leave the target holding
                ``super_admin`` together with another role.
        """
        target = await self.get(target_id, acting_user=acting_user)
        update = data.model_dump(exclude_unset=True)
        if has_any_role(acting_roles, Role.admin):
            if data.roles is not None and not has_any_role(
                acting_user.roles, Role.super_admin
            ):
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
                if not has_any_role(acting_user.roles, Role.super_admin):
                    raise ForbiddenError("Only a super admin can assign a tenant")
            effective_roles = data.roles if data.roles is not None else target.roles
            effective_tenant_id = update.get("tenant_id", target.tenant_id)
            _reject_super_admin_tenant_conflict(effective_roles, effective_tenant_id)
            _require_tenant_for_non_super_admin(effective_roles, effective_tenant_id)
            _reject_super_admin_role_combination(effective_roles)
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
