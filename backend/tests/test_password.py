import pytest

from infrastructure.password import hash_password, verify_password


def test_hash_password_round_trips_at_configured_rounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BCRYPT_ROUNDS", "12")
    plain = "correct horse battery staple"

    hashed = hash_password(plain)

    assert hashed.split("$")[2] == "12"
    assert verify_password(plain, hashed)
    assert not verify_password("wrong password", hashed)


def test_hash_password_uses_fast_rounds_by_default_in_tests() -> None:
    plain = "correct horse battery staple"

    hashed = hash_password(plain)

    assert hashed.split("$")[2] == "04"
    assert verify_password(plain, hashed)
