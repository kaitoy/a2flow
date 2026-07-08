"""Unit tests for the Fernet key-loading precedence and the SecretCipher."""

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from infrastructure.secret_cipher import SecretCipher, load_or_create_key


def test_env_key_takes_priority_over_key_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_key = Fernet.generate_key()
    key_file = tmp_path / "key"
    key_file.write_bytes(Fernet.generate_key())
    monkeypatch.setenv("SECRET_ENCRYPTION_KEY", env_key.decode())
    monkeypatch.setenv("SECRET_KEY_FILE", str(key_file))

    assert load_or_create_key() == env_key


def test_invalid_env_key_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_ENCRYPTION_KEY", "not-a-fernet-key")

    with pytest.raises(ValueError, match="SECRET_ENCRYPTION_KEY"):
        load_or_create_key()


def test_key_file_used_when_env_unset(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key = Fernet.generate_key()
    key_file = tmp_path / "key"
    key_file.write_bytes(key)
    monkeypatch.setenv("SECRET_KEY_FILE", str(key_file))

    assert load_or_create_key() == key


def test_invalid_key_file_fails_fast(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key_file = tmp_path / "key"
    key_file.write_bytes(b"garbage")
    monkeypatch.setenv("SECRET_KEY_FILE", str(key_file))

    with pytest.raises(ValueError, match="key file"):
        load_or_create_key()


def test_key_generated_and_persisted_when_nothing_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key_file = tmp_path / "generated" / "key"
    monkeypatch.setenv("SECRET_KEY_FILE", str(key_file))

    first = load_or_create_key()

    assert key_file.read_bytes() == first
    # A second load reuses the persisted file instead of generating anew.
    assert load_or_create_key() == first


def test_cipher_roundtrip() -> None:
    cipher = SecretCipher(Fernet.generate_key())
    assert cipher.decrypt(cipher.encrypt("s3cr3t")) == "s3cr3t"


def test_ciphertext_differs_from_plaintext() -> None:
    cipher = SecretCipher(Fernet.generate_key())
    assert cipher.encrypt("s3cr3t") != "s3cr3t"


def test_decrypt_with_wrong_key_raises_value_error() -> None:
    token = SecretCipher(Fernet.generate_key()).encrypt("s3cr3t")
    other = SecretCipher(Fernet.generate_key())

    with pytest.raises(ValueError, match="decrypt"):
        other.decrypt(token)


def test_decrypt_garbage_raises_value_error() -> None:
    cipher = SecretCipher(Fernet.generate_key())

    with pytest.raises(ValueError, match="decrypt"):
        cipher.decrypt("not-a-token")
