"""Shared write rule for a stored LLM API key.

The platform (:class:`services.system_settings.SystemSettingsService`) and each
tenant (:class:`services.tenant.TenantService`) store the key the same way, so
both run their PATCH payload through :func:`prepare_llm_fields`.
"""

from typing import Any

from infrastructure.secret_cipher import SecretCipher


def prepare_llm_fields(payload: dict[str, Any], cipher: SecretCipher) -> None:
    """Encrypt the submitted LLM API key, with the write-only semantics of a password.

    Mutates ``payload`` in place. A non-empty key is replaced by its ciphertext;
    an empty one is dropped so the stored ciphertext is kept (the form never
    receives it, so a blank field means "unchanged"); an explicit ``None`` is
    kept and clears it. A payload without ``llm_api_key`` is left alone.

    Args:
        payload: The fields the caller set.
        cipher: Cipher the key is encrypted with.
    """
    if "llm_api_key" not in payload:
        return
    key = payload["llm_api_key"]
    if key:
        payload["llm_api_key"] = cipher.encrypt(key)
    elif key is not None:
        payload.pop("llm_api_key")
