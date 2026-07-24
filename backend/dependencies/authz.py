"""Role-based authorization FastAPI dependencies.

``require_roles`` builds a route dependency that gates an endpoint behind one
or more :class:`~models.user.Role` grants. It composes with the router-level
``get_current_user`` guard (FastAPI caches the resolved user per request, so
no second auth lookup happens) and raises :class:`ForbiddenError` — mapped to
HTTP 403 ``FORBIDDEN`` by the global exception handlers — when the caller
holds neither a listed role nor ``super_admin``.

``require_actor_roles`` is the same check built on ``RealUserDep`` (the real,
session-cookie identity) instead of ``CurrentUserDep`` (the possibly-
impersonated effective identity). It exists solely for the impersonate
start/stop routes: once impersonating, every request — including the "stop"
call itself — carries the impersonation header, so gating those two routes
with the ordinary, ``CurrentUserDep``-based ``require_roles`` would resolve
the role check against the (deliberately non-admin) impersonation target and
permanently lock an impersonating admin out of ever stopping. Every other
route should keep using ``require_roles``.
"""

from collections.abc import Callable

from models.user import Role, has_role
from repositories.exceptions import ForbiddenError

from .auth import CurrentUserDep, RealUserDep


def require_roles(*allowed: Role) -> Callable[[CurrentUserDep], None]:
    """Build a route dependency requiring one of the given roles.

    ``super_admin`` always passes (see :func:`~models.user.has_role`). Attach
    the result to a route with ``dependencies=[Depends(require_roles(...))]``.

    Args:
        allowed: Roles that grant access to the route.

    Returns:
        A dependency callable that raises :class:`ForbiddenError` when the
        authenticated user holds none of the allowed roles.
    """

    def _check(user: CurrentUserDep) -> None:
        """Reject the request unless the current user holds an allowed role.

        Args:
            user: The authenticated user resolved by ``get_current_user``.

        Raises:
            ForbiddenError: If the user holds neither an allowed role nor
                ``super_admin``.
        """
        if not has_role(user, *allowed):
            required = ", ".join(role.value for role in allowed)
            raise ForbiddenError(f"Requires one of the roles: {required}")

    return _check


def require_actor_roles(*allowed: Role) -> Callable[[RealUserDep], None]:
    """Build a route dependency requiring one of the given roles, checked against the real actor.

    Identical to :func:`require_roles` except it checks ``RealUserDep``
    (unaffected by impersonation) rather than ``CurrentUserDep`` — see the
    module docstring for why that distinction is required for the
    impersonate start/stop routes specifically.

    Args:
        allowed: Roles that grant access to the route.

    Returns:
        A dependency callable that raises :class:`ForbiddenError` when the
        real, session-authenticated user holds none of the allowed roles.
    """

    def _check(user: RealUserDep) -> None:
        """Reject the request unless the real actor holds an allowed role.

        Args:
            user: The real user resolved by ``get_session_user``.

        Raises:
            ForbiddenError: If the user holds neither an allowed role nor
                ``super_admin``.
        """
        if not has_role(user, *allowed):
            required = ", ".join(role.value for role in allowed)
            raise ForbiddenError(f"Requires one of the roles: {required}")

    return _check
