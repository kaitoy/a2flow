"""Platform-wide system settings: the SMTP relay used for notification email.

A2Flow's notifications are otherwise in-app only — a row in ``notifications``
that the toolbar bell polls for. This table holds the one piece of
configuration needed to also deliver them by email: where to hand a message to,
and what address to send it from.

The record is **platform-scoped, not tenant-scoped**: it inherits
:class:`~models.base.BaseEntity` alone, the same shape as
:class:`~models.tenant.Tenant`, and only a ``super_admin`` may read or write it.
Exactly one row ever exists — its primary key is pinned to
:data:`SYSTEM_SETTINGS_ID` and a check constraint makes that a database
invariant rather than a convention.

``smtp_password`` follows the write-only pattern of
:class:`models.secret.Secret.entries` and :class:`models.user.User.password`: it
is stored as Fernet ciphertext (encrypted in
:class:`services.system_settings.SystemSettingsService`, never by the
repository) and never serialized to a client. Responses use
:class:`SystemSettingsRead`, which replaces it with the bare
``smtp_password_set`` flag so the admin UI can tell "a password is stored" from
"no password is stored" without receiving either one.
"""

from enum import StrEnum

from pydantic import EmailStr
from pydantic.alias_generators import to_camel
from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel
from sqlmodel._compat import SQLModelConfig

from models.base import BaseEntity
from models.constraints import AppBaseUrl, PersonName, ShortText, SmtpHost

_alias_config = SQLModelConfig(alias_generator=to_camel, populate_by_name=True)

#: Primary key of the single ``system_settings`` row. Fixed rather than
#: generated so every caller can address the record without first looking up
#: which id it happens to have.
SYSTEM_SETTINGS_ID = "00000000-0000-0000-0000-000000000001"

#: Default submission port, used when no port has been configured. 587 is the
#: RFC 6409 message-submission port, which pairs with ``starttls``.
DEFAULT_SMTP_PORT = 587


class SmtpSecurity(StrEnum):
    """How the connection to the SMTP relay is secured."""

    #: Plain, unencrypted SMTP. Appropriate only for a relay on the loopback
    #: interface or inside a trusted network segment.
    none = "none"
    #: Connect in the clear, then upgrade with ``STARTTLS`` before authenticating.
    starttls = "starttls"
    #: Implicit TLS from the first byte (``SMTPS``, conventionally port 465).
    ssl = "ssl"


class SystemSettingsUpdate(SQLModel):
    """Partial update payload for the system settings — all fields are optional.

    Omitting ``smtp_password`` leaves the stored ciphertext untouched. Since
    clients never receive the stored value, an **empty string** carries the same
    meaning as omitting it — "keep the password already stored" — which is why
    the field is a plain ``str`` rather than a length-bounded alias. This
    mirrors :class:`models.secret.SecretUpdate.entries`. An explicit ``null``
    is the one way to actually clear it — a blank form field never produces
    one, since the field is either omitted or sent as ``""`` — so it is
    reserved for a deliberate "clear the password" action.

    The cross-field rules (which fields must be present once SMTP is enabled)
    are enforced against the merged result by
    :class:`services.system_settings.SystemSettingsService`, because a PATCH
    body alone cannot know the effective configuration.
    """

    model_config = _alias_config
    app_base_url: AppBaseUrl | None = None
    smtp_enabled: bool | None = None
    smtp_host: SmtpHost | None = None
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_security: SmtpSecurity | None = None
    smtp_username: ShortText | None = None
    smtp_password: str | None = Field(default=None, max_length=1024)
    smtp_from_email: EmailStr | None = None
    smtp_from_name: PersonName | None = None


class SystemSettings(SystemSettingsUpdate, BaseEntity, table=True):
    """The single, database-persisted row of platform-wide settings.

    Not tenant-scoped: these settings apply to every tenant on the deployment.
    ``smtp_password`` holds Fernet ciphertext and is never exposed through the
    API — every route responds with :class:`SystemSettingsRead`.
    """

    __tablename__ = "system_settings"
    __table_args__ = (
        CheckConstraint(
            f"id = '{SYSTEM_SETTINGS_ID}'", name="ck_system_settings_singleton"
        ),
    )

    #: Email delivery is opt-in: a fresh deployment keeps notifications in-app
    #: until an operator has configured and verified a relay.
    smtp_enabled: bool = False
    smtp_port: int = DEFAULT_SMTP_PORT
    smtp_security: SmtpSecurity = SmtpSecurity.starttls


class SystemSettingsRead(BaseEntity):
    """Read view of the system settings, excluding the SMTP password.

    ``smtp_password_set`` reports only whether a password is stored, so the
    admin UI can show the field as already configured without ever receiving
    the value — the same shape as :attr:`models.secret.SecretRead.keys`.
    """

    model_config = _alias_config
    app_base_url: str | None = None
    smtp_enabled: bool = False
    smtp_host: str | None = None
    smtp_port: int = DEFAULT_SMTP_PORT
    smtp_security: SmtpSecurity = SmtpSecurity.starttls
    smtp_username: str | None = None
    smtp_from_email: str | None = None
    smtp_from_name: str | None = None
    #: Whether a password is stored. The password itself is never serialized.
    smtp_password_set: bool = False

    @classmethod
    def from_settings(cls, settings: SystemSettings) -> "SystemSettingsRead":
        """Build the read view of the stored settings, dropping the password.

        Args:
            settings: The persisted (or default, unsaved) settings row.

        Returns:
            A read view carrying every field except ``smtp_password``, plus the
            ``smtp_password_set`` flag derived from it.
        """
        return cls(
            **settings.model_dump(exclude={"smtp_password"}),
            smtp_password_set=bool(settings.smtp_password),
        )
