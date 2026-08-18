import pytest

from backend.core.db_retry import is_transient_db_error, retry_transient


class _Transient(Exception):
    pass


def test_classifies_generic_connection_error_as_transient():
    assert is_transient_db_error(_Transient("could not connect to server: Connection timed out"))


def test_classifies_password_auth_failure_as_non_transient():
    assert not is_transient_db_error(Exception("password authentication failed for user \"x\""))


def test_classifies_missing_database_as_non_transient():
    assert not is_transient_db_error(Exception('database "nope" does not exist'))


def test_classifies_permission_denied_as_non_transient():
    assert not is_transient_db_error(Exception("permission denied for table conversations"))


def test_retry_transient_succeeds_after_transient_failures():
    calls = {"count": 0}

    def flaky():
        calls["count"] += 1
        if calls["count"] < 3:
            raise _Transient("could not connect to server")
        return "ok"

    sleeps = []
    result = retry_transient(flaky, attempts=5, base_delay_seconds=0.01, sleep=sleeps.append)
    assert result == "ok"
    assert calls["count"] == 3
    assert len(sleeps) == 2  # slept after attempt 1 and 2, not after the succeeding attempt 3


def test_retry_transient_gives_up_after_max_attempts():
    def always_fails():
        raise _Transient("could not connect to server")

    with pytest.raises(_Transient):
        retry_transient(always_fails, attempts=3, base_delay_seconds=0.01, sleep=lambda _: None)


def test_retry_transient_does_not_retry_auth_errors():
    calls = {"count": 0}

    def bad_password():
        calls["count"] += 1
        raise Exception("password authentication failed for user \"x\"")

    with pytest.raises(Exception, match="password authentication failed"):
        retry_transient(bad_password, attempts=5, base_delay_seconds=0.01, sleep=lambda _: None)
    assert calls["count"] == 1
