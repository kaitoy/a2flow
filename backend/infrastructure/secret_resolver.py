"""Resolution of ``${secret:NAME/KEY}`` placeholders to secret values.

The resolver is the single component that turns a secret *reference* into its
plaintext value, used by every consumer:

* :func:`infrastructure.mcp_client.resolve_connection` resolves placeholders
  inside MCP server header values (streamable HTTP) and environment variable
  values (stdio) before connecting, on behalf of
  :class:`services.mcp_server.MCPServerService` and the agent proxy tools in
  :mod:`infrastructure.mcp_tools`.
* :class:`services.workflow.WorkflowService` resolves an AgentSkill's
  ``repo_auth_password`` (a bare ``NAME/KEY`` reference) before cloning.

The module lives in the infrastructure layer (not ``services``) because
:mod:`infrastructure.mcp_tools` needs it: an infrastructure module importing
the services package would create an import cycle through
:mod:`infrastructure.agent`.

A secret holds a map of entries, so every reference must name a key — even when
the secret has exactly one entry. ``local`` entries are decrypted from the
database; ``vault`` entries are read live from HashiCorp Vault. Every failure
mode — unknown name, missing key, undecryptable ciphertext, Vault error, Vault
not configured — raises :class:`~repositories.exceptions.SecretResolutionError`
naming the secret, so a stale reference fails with an actionable message at use
time.
"""

import re

from infrastructure.secret_cipher import SecretCipher
from infrastructure.vault_client import VaultClient, VaultError
from models.secret import Secret, SecretType
from repositories import SecretRepository
from repositories.exceptions import SecretResolutionError

#: Matches ``${secret:NAME/KEY}`` where NAME uses the slug charset enforced by
#: :data:`models.constraints.SecretName`. The key group is optional so that a
#: key-less ``${secret:NAME}`` — invalid since a secret became a map of entries
#: — still matches and fails loudly, instead of slipping through unsubstituted
#: and reaching the MCP server as a literal string.
PLACEHOLDER_PATTERN = re.compile(r"\$\{secret:([A-Za-z0-9._-]+)(?:/([^}]+))?\}")

#: Reason reported when a reference names a secret but no entry within it.
_MISSING_KEY_REASON = "a key is required: reference the entry as ${secret:NAME/KEY}"


def split_secret_ref(ref: str) -> tuple[str, str | None]:
    """Split a ``NAME/KEY`` reference into its parts.

    Args:
        ref: The reference to split.

    Returns:
        The secret name and the entry key, the key being ``None`` when the
        reference carries no ``/``.
    """
    name, separator, key = ref.partition("/")
    return (name, key) if separator else (name, None)


class SecretResolver:
    """Resolves secret references and placeholder-bearing text to plaintext."""

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

    async def resolve_value(self, name: str, key: str) -> str:
        """Return the plaintext value of one entry of the named secret.

        Args:
            name: The secret's unique name.
            key: The entry key within that secret.

        Returns:
            The plaintext entry value.

        Raises:
            SecretResolutionError: If the secret does not exist, holds no such
                entry, its stored ciphertext cannot be decrypted, Vault is not
                configured, or the Vault read fails.
        """
        secret = await self._repo.get_by_name(name)
        if secret is None:
            raise SecretResolutionError(name, "no secret with this name exists")
        if secret.type is SecretType.local:
            return self._decrypt(secret, key)
        return await self._read_vault(secret, key)

    async def resolve_ref(self, ref: str) -> str:
        """Return the plaintext value named by a bare ``NAME/KEY`` reference.

        Used by fields that store a reference directly rather than embedding it
        in a placeholder, such as an AgentSkill's ``repo_auth_password``.

        Args:
            ref: The reference to resolve.

        Returns:
            The plaintext entry value.

        Raises:
            SecretResolutionError: If the reference omits the key, or the
                referenced entry fails to resolve.
        """
        name, key = split_secret_ref(ref)
        if key is None:
            raise SecretResolutionError(name, _MISSING_KEY_REASON)
        return await self.resolve_value(name, key)

    async def resolve_text(self, text: str) -> str:
        """Replace every ``${secret:NAME/KEY}`` placeholder in the text.

        Text without placeholders is returned unchanged (and costs no lookups).

        Args:
            text: The text possibly containing placeholders.

        Returns:
            The text with every placeholder replaced by its entry value.

        Raises:
            SecretResolutionError: If any placeholder omits its key, or any
                referenced entry fails to resolve.
        """
        result: list[str] = []
        cursor = 0
        for match in PLACEHOLDER_PATTERN.finditer(text):
            name, key = match.group(1), match.group(2)
            if key is None:
                raise SecretResolutionError(name, _MISSING_KEY_REASON)
            result.append(text[cursor : match.start()])
            result.append(await self.resolve_value(name, key))
            cursor = match.end()
        if not result:
            return text
        result.append(text[cursor:])
        return "".join(result)

    async def resolve_mapping(self, values: dict[str, str]) -> dict[str, str]:
        """Resolve placeholders in every value of a mapping.

        Used for MCP server headers (streamable HTTP) and environment variables
        (stdio), both of which carry secrets the same way.

        Args:
            values: Keys to values, the values possibly containing placeholders.

        Returns:
            A new mapping with all placeholders replaced; keys are untouched.

        Raises:
            SecretResolutionError: If any referenced entry fails to resolve.
        """
        return {key: await self.resolve_text(value) for key, value in values.items()}

    async def resolve_headers(self, headers: dict[str, str]) -> dict[str, str]:
        """Resolve placeholders in every value of a header mapping.

        Args:
            headers: Header names to values, possibly containing placeholders.

        Returns:
            A new mapping with all placeholders replaced; keys are untouched.

        Raises:
            SecretResolutionError: If any referenced entry fails to resolve.
        """
        return await self.resolve_mapping(headers)

    def _decrypt(self, secret: Secret, key: str) -> str:
        """Decrypt one entry of a local secret.

        Args:
            secret: A ``local``-type secret row.
            key: The entry key to decrypt.

        Returns:
            The plaintext value.

        Raises:
            SecretResolutionError: If the row holds no such entry or decryption
                fails (e.g. the encryption key changed).
        """
        ciphertext = secret.entries.get(key)
        if ciphertext is None:
            raise SecretResolutionError(
                secret.name, "the secret has no entry with this key"
            )
        try:
            return self._cipher.decrypt(ciphertext)
        except ValueError as exc:
            raise SecretResolutionError(secret.name, str(exc)) from exc

    async def _read_vault(self, secret: Secret, key: str) -> str:
        """Read one entry of a vault secret from HashiCorp Vault.

        Args:
            secret: A ``vault``-type secret row.
            key: The key to pick out of the secret's data object.

        Returns:
            The value fetched from Vault.

        Raises:
            SecretResolutionError: If Vault is not configured, the reference is
                incomplete, the read fails, or the path holds no such key.
        """
        if self._vault is None:
            raise SecretResolutionError(
                secret.name,
                "no Vault connection is configured (set VAULT_ADDR and credentials)",
            )
        if not (secret.vault_mount and secret.vault_path):
            raise SecretResolutionError(secret.name, "incomplete Vault reference")
        try:
            data = await self._vault.read_kv2(secret.vault_mount, secret.vault_path)
        except VaultError as exc:
            raise SecretResolutionError(secret.name, exc.reason) from exc
        if key not in data:
            raise SecretResolutionError(
                secret.name, "the Vault secret has no entry with this key"
            )
        return data[key]
