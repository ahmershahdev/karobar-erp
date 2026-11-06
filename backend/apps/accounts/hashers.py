"""Password hashing: Argon2id, falling back to bcrypt if a hash can't be computed."""

import logging

from argon2.exceptions import Argon2Error
from django.contrib.auth.hashers import Argon2PasswordHasher, BCryptSHA256PasswordHasher

logger = logging.getLogger(__name__)


class Argon2WithBcryptFallback(Argon2PasswordHasher):
    """Keeps sign-up and password changes working when Argon2id fails at runtime.

    Argon2id deliberately needs a lot of memory, so a starved server is the realistic failure.
    The string returned then starts with bcrypt_sha256$, which Django recognises on its own, and
    because this hasher stays first in PASSWORD_HASHERS the password is rehashed with Argon2id at
    the next successful sign-in. The algorithm name is inherited, so existing hashes keep working.
    """

    def encode(self, password: str, salt: str) -> str:
        try:
            return super().encode(password, salt)
        except (Argon2Error, MemoryError):
            logger.warning("Argon2id failed; hashing this password with bcrypt instead")
            fallback = BCryptSHA256PasswordHasher()
            return fallback.encode(password, fallback.salt())
