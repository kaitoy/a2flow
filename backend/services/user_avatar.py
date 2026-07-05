"""Use case service for custom user avatars.

Validates uploaded images (allowed MIME types and a maximum size) before
delegating persistence to the :class:`UserAvatarRepository`, and raises
:class:`NotFoundError` when a requested avatar does not exist so the router
never repeats the null check.
"""

from models.user_avatar import UserAvatar
from repositories import UserAvatarRepository
from repositories.exceptions import AvatarValidationError, NotFoundError

#: MIME types accepted for an uploaded avatar image.
ALLOWED_CONTENT_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/webp", "image/gif"}
)
#: Maximum accepted avatar size in bytes (2 MiB).
MAX_AVATAR_BYTES = 2 * 1024 * 1024


def _sniff_content_type(data: bytes) -> str | None:
    """Detect an image MIME type from its magic-byte signature.

    Used to verify that uploaded bytes actually are the type the client
    claimed via the ``Content-Type`` header, since that header is
    client-controlled and cannot be trusted on its own.

    Args:
        data: Raw file bytes to inspect.

    Returns:
        One of the values in :data:`ALLOWED_CONTENT_TYPES`, or ``None`` if
        the bytes do not match any recognized image signature.
    """
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class UserAvatarService:
    """Application service orchestrating custom user-avatar operations."""

    def __init__(self, repo: UserAvatarRepository) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing avatar persistence.
        """
        self._repo = repo

    async def get(self, user_id: str) -> UserAvatar:
        """Return the user's custom avatar.

        Args:
            user_id: Identifier of the owning user.

        Returns:
            The stored :class:`UserAvatar`.

        Raises:
            NotFoundError: If the user has no custom avatar.
        """
        avatar = await self._repo.get(user_id)
        if avatar is None:
            raise NotFoundError("UserAvatar", user_id)
        return avatar

    async def set(
        self, user_id: str, *, data: bytes, content_type: str, acting_user_id: str
    ) -> UserAvatar:
        """Validate and store (or replace) the user's custom avatar.

        Args:
            user_id: Identifier of the owning user.
            data: Raw image bytes to store.
            content_type: MIME type reported for the upload.
            acting_user_id: ID of the user performing the upload.

        Returns:
            The stored :class:`UserAvatar`.

        Raises:
            AvatarValidationError: If the type is unsupported, the image is
                empty or larger than :data:`MAX_AVATAR_BYTES`, or the file's
                actual bytes do not match the declared type.
            ForeignKeyViolationError: If the owning user does not exist.
        """
        normalized = content_type.split(";", 1)[0].strip().lower()
        if normalized not in ALLOWED_CONTENT_TYPES:
            raise AvatarValidationError(
                f"Unsupported image type {content_type!r}; "
                f"allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
            )
        if not data:
            raise AvatarValidationError("Image file is empty")
        if len(data) > MAX_AVATAR_BYTES:
            raise AvatarValidationError(
                f"Image exceeds the {MAX_AVATAR_BYTES // (1024 * 1024)} MiB size limit"
            )
        if _sniff_content_type(data) != normalized:
            raise AvatarValidationError(
                f"Image bytes do not match the declared type {content_type!r}"
            )
        return await self._repo.upsert(
            user_id,
            data=data,
            content_type=normalized,
            acting_user_id=acting_user_id,
        )

    async def remove(self, user_id: str) -> None:
        """Delete the user's custom avatar.

        Args:
            user_id: Identifier of the owning user.

        Raises:
            NotFoundError: If the user has no custom avatar.
        """
        await self._repo.delete(user_id)
