"""Use-case service for impersonation: acting as another user.

Impersonation is a request-header override, not a session swap (see
``dependencies/auth.py``): the real session cookie never changes, and
:meth:`ImpersonationService.resolve_effective_user` is consulted on every
request that carries the ``X-Impersonate-User-Id`` header, not just at
:meth:`start`. This service owns the eligibility rules (who may impersonate
whom) and the persistent audit trail (:class:`~models.impersonation_event.ImpersonationEvent`).
"""

from models.user import SYSTEM_USER_ID, Role, User
from repositories import ImpersonationEventRepository, UserRepository
from repositories.exceptions import ForbiddenError, NotFoundError


def _target_ineligible_for_actor(*, actor: User, target: User) -> bool:
    """Return whether ``actor`` is barred from impersonating ``target`` by role.

    A ``super_admin``-held target can never be impersonated, by anyone. An
    ``admin``-held target can only be impersonated by an actor who themself
    holds ``super_admin`` -- a regular admin still cannot impersonate a
    fellow admin. Deliberately checks raw role membership on both sides
    rather than :func:`~models.user.has_role`: that helper's
    ``super_admin``-bypass semantics test whether an *actor* satisfies a
    requirement, which is backwards for the target side, and for the actor
    side the bypass collapses to the same plain containment check anyway.

    Args:
        actor: The prospective impersonator.
        target: The prospective impersonation target.

    Returns:
        ``True`` if ``actor`` may not impersonate ``target``.
    """
    target_roles = set(target.roles or [])
    if Role.super_admin in target_roles:
        return True
    if Role.admin in target_roles:
        return Role.super_admin not in (actor.roles or [])
    return False


class ImpersonationService:
    """Application service orchestrating impersonation eligibility and audit trail."""

    def __init__(
        self, events: ImpersonationEventRepository, users: UserRepository
    ) -> None:
        """Initialize the service.

        Args:
            events: Repository for the impersonation audit trail.
            users: Repository for resolving prospective impersonation targets.
        """
        self._events = events
        self._users = users

    async def start(self, *, actor: User, target_user_id: str) -> User:
        """Validate eligibility and open a new impersonation event.

        Args:
            actor: The real, session-authenticated user requesting to
                impersonate someone else.
            target_user_id: Id of the user to impersonate.

        Returns:
            The target user.

        Raises:
            NotFoundError: If the target does not exist, or (for a non
                super_admin actor) belongs to a different tenant -- reported
                as "not found" rather than "forbidden" so a cross-tenant
                reference never confirms the target's existence, matching
                ``services/user.py``'s ``_assert_tenant_visible`` convention.
            ForbiddenError: If the target is the actor themself, the seeded
                system user, disabled, soft-deleted, holds ``super_admin``,
                or holds ``admin`` while the actor is not a ``super_admin``.
        """
        target = await self._users.get(target_user_id)
        if target is None:
            raise NotFoundError("User", target_user_id)
        if Role.super_admin not in (actor.roles or []) and (
            target.tenant_id != actor.tenant_id
        ):
            raise NotFoundError("User", target_user_id)
        if target.id == actor.id:
            raise ForbiddenError("Cannot impersonate yourself")
        if target.id == SYSTEM_USER_ID:
            raise ForbiddenError("Cannot impersonate the system user")
        if not target.enabled or target.deleted_at is not None:
            raise ForbiddenError("Cannot impersonate a disabled or deleted user")
        if _target_ineligible_for_actor(actor=actor, target=target):
            raise ForbiddenError("Cannot impersonate this user")

        await self._events.close_open_for_actor(actor.id)
        await self._events.create(impersonator_id=actor.id, target_user_id=target.id)
        return target

    async def stop(self, *, actor: User) -> None:
        """Close the actor's open impersonation event, if any.

        A no-op (never raises) when nothing is open, so a client can always
        safely call this regardless of its own local state.

        Args:
            actor: The real, session-authenticated user.
        """
        await self._events.close_open_for_actor(actor.id)

    async def resolve_effective_user(self, *, actor: User, target_user_id: str) -> User:
        """Resolve the effective identity for a request carrying the impersonation header.

        Called on every request, not just at :meth:`start`. Never raises: a
        header that no longer names a valid, open impersonation (stopped
        elsewhere, target since disabled/promoted, or -- since eligibility
        for an ``admin`` target also depends on the actor's own role -- the
        actor since demoted from ``super_admin``) silently falls back to the
        real actor and closes the stale event, rather than failing the
        request -- an error here would otherwise be able to lock a legitimate
        admin out of the whole app on a stale ``localStorage`` value (see
        ``dependencies/auth.py``'s module docs).

        Args:
            actor: The real, session-authenticated user.
            target_user_id: The id carried in the impersonation header.

        Returns:
            The target user if an open, still-valid impersonation matches,
            otherwise ``actor``.
        """
        event = await self._events.get_open(
            impersonator_id=actor.id, target_user_id=target_user_id
        )
        if event is None:
            return actor
        target = await self._users.get(target_user_id)
        if (
            target is None
            or not target.enabled
            or target.deleted_at is not None
            or _target_ineligible_for_actor(actor=actor, target=target)
        ):
            await self._events.close_open_for_actor(actor.id)
            return actor
        return target
