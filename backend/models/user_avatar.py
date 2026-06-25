"""User avatar model holding an uploaded image as a database blob.

A :class:`UserAvatar` stores the custom image a user uploaded, kept in a table
separate from :class:`~models.user.User` so the (potentially large) binary is
never loaded by the auth path that reads the user row on every request. There is
at most one avatar per user (a unique ``user_id``); its presence is mirrored onto
``User.avatar_updated_at`` so read views can report it without an extra query.
"""

from sqlalchemy import ForeignKeyConstraint, LargeBinary, UniqueConstraint
from sqlmodel import Field

from models.base import BaseEntity


class UserAvatar(BaseEntity, table=True):
    """Database-persisted custom avatar image for a single user.

    ``user_id`` references the owning user (``ON DELETE CASCADE``), so removing
    the user removes their avatar. ``data`` holds the raw image bytes and
    ``content_type`` the matching MIME type (e.g. ``image/png``) used when the
    image is served back. The inherited ``created_by`` / ``updated_by`` record
    the actor that uploaded or last replaced the image.
    """

    __tablename__ = "user_avatars"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_user_avatars_user_id"),
        ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_user_avatars_user_id",
        ),
    )

    user_id: str
    data: bytes = Field(sa_type=LargeBinary)
    content_type: str
