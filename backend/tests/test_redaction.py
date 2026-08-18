"""Free-form text redaction used before persisting assistant messages."""
import pytest

from backend.services.redaction import contains_secret, redact_text


@pytest.mark.parametrize(
    "text",
    [
        "Bearer " + ".".join([
            "jwt_header_fixture",
            "jwt_payload_fixture",
            "jwt_signature_fixture",
        ]),
        "api_key: " + "sk-" + "abcdef1234567890" + "abcdef1234567890",
        "AKIA" + "IOSFODNN7EXAMPLE",
        "postgresql://user:" + "hunter2" + "@db.internal:5432/app",
        "password=" + "SuperSecret123!",
        "-----BEGIN " + "PRIVATE KEY-----\nMIIBVQIBADANBgkq\n-----END PRIVATE KEY-----",
    ],
)
def test_redact_text_removes_secret_shaped_substrings(text):
    redacted = redact_text(text)
    assert redacted != text
    assert "[REDACTED]" in redacted


def test_redact_text_leaves_ordinary_text_untouched():
    text = "What is CVE-2021-44228 and how severe is it?"
    assert redact_text(text) == text


def test_redact_text_handles_empty_input():
    assert redact_text("") == ""


def test_contains_secret_detects_a_token():
    assert contains_secret("Authorization: Bearer abcdefghij1234567890") is True


def test_contains_secret_is_false_for_clean_text():
    assert contains_secret("hello, is this URL safe?") is False
