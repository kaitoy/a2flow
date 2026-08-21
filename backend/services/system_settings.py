"""Use case service for the platform-wide SystemSettings record.

Holds the two rules the router must not repeat and the repository must not see:

* **Encryption.** ``smtp_password`` reaches the repository as Fernet ciphertext
  and never as plaintext, the same split :class:`services.secret.SecretService`
  uses. An empty submitted value means "keep the stored ciphertext", so the
  admin UI can render the field blank without wiping the saved password on
  every save; an explicit ``null`` clears it instead, for a deliberate
  "clear the password" action.
* **Merged-result validation.** A PATCH body alone cannot tell whether the
  resulting configuration is usable — enabling delivery requires a host and a
  sender address that may already be stored. Only the service can compute the
  merge, so :class:`SystemSettingsValidationError` is raised here rather than by
  a model validator.

:meth:`SystemSettingsService.resolve_smtp` is the read side of the same split:
it decrypts once and hands back an :class:`~infrastructure.email_sender.SmtpConfig`,
or ``None`` when delivery is switched off or not configured — which is how every
caller decides not to send.
"""

import logging

from infrastructure.email_sender import SmtpConfig
from infrastructure.secret_cipher import SecretCipher
from models.system_settings import (
    SYSTEM_SETTINGS_ID,
    SystemSettings,
    SystemSettingsRead,
    SystemSettingsUpdate,
)
from repositories import SystemSettingsRepository
from repositories.exceptions import NotFoundError, SystemSettingsValidationError

logger = logging.getLogger(__name__)


class SystemSettingsService:
    """Application service orchestrating SystemSettings reads and updates."""

    def __init__(self, repo: SystemSettingsRepository, cipher: SecretCipher) -> None:
        """Initialize the service.

        Args:
            repo: Repository providing SystemSettings persistence.
            cipher: Cipher used to encrypt the SMTP password before storage and
                decrypt it when resolving a send configuration.
        """
        self._repo = repo
        self._cipher = cipher

    async def get(self) -> SystemSettings:
        """Return the settings row.

        Returns:
            The single settings record.

        Raises:
            NotFoundError: If the row is missing, which means the startup seed
                (:func:`infrastructure.bootstrap.seed_system_settings`) did not
                run against this database.
        """
        settings = await self._repo.get()
        if settings is None:
            raise NotFoundError("SystemSettings", SYSTEM_SETTINGS_ID)
        return settings

    async def update(
        self, data: SystemSettingsUpdate, *, user_id: str
    ) -> SystemSettings:
        """Apply a partial update, encrypting the password and validating the result.

        Args:
            data: Fields to apply. An unset or empty ``smtp_password`` keeps the
                stored ciphertext; an explicit ``None`` clears it.
            user_id: The acting user, recorded as ``updated_by``.

        Returns:
            The updated settings row.

        Raises:
            SystemSettingsValidationError: If the merged result would enable
                delivery without a usable configuration.
            NotFoundError: If the settings row is missing.
        """
        current = await self.get()
        payload = data.model_dump(exclude_unset=True)
        # Distinguish "key present" from "value truthy": an admitted empty
        # string keeps what is stored (a blank field in the admin form is
        # non-destructive), while an explicit `null` -- unreachable from a
        # blank form field, which always omits the key instead -- clears it.
        if "smtp_password" in payload:
            password = payload["smtp_password"]
            if password:
                payload["smtp_password"] = self._cipher.encrypt(password)
            elif password is not None:
                payload.pop("smtp_password")
        _assert_usable(current, payload)
        return await self._repo.update(
            SystemSettingsUpdate.model_construct(**payload), user_id=user_id
        )

    def to_read(self, settings: SystemSettings) -> SystemSettingsRead:
        """Project the settings row onto its password-free read view.

        Args:
            settings: The persisted settings row.

        Returns:
            The read view carrying ``smtp_password_set`` in place of the password.
        """
        return SystemSettingsRead.from_settings(settings)

    async def resolve_smtp(self) -> SmtpConfig | None:
        """Return a ready-to-send SMTP configuration, or ``None`` if unavailable.

        Returns:
            The resolved configuration with the password decrypted, or ``None``
            when delivery is disabled, the settings row is missing, or the
            stored password cannot be decrypted (which means the Fernet key
            changed since it was saved — see
            :mod:`infrastructure.secret_cipher`).
        """
        settings = await self._repo.get()
        if settings is None or not settings.smtp_enabled:
            return None
        if not settings.smtp_host or not settings.smtp_from_email:
            return None
        password: str | None = None
        if settings.smtp_password:
            try:
                password = self._cipher.decrypt(settings.smtp_password)
            except ValueError:
                logger.error(
                    "Stored SMTP password could not be decrypted; email delivery "
                    "is disabled until it is set again."
                )
                return None
        return SmtpConfig(
            host=settings.smtp_host,
            port=settings.smtp_port,
            security=settings.smtp_security,
            username=settings.smtp_username or None,
            password=password,
            from_email=settings.smtp_from_email,
            from_name=settings.smtp_from_name or None,
        )


def _assert_usable(current: SystemSettings, payload: dict[str, object]) -> None:
    """Reject an update whose merged result would enable unusable email delivery.

    Args:
        current: The stored settings row before the update.
        payload: The fields the caller actually set, password already encrypted.

    Raises:
        SystemSettingsValidationError: If delivery would be enabled without a
            relay host or sender address, or with a username but no password.
    """

    def merged(field: str) -> object:
        return payload[field] if field in payload else getattr(current, field)

    if not merged("smtp_enabled"):
        return
    if not merged("smtp_host"):
        raise SystemSettingsValidationError(
            "smtpHost is required when email delivery is enabled"
        )
    if not merged("smtp_from_email"):
        raise SystemSettingsValidationError(
            "smtpFromEmail is required when email delivery is enabled"
        )
    if merged("smtp_username") and not merged("smtp_password"):
        raise SystemSettingsValidationError(
            "smtpPassword is required when smtpUsername is set"
        )
