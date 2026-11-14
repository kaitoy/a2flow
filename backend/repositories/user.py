"""User repository: Protocol interface and SQLModel-backed implementation."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import Text, cast, func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from models.user import SYSTEM_USER_ID, User, UserCreate, UserRead, UserUpdate
from models.user_group import UserGroupMember
from repositories._integrity import is_foreign_key_error
from repositories.exceptions import (
    ForeignKeyViolationError,
    NotFoundError,
    UniqueViolationError,
)
from repositories.query import FilterSpec, SortSpec, apply_filters, apply_sort

#: Portable "roles contains super_admin" predicate for the JSON ``roles``
#: column, shared with :func:`list`'s ``visible_tenant_id`` scope. Mirrors the
#: ``CAST(roles AS TEXT) LIKE '%"super_admin"%'`` idiom already used by the
#: ``ck_users_super_admin_no_tenant`` / ``ck_users_non_super_admin_requires_tenant``
#: CHECK constraints (:class:`~models.user.User`) -- chosen there, and reused
#: here, because it works identically on SQLite's plain ``JSON`` and
#: PostgreSQL's ``jsonb``, unlike a native JSON "contains" operator.
_IS_SUPER_ADMIN = cast(col(User.roles), Text).like('%"super_admin"%')

#: Alias usable inside the classes below, whose ``list`` method shadows the builtin.
_UserList = list[User]


class UserRepository(Protocol):
    """Interface for User persistence operations."""

    async def get(self, user_id: str) -> User | None: ...

    async def get_many(self, user_ids: Sequence[str]) -> list[User]: ...

    async def get_by_username(
        self, username: str, *, tenant_id: str | None
    ) -> User | None: ...

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        visible_tenant_id: str | None = None,
        group_ids: Sequence[str] = (),
    ) -> list[User]: ...

    async def create(self, data: UserCreate, *, user_id: str) -> User: ...

    async def update(
        self, target_id: str, data: UserUpdate, *, user_id: str
    ) -> User: ...

    async def delete(self, user_id: str) -> None: ...

    async def exists(self, user_id: str) -> bool: ...

    async def clear_oidc_subjects(self, tenant_id: str) -> None: ...

    async def get_by_oidc_subject(
        self, tenant_id: str, subject: str
    ) -> User | None: ...

    async def list_by_email(self, tenant_id: str, email: str) -> _UserList: ...

    async def set_oidc_subject(self, user_id: str, subject: str) -> User: ...

    async def create_sso_user(
        self,
        *,
        tenant_id: str,
        username: str,
        first_name: str,
        last_name: str,
        email: str,
        email_verified: bool,
        oidc_subject: str,
    ) -> User: ...


class SqlUserRepository:
    """SQLModel-backed implementation of UserRepository.

    ``create`` and ``update`` catch IntegrityError on the ``username`` unique
    constraint and re-raise it as :class:`UniqueViolationError`. Passwords are
    expected to be already hashed by the service layer before reaching here.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def get(self, user_id: str) -> User | None:
        return await self._db.get(User, user_id)

    async def get_many(self, user_ids: Sequence[str]) -> list[User]:
        """Return every User whose id is in ``user_ids``, in unspecified order.

        Mirrors :meth:`get` rather than :meth:`list`: no ``deleted_at`` filter
        and no ``SYSTEM_USER_ID`` exclusion, because the display names of
        soft-deleted users and of the seeded system user must stay resolvable
        for the records they own. Ids with no matching row are simply absent
        from the result.

        Args:
            user_ids: Identifiers to look up. An empty sequence short-circuits
                without touching the database.

        Returns:
            The matching users.
        """
        if not user_ids:
            return []
        stmt = select(User).where(col(User.id).in_(user_ids))
        return list((await self._db.exec(stmt)).all())

    async def get_by_username(
        self, username: str, *, tenant_id: str | None
    ) -> User | None:
        """Return the user with the given username scoped to ``tenant_id``.

        ``tenant_id=None`` matches only platform-scoped users (``tenant_id IS
        NULL`` -- the seeded system user, ``root``, or any other
        super_admin); a non-``None`` value matches only users belonging to
        that tenant. This mirrors the two-tier uniqueness enforced by
        ``uq_users_tenant_id_username`` and the partial unique index on
        ``username`` where ``tenant_id IS NULL`` (see :class:`~models.user.User`).

        Soft-deleted users are included so the auth layer can reject a login
        with an explicit "disabled" decision rather than silently missing them.

        Args:
            username: The username to look up.
            tenant_id: The tenant to scope the lookup to, or ``None`` for a
                platform-scoped user.

        Returns:
            The matching ``User`` or ``None``.
        """
        tenant_filter = (
            col(User.tenant_id).is_(None)
            if tenant_id is None
            else col(User.tenant_id) == tenant_id
        )
        stmt = select(User).where(col(User.username) == username, tenant_filter)
        return (await self._db.exec(stmt)).first()

    async def exists(self, user_id: str) -> bool:
        return (await self._db.get(User, user_id)) is not None

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        sort: Sequence[SortSpec] = (),
        filters: Sequence[FilterSpec] = (),
        visible_tenant_id: str | None = None,
        group_ids: Sequence[str] = (),
    ) -> list[User]:
        """List users, optionally OR-scoped to a tenant plus every super_admin.

        ``visible_tenant_id``, when set, restricts the result to rows where
        either ``tenant_id`` matches it or the row holds the ``super_admin``
        role -- the visibility a super_admin actor gets for the tenant they
        are currently acting as (see :meth:`services.user.UserService.list`).
        A non-super-admin actor's own-tenant restriction is expressed instead
        as a ``FilterSpec`` in ``filters`` and this parameter is left unset,
        since it combines with (never widens past) the caller-supplied
        filters the same way.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.
            sort: Ordering instructions applied to the query.
            filters: Field filters applied to the query (AND-combined).
            visible_tenant_id: When set, OR-scopes the result to this tenant
                plus every super_admin, regardless of ``filters``.
            group_ids: Ids of the groups a user must belong to (AND-combined,
                mirroring the taggable resources' ``tag`` filter). One
                correlated ``EXISTS`` subquery per group, since membership
                lives in :class:`~models.user_group.UserGroupMember` rather
                than a column of ``users``.

        Returns:
            The requested page of users.
        """
        stmt = (
            select(User)
            .where(col(User.deleted_at).is_(None))
            .where(col(User.id) != SYSTEM_USER_ID)
        )
        if visible_tenant_id is not None:
            stmt = stmt.where(
                or_(col(User.tenant_id) == visible_tenant_id, _IS_SUPER_ADMIN)
            )
        for group_id in group_ids:
            stmt = stmt.where(
                select(col(UserGroupMember.user_id))
                .where(
                    col(UserGroupMember.user_id) == col(User.id),
                    col(UserGroupMember.group_id) == group_id,
                )
                .exists()
            )
        stmt = apply_filters(stmt, User, filters, readable=UserRead)
        stmt = apply_sort(
            stmt,
            User,
            sort,
            default=[col(User.created_at).desc()],
            readable=UserRead,
        )
        result = await self._db.exec(stmt.limit(limit).offset(offset))
        return list(result.all())

    async def create(self, data: UserCreate, *, user_id: str) -> User:
        user = User.model_validate(
            {**data.model_dump(), "created_by": user_id, "updated_by": user_id}
        )
        self._db.add(user)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            raise UniqueViolationError("User", "username", data.username) from e
        await self._db.refresh(user)
        return user

    async def update(self, target_id: str, data: UserUpdate, *, user_id: str) -> User:
        user = await self._db.get(User, target_id)
        if user is None:
            raise NotFoundError("User", target_id)
        update = data.model_dump(exclude_unset=True)
        user.sqlmodel_update(update)
        user.updated_by = user_id
        self._db.add(user)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            if is_foreign_key_error(e):
                raise ForeignKeyViolationError("User", user_id) from e
            raise UniqueViolationError(
                "User", "username", str(update.get("username", ""))
            ) from e
        await self._db.refresh(user)
        return user

    async def delete(self, user_id: str) -> None:
        """Delete a user, falling back to a soft delete when still referenced.

        A hard delete is attempted first. If the user is referenced by other
        records through ``created_by`` / ``updated_by`` (``ondelete=RESTRICT``),
        the database raises an IntegrityError; the user is then soft-deleted by
        setting ``deleted_at`` and disabling the account, so existing references
        stay valid and the name can still be resolved. The soft delete also
        clears ``oidc_subject``, freeing the subject for a fresh SSO account.

        Args:
            user_id: Identifier of the user to delete.

        Raises:
            NotFoundError: If no user exists with the given ID.
        """
        user = await self._db.get(User, user_id)
        if user is None:
            raise NotFoundError("User", user_id)
        try:
            await self._db.delete(user)
            await self._db.commit()
        except IntegrityError:
            await self._db.rollback()
            user = await self._db.get(User, user_id)
            if user is None:
                raise NotFoundError("User", user_id) from None
            user.deleted_at = datetime.now(UTC)
            user.enabled = False
            # A soft-deleted row keeps its unique slot otherwise, so the same
            # person could never be re-provisioned by SSO under that subject.
            user.oidc_subject = None
            self._db.add(user)
            await self._db.commit()

    async def clear_oidc_subjects(self, tenant_id: str) -> None:
        """Forget every OIDC subject linked to the tenant's users.

        Subjects are only unique per issuer and client, so they must not
        survive a change of either: each user re-links at their next SSO
        sign-in.

        Does not commit: the caller's next commit (the tenant update that
        changes the provider) makes the reset permanent, and a rollback
        discards it, so the two always land together.

        Args:
            tenant_id: Identifier of the tenant whose users are reset.
        """
        await self._db.exec(
            update(User)
            .where(col(User.tenant_id) == tenant_id)
            .values(oidc_subject=None)
        )

    async def get_by_oidc_subject(self, tenant_id: str, subject: str) -> User | None:
        """Return the tenant's user linked to the OIDC subject ``subject``.

        Disabled and soft-deleted users are included, so the caller can refuse
        them explicitly.

        Args:
            tenant_id: The tenant to search.
            subject: The provider's ``sub`` claim.

        Returns:
            The linked user, or ``None``.
        """
        stmt = select(User).where(
            col(User.tenant_id) == tenant_id, col(User.oidc_subject) == subject
        )
        return (await self._db.exec(stmt)).first()

    async def list_by_email(self, tenant_id: str, email: str) -> _UserList:
        """Return the tenant's non-deleted users whose e-mail matches ``email``.

        The match ignores case and surrounding whitespace on both sides.

        Args:
            tenant_id: The tenant to search.
            email: The e-mail address to match.

        Returns:
            Every matching user, linked to an OIDC subject or not.
        """
        stmt = select(User).where(
            col(User.tenant_id) == tenant_id,
            col(User.deleted_at).is_(None),
            func.lower(func.trim(col(User.email))) == email.strip().lower(),
        )
        return list((await self._db.exec(stmt)).all())

    async def set_oidc_subject(self, user_id: str, subject: str) -> User:
        """Link a user to an OIDC subject and commit.

        Args:
            user_id: The user to link.
            subject: The provider's ``sub`` claim.

        Returns:
            The updated user.

        Raises:
            NotFoundError: If the user does not exist.
            UniqueViolationError: If another user of the tenant already holds
                ``subject``.
        """
        user = await self._db.get(User, user_id)
        if user is None:
            raise NotFoundError("User", user_id)
        user.oidc_subject = subject
        self._db.add(user)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            raise UniqueViolationError("User", "oidc_subject", subject) from e
        await self._db.refresh(user)
        return user

    async def create_sso_user(
        self,
        *,
        tenant_id: str,
        username: str,
        first_name: str,
        last_name: str,
        email: str,
        email_verified: bool,
        oidc_subject: str,
    ) -> User:
        """Create a password-less user provisioned by OIDC single sign-on.

        The user has no direct roles and is owned by the system user.

        Args:
            tenant_id: The tenant the user belongs to.
            username: A free, already-normalised username.
            first_name: Given name.
            last_name: Family name.
            email: E-mail address.
            email_verified: Whether the identity provider vouched for ``email``.
            oidc_subject: The provider's ``sub`` claim.

        Returns:
            The created user.

        Raises:
            UniqueViolationError: If the username or subject was taken
                concurrently.
        """
        user = User(
            tenant_id=tenant_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
            email_verified=email_verified,
            oidc_subject=oidc_subject,
            password=None,
            roles=[],
            created_by=SYSTEM_USER_ID,
            updated_by=SYSTEM_USER_ID,
        )
        self._db.add(user)
        try:
            await self._db.commit()
        except IntegrityError as e:
            await self._db.rollback()
            raise UniqueViolationError("User", "username", username) from e
        await self._db.refresh(user)
        return user
