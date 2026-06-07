"""Use case service for User resources.

Wraps the :class:`UserRepository` with the business rules the routers need:
hashing passwords before persistence (so the repository only ever stores a
bcrypt hash) and raising :class:`NotFoundError` when a user is missing.
"""

from collections.abc import Sequence

from infrastructure.password import hash_password
from models.user import User, UserCreate, UserUpdate
from repositories import UserRepository
from repositories.exceptions import NotFoundError
from repositories.query import FilterSpec, SortSpec


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

    async def create(self, data: UserCreate, *, user_id: str) -> User:
        """Create a new User, hashing the supplied password before persistence.

        Args:
            data: Fields for the new user (with a plaintext password).
            user_id: ID of the user creating the record.

        Returns:
            The created User.
        """
        hashed = data.model_copy(update={"password": hash_password(data.password)})
        return await self._repo.create(hashed, user_id=user_id)

    async def update(self, target_id: str, data: UserUpdate, *, user_id: str) -> User:
        """Apply a partial update to a User.

        A blank or omitted password leaves the stored password unchanged; a
        non-empty password is hashed before persistence.

        Args:
            target_id: Identifier of the user to update.
            data: Fields to update (password optional).
            user_id: ID of the user performing the update.

        Returns:
            The updated User.

        Raises:
            NotFoundError: If no user exists with the given ID.
        """
        update = data.model_dump(exclude_unset=True)
        password = update.get("password")
        if password:
            update["password"] = hash_password(password)
        else:
            update.pop("password", None)
        return await self._repo.update(target_id, UserUpdate(**update), user_id=user_id)

    async def delete(self, user_id: str) -> None:
        """Delete a User.

        Args:
            user_id: Identifier of the user to delete.

        Raises:
            NotFoundError: If no user exists with the given ID.
        """
        await self._repo.delete(user_id)
