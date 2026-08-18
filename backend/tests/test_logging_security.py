import logging

from backend.core.logging import _redact


def test_redact_strips_sensitive_keys_case_insensitively():
    payload = {
        "method": "GET",
        "authorization": "Bearer super-secret-token",
        "headers": {"Cookie": "session=abc", "password": "hunter2", "X-Request-ID": "abc"},
    }
    redacted = _redact(payload)
    assert redacted["authorization"] == "***redacted***"
    assert redacted["headers"]["Cookie"] == "***redacted***"
    assert redacted["headers"]["password"] == "***redacted***"
    assert redacted["headers"]["X-Request-ID"] == "abc"
    assert redacted["method"] == "GET"


def test_authorization_header_never_appears_in_logs(client, caplog):
    caplog.set_level(logging.INFO)
    secret_token = "Bearer super-secret-token-xyz"

    client.get("/health", headers={"Authorization": secret_token})

    for record in caplog.records:
        assert secret_token not in record.getMessage()
        assert secret_token not in str(getattr(record, "fields", {}))
