"""Resolution of ``${secret:NAME}`` placeholders to secret values.

The resolver is the single component that turns a secret *reference* into its
plaintext value, used by every consumer:

* :class:`services.mcp_server.MCPServerService` and the agent proxy tools in
  :mod:`infrastructure.mcp_tools` resolve placeholders inside MCP server
  header values before connecting.
* :class:`services.workflow.WorkflowService` resolves an AgentSkill's
  ``repo_auth_secret`` (a bare secret name) before cloning.

The module lives in the infrastructure layer (not ``services``) because
:mod:`infrastructure.mcp_tools` needs it: an infrastructure module importing
the services package would create an import cycle through
:mod:`infrastructure.agent`.

``local`` secrets are decrypted from the database; ``vault`` secrets are read
live from HashiCorp Vault. Every failure mode — unknown name, undecryptable
ciphertext, Vault error, Vault not configured — raises
:class:`~repositories.exceptions.SecretResolutionError` naming the secret, so
a stale reference fails with an actionable message at use time.
"""

import re

from infrastructure.secret_cipher import SecretCipher
from infrastructure.vault_client import VaultClient, VaultError
from models.secret import Secret, SecretType
from repositories import SecretRepository
from repositories.exceptions import SecretResolutionError

#: Matches ``${secret:NAME}`` where NAME uses the slug charset enforced by
#: :data:`models.constraints.SecretName`.
PLACEHOLDER_PATTERN = re.compile(r"\$\{secret:([A-Za-z0-9._-]+)\}")


class SecretResolver:
    """Resolves secret names and placeholder-bearing text to plaintext values."""

    def __init__(
        self,
        repo: SecretRepository,
        cipher: SecretCipher,
        vault: VaultClient | None,
    ) -> None:
        """Initialize the resolver.

        Args:
            repo: Repository used to look secrets up by name.
            cipher: Cipher used to decrypt local secret values.
            vault: Vault client for ``vault``-type secrets, or ``None`` when no
                Vault connection is configured (resolving a vault secret then
                fails with :class:`SecretResolutionError`).
        """
        self._repo = repo
        self._cipher = cipher
        self._vault = vault

    async def resolve_value(self, name: str) -> str:
        """Return the plaintext value of the secret with the given name.

        Args:
            name: The secret's unique name.

        Returns:
            The plaintext secret value.

        Raises:
            SecretResolutionError: If the secret does not exist, its stored
                ciphertext cannot be decrypted, Vault is not configured, or the
                Vault read fails.
        """
        secret = await self._repo.get_by_name(name)
        if secret is None:
            raise SecretResolutionError(name, "no secret with this name exists")
        if secret.type is SecretType.local:
            return self._decrypt(secret)
        return await self._read_vault(secret)

    async def resolve_text(self, text: str) -> str:
        """Replace every ``${secret:NAME}`` placeholder in the text.

        Text without placeholders is returned unchanged (and costs no lookups).

        Args:
            text: The text possibly containing placeholders.

        Returns:
            The text with every placeholder replaced by its secret value.

        Raises:
            SecretResolutionError: If any referenced secret fails to resolve.
        """
        result: list[str] = []
        cursor = 0
        for match in PLACEHOLDER_PATTERN.finditer(text):
            result.append(text[cursor : match.start()])
            result.append(await self.resolve_value(match.group(1)))
            cursor = match.end()
        if not result:
            return text
        result.append(text[cursor:])
        return "".join(result)

    async def resolve_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Resolve placeholders in every value of a header mapping.

        Args:
            headers: Header names to values, possibly containing placeholders.

        Returns:
            A new mapping with all placeholders replaced; keys are untouched.

        Raises:
            SecretResolutionError: If any referenced secret fails to resolve.
        """
        return {key: await self.resolve_text(value) for key, value in headers.items()}

    def _decrypt(self, secret: Secret) -> str:
        """Decrypt a local secret's stored ciphertext.

        Args:
            secret: A ``local``-type secret row.

        Returns:
            The plaintext value.

        Raises:
            SecretResolutionError: If the row has no ciphertext or decryption
                fails (e.g. the encryption key changed).
        """
        if secret.value is None:
            raise SecretResolutionError(secret.name, "local secret has no stored value")
        try:
            return self._cipher.decrypt(secret.value)
        except ValueError as exc:
            raise SecretResolutionError(secret.name, str(exc)) from exc

    async def _read_vault(self, secret: Secret) -> str:
        """Read a vault secret's value from HashiCorp Vault.

        Args:
            secret: A ``vault``-type secret row.

        Returns:
            The value fetched from Vault.

        Raises:
            SecretResolutionError: If Vault is not configured, the reference is
                incomplete, or the read fails.
        """
        if self._vault is None:
            raise SecretResolutionError(
                secret.name,
                "no Vault connection is configured (set VAULT_ADDR and credentials)",
            )
        if not (secret.vault_mount and secret.vault_path and secret.vault_key):
            raise SecretResolutionError(secret.name, "incomplete Vault reference")
        try:
            return await self._vault.read_kv2(
                secret.vault_mount, secret.vault_path, secret.vault_key
            )
        except VaultError as exc:
            raise SecretResolutionError(secret.name, exc.reason) from exc
