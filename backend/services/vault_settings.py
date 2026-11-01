"""Shared write rules for a stored Vault connection.

A tenant stores two Vault connections with the same rules -- its own
(:class:`models.tenant.TenantVaultFields`, ``vault_*``) and its credential for
the global Vault (:class:`models.tenant.TenantGlobalVaultFields`,
``global_vault_*``) -- so :class:`services.tenant.TenantService` runs each PATCH
payload through :func:`prepare_vault_fields` once per field prefix.
"""

from typing import Any

from pydantic.alias_generators import to_camel

from infrastructure.secret_cipher import SecretCipher
from models.tenant import VaultAuthMethod
from repositories.exceptions import ReasonError


def prepare_vault_fields(
    current: object | None,
    payload: dict[str, Any],
    cipher: SecretCipher,
    error: type[ReasonError],
    *,
    prefix: str = "vault_",
) -> None:
    """Encrypt the submitted Vault credential and validate the merged result.

    Mutates ``payload`` in place. A non-empty credential is replaced by its
    ciphertext; an empty one is dropped so the stored ciphertext is kept (the
    form never receives it, so a blank field means "unchanged"); an explicit
    ``None`` is kept and clears it. A payload that sets none of the prefix's
    fields is left alone, so an update of unrelated fields is never refused
    over this connection.

    Args:
        current: The stored record carrying the prefixed attributes, or
            ``None`` when there is none yet.
        payload: The fields the caller set.
        cipher: Cipher the credential is encrypted with.
        error: The validation error to raise, so each caller keeps its own
            error code.
        prefix: Field-name prefix of the connection: ``vault_`` for one with
            its own ``vault_addr``, ``global_vault_`` for a credential for the
            global Vault, whose address is stored elsewhere.

    Raises:
        ReasonError: (as ``error``) If the merged result is in use (it names an
            address, or for ``global_vault_`` an auth method or credential)
            but has no auth method or credential, switches the auth method
            while keeping the old method's credential, or names the AppRole
            method without a role id.
    """
    if not any(field.startswith(prefix) for field in payload):
        return
    credential_field = f"{prefix}credential"
    new_credential = False
    if credential_field in payload:
        credential = payload[credential_field]
        if credential:
            payload[credential_field] = cipher.encrypt(credential)
            new_credential = True
        elif credential is not None:
            payload.pop(credential_field)

    def merged(name: str) -> object:
        field = f"{prefix}{name}"
        if field in payload:
            return payload[field]
        return getattr(current, field, None)

    def camel(name: str) -> str:
        return to_camel(f"{prefix}{name}")

    if prefix == "vault_":
        in_use = merged("addr")
        trigger = f"{camel('addr')} is set"
    else:
        in_use = merged("auth_method") or merged("credential")
        trigger = "a global Vault credential is configured"
    if not in_use:
        return
    method = merged("auth_method")
    if method is None:
        raise error(f"{camel('auth_method')} is required when {trigger}")
    if not merged("credential"):
        raise error(f"{camel('credential')} is required when {trigger}")
    if (
        getattr(current, credential_field, None)
        and method != getattr(current, f"{prefix}auth_method", None)
        and not new_credential
    ):
        # A stored token must never be replayed as an AppRole secret id (or the
        # reverse): a method switch needs its own credential.
        raise error(
            f"{camel('credential')} is required when {camel('auth_method')} changes"
        )
    if method == VaultAuthMethod.approle and not merged("role_id"):
        raise error(f"{camel('role_id')} is required for the approle auth method")
