"""Role-based authorization FastAPI dependencies.

``require_roles`` builds a route dependency that gates an endpoint behind one
or more :class:`~models.user.Role` grants. It composes with the router-level
``get_current_user`` guard (FastAPI caches the resolved user per request, so
no second auth lookup happens) and raises :class:`ForbiddenError` — mapped to
HTTP 403 ``FORBIDDEN`` by the global exception handlers — when the caller
holds neither a listed role nor ``super_admin``.

Both gates check **effective** roles: the caller's direct ``users.roles``
grants unioned with the roles inherited from every
:class:`~models.user_group.UserGroup` they belong to. That union is resolved
once per request by ``dependencies.auth.get_effective_roles``, which is what
these dependencies consume — they never see the ``User`` itself.

``require_actor_roles`` is the same check built on ``ActorEffectiveRolesDep``
(derived from the real, session-cookie identity) instead of
``EffectiveRolesDep`` (derived from the possibly-impersonated effective
identity). It exists solely for the impersonate
start/stop routes: once impersonating, every request — including the "stop"
call itself — carries the impersonation header, so gating those two routes
with the ordinary, ``CurrentUserDep``-based ``require_roles`` would resolve
the role check against the (deliberately non-admin) impersonation target and
permanently lock an impersonating admin out of ever stopping. Every other
route should keep using ``require_roles``.
"""

from collections.abc import Callable

from models.user import Role, has_any_role
from repositories.exceptions import ForbiddenError

from .auth import ActorEffectiveRolesDep, EffectiveRolesDep


def require_roles(*allowed: Role) -> Callable[[EffectiveRolesDep], None]:
    """Build a route dependency requiring one of the given roles.

    The check runs against the caller's **effective** roles — their direct
    grants unioned with the roles inherited from every group they belong to
    (see :func:`dependencies.auth.get_effective_roles`). ``super_admin``
    always passes (see :func:`~models.user.has_any_role`). Attach the result
    to a route with ``dependencies=[Depends(require_roles(...))]``.

    Args:
        allowed: Roles that grant access to the route.

    Returns:
        A dependency callable that raises :class:`ForbiddenError` when the
        authenticated user holds none of the allowed roles.
    """

    def _check(roles: EffectiveRolesDep) -> None:
        """Reject the request unless the current user holds an allowed role.

        Args:
            roles: The effective roles resolved by ``get_effective_roles``.

        Raises:
            ForbiddenError: If the user holds neither an allowed role nor
                ``super_admin``.
        """
        if not has_any_role(roles, *allowed):
            required = ", ".join(role.value for role in allowed)
            raise ForbiddenError(f"Requires one of the roles: {required}")

    return _check


def require_actor_roles(*allowed: Role) -> Callable[[ActorEffectiveRolesDep], None]:
    """Build a route dependency requiring one of the given roles, checked against the real actor.

    Identical to :func:`require_roles` except it checks
    ``ActorEffectiveRolesDep`` (the real session user's effective roles,
    unaffected by impersonation) rather than ``EffectiveRolesDep`` — see the
    module docstring for why that distinction is required for the
    impersonate start/stop routes specifically.

    Args:
        allowed: Roles that grant access to the route.

    Returns:
        A dependency callable that raises :class:`ForbiddenError` when the
        real, session-authenticated user holds none of the allowed roles.
    """

    def _check(roles: ActorEffectiveRolesDep) -> None:
        """Reject the request unless the real actor holds an allowed role.

        Args:
            roles: The real actor's effective roles, resolved by
                ``get_actor_effective_roles``.

        Raises:
            ForbiddenError: If the user holds neither an allowed role nor
                ``super_admin``.
        """
        if not has_any_role(roles, *allowed):
            required = ", ".join(role.value for role in allowed)
            raise ForbiddenError(f"Requires one of the roles: {required}")

    return _check
