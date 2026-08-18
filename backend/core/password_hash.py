"""Argon2id password hashing for the Local Mode admin login.

Never rolled by hand: this is a thin wrapper over ``argon2-cffi``'s own
constant-time verify, with the library's recommended default parameters.
Hashes are self-describing (the algorithm/params are encoded in the hash
string itself), so a future parameter bump does not invalidate stored hashes
and does not need a migration - :meth:`needs_rehash` flags them for lazy
upgrade on next successful login instead.
"""
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

#: At most this many characters are hashed - long enough for any real
#: passphrase, short enough that a client cannot force multi-megabyte input
#: into the hash function as a cheap CPU-exhaustion vector.
MAX_PASSWORD_LENGTH = 256
MIN_PASSWORD_LENGTH = 8

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verify. Any malformed/foreign hash format is a mismatch,
    never a crash - a corrupted stored hash must fail closed."""
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:  # noqa: BLE001 - any hash-format error is "does not match"
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
