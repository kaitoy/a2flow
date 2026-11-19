"""Unit tests for the Fernet key-loading precedence and the SecretCipher."""

from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from infrastructure.secret_cipher import (
    SecretCipher,
    data_key_cipher,
    get_secret_cipher,
    load_fallback_keys,
    load_or_create_key,
    new_data_key,
)


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


def test_data_key_is_wrapped_by_the_master_key() -> None:
    wrapped = new_data_key()
    unwrapped = get_secret_cipher().decrypt(wrapped).encode("ascii")

    cipher = data_key_cipher(wrapped)
    assert cipher.decrypt(SecretCipher(unwrapped).encrypt("s3cr3t")) == "s3cr3t"


def test_one_tenants_ciphertext_does_not_decrypt_under_another_data_key() -> None:
    mine, theirs = data_key_cipher(new_data_key()), data_key_cipher(new_data_key())
    token = mine.encrypt("s3cr3t")

    assert mine.decrypt(token) == "s3cr3t"
    with pytest.raises(ValueError, match="decrypt"):
        theirs.decrypt(token)
    with pytest.raises(ValueError, match="decrypt"):
        get_secret_cipher().decrypt(token)


def test_a_data_key_not_wrapped_by_the_master_is_refused() -> None:
    foreign = SecretCipher(Fernet.generate_key()).encrypt(
        Fernet.generate_key().decode()
    )

    with pytest.raises(ValueError, match="decrypt"):
        data_key_cipher(foreign)


def test_fallback_keys_are_read_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    first, second = Fernet.generate_key(), Fernet.generate_key()
    monkeypatch.setenv(
        "SECRET_ENCRYPTION_KEY_FALLBACKS", f" {first.decode()} ,,{second.decode()}"
    )

    assert load_fallback_keys() == [first, second]


def test_no_fallback_keys_by_default() -> None:
    assert load_fallback_keys() == []


def test_invalid_fallback_key_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "SECRET_ENCRYPTION_KEY_FALLBACKS", f"{Fernet.generate_key().decode()},nope"
    )

    with pytest.raises(ValueError, match="entry 2 of SECRET_ENCRYPTION_KEY_FALLBACKS"):
        load_fallback_keys()


def test_a_fallback_decrypts_but_never_encrypts() -> None:
    old_key, new_key = Fernet.generate_key(), Fernet.generate_key()
    old_token = SecretCipher(old_key).encrypt("s3cr3t")
    cipher = SecretCipher(new_key, [old_key])

    assert cipher.has_fallbacks
    assert cipher.decrypt(old_token) == "s3cr3t"
    assert SecretCipher(new_key).decrypt(cipher.encrypt("s3cr3t")) == "s3cr3t"


def test_rotate_moves_only_old_ciphertexts_to_the_primary_key() -> None:
    old_key, new_key = Fernet.generate_key(), Fernet.generate_key()
    cipher = SecretCipher(new_key, [old_key])

    rotated = cipher.rotate(SecretCipher(old_key).encrypt("s3cr3t"))
    assert rotated is not None
    assert SecretCipher(new_key).decrypt(rotated) == "s3cr3t"
    assert cipher.rotate(cipher.encrypt("s3cr3t")) is None
    with pytest.raises(ValueError, match="decrypt"):
        cipher.rotate(SecretCipher(Fernet.generate_key()).encrypt("s3cr3t"))
