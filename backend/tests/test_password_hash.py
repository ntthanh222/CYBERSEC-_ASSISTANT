"""Argon2id password hashing: real verify, no plaintext round-trip."""
from backend.core.password_hash import hash_password, needs_rehash, verify_password


def test_hash_is_never_the_plaintext():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert hashed.startswith("$argon2id$")


def test_verify_accepts_the_correct_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_rejects_a_wrong_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_verify_fails_closed_on_a_malformed_hash_instead_of_raising():
    assert verify_password("anything", "not-a-real-argon2-hash") is False


def test_two_hashes_of_the_same_password_differ_by_salt():
    a = hash_password("same input")
    b = hash_password("same input")
    assert a != b
    assert verify_password("same input", a) is True
    assert verify_password("same input", b) is True


def test_needs_rehash_is_false_for_a_freshly_hashed_password():
    assert needs_rehash(hash_password("correct horse battery staple")) is False
