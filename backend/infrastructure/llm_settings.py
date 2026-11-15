"""Which LLM a tenant's agents run on, and the key it is reached with.

There are two layers of stored settings:

* the platform-wide LLM (:class:`~models.system_settings.SystemSettings`
  ``llm_model`` / ``llm_api_key``), which ``SYSTEM_DEFAULT_LLM_MODEL`` and
  ``SYSTEM_DEFAULT_LLM_API_KEY`` overwrite at every startup when set (see
  :func:`infrastructure.bootstrap.apply_system_settings_env_overrides`), and
* a tenant's own (:class:`~models.tenant.Tenant` ``llm_*``), which applies only
  while its :class:`~models.tenant.LlmMode` is not ``system_default``.

How the two layers combine depends on who set the tenant's values. A
``super_admin`` may override the model or the key alone and inherit the other.
The tenant's own ``admin`` (``tenant_admin`` mode) may not lean on the
platform's key: without a key of the tenant's own, its model is ignored too and
the tenant runs on the platform's LLM unchanged -- otherwise an admin could
pick any model and bill it to the platform, or send the platform's key to
another provider.

:class:`LlmSettingsResolver` folds them into one :class:`ResolvedLlm`. Nothing at
run time reads the environment: the variables above only ever reach the
database. The one exception is a key left empty at both layers -- then none is
passed, and the provider's own variable (``GOOGLE_API_KEY``, ``OPENAI_API_KEY``,
``AWS_BEARER_TOKEN_BEDROCK`` ...) is what litellm and google-genai read, as
before.
"""

from dataclasses import dataclass, field

from sqlmodel.ext.asyncio.session import AsyncSession

from infrastructure.secret_cipher import SecretCipher
from models.system_settings import SYSTEM_SETTINGS_ID, SystemSettings
from models.tenant import LlmMode, Tenant

#: The model used when neither the tenant nor the platform names one.
DEFAULT_LLM_MODEL = "gemini-3.8-flash"


@dataclass(frozen=True)
class ResolvedLlm:
    """The LLM one tenant's agents run on.

    Frozen and hashable: :class:`infrastructure.agent.AgentRegistry` keys its
    cache on it, so an edit of the settings builds a new agent instead of
    reusing one that still carries the old model.

    Attributes:
        model: ``litellm:<provider>/<model>`` or a bare Gemini model name.
        api_key: The decrypted API key, or ``None`` to leave it to the
            provider's own environment variable. Left out of ``repr`` so it
            never reaches a log line.
    """

    model: str
    api_key: str | None = field(default=None, repr=False)


class LlmSettingsResolver:
    """Resolves the LLM a tenant runs on from the stored settings."""

    def __init__(self, session: AsyncSession, cipher: SecretCipher) -> None:
        """Store the session the settings rows are read through and the cipher.

        Args:
            session: The SQLModel async session to read the rows with.
            cipher: Cipher that decrypts the stored API keys.
        """
        self._db = session
        self._cipher = cipher

    async def resolve(self, tenant_id: str) -> ResolvedLlm:
        """Return the LLM ``tenant_id``'s agents run on.

        In ``super_admin`` mode a field the tenant leaves empty falls back to
        the platform-wide one. In ``tenant_admin`` mode the tenant's values
        apply only when it has a key of its own (its model may still be empty,
        falling back to the platform's); without one, the platform's model and
        key are used as they are. An empty platform-wide model falls back to
        :data:`DEFAULT_LLM_MODEL`.

        Args:
            tenant_id: The tenant the agent runs for.

        Returns:
            The model and the decrypted key (``None`` when neither layer has
            one).

        Raises:
            ValueError: If the stored key no longer decrypts because the Fernet
                key changed. Deliberately not swallowed: falling back to the
                platform's key would silently bill the wrong account.
        """
        system = await self._db.get(SystemSettings, SYSTEM_SETTINGS_ID)
        model = system.llm_model if system else None
        api_key = system.llm_api_key if system else None
        tenant = await self._db.get(Tenant, tenant_id)
        if tenant is not None and (
            tenant.llm_mode == LlmMode.super_admin
            or (tenant.llm_mode == LlmMode.tenant_admin and tenant.llm_api_key)
        ):
            model = tenant.llm_model or model
            api_key = tenant.llm_api_key or api_key
        return ResolvedLlm(
            model=model or DEFAULT_LLM_MODEL,
            api_key=self._cipher.decrypt(api_key) if api_key else None,
        )
