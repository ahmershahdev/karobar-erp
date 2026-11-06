import pytest
from argon2.exceptions import HashingError
from django.contrib.auth.hashers import (
    Argon2PasswordHasher,
    check_password,
    identify_hasher,
    make_password,
)
from pytest_django.fixtures import Settings as SettingsWrapper

PASSWORD = "lantern river cardamom"


@pytest.fixture(autouse=True)
def real_hashers(settings: SettingsWrapper) -> None:
    settings.PASSWORD_HASHERS = [
        "apps.accounts.hashers.Argon2WithBcryptFallback",
        "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
    ]


def test_new_passwords_use_argon2id() -> None:
    encoded = make_password(PASSWORD)
    assert encoded.startswith("argon2$argon2id$")
    assert check_password(PASSWORD, encoded)


def test_bcrypt_takes_over_when_argon2_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*args: object) -> str:
        raise HashingError("out of memory")

    monkeypatch.setattr(Argon2PasswordHasher, "encode", fail)
    encoded = make_password(PASSWORD)
    assert identify_hasher(encoded).algorithm == "bcrypt_sha256"
    assert check_password(PASSWORD, encoded)
    assert not check_password("wrong password here", encoded)


def test_a_bcrypt_password_moves_back_to_argon2_at_sign_in() -> None:
    encoded = make_password(PASSWORD, hasher="bcrypt_sha256")
    upgraded: list[str] = []
    assert check_password(
        PASSWORD, encoded, setter=lambda raw: upgraded.append(make_password(raw))
    )
    assert upgraded[0].startswith("argon2$argon2id$")
