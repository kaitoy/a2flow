"""Role-based authorization FastAPI dependencies.

``require_roles`` builds a route dependency that gates an endpoint behind one
or more :class:`~models.user.Role` grants. It composes with the router-level
``get_current_user`` guard (FastAPI caches the resolved user per request, so
no second auth lookup happens) and raises :class:`ForbiddenError` — mapped to
HTTP 403 ``FORBIDDEN`` by the global exception handlers — when the caller
holds neither a listed role nor ``super_admin``.
"""

from collections.abc import Callable

from models.user import Role, has_role
from repositories.exceptions import ForbiddenError

from .auth import CurrentUserDep


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
