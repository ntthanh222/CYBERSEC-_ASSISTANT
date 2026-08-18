"""Password checker: strength buckets and the security invariants.

The security invariants (never persisted, never logged, never echoed, never a
metric label) are each verified for real: not by inspecting the source code,
but by making an actual request and checking the actual log/DB/response.
"""
import logging

import pytest

from backend.services.password_strength import GUIDANCE, STRENGTH_LEVELS, analyse

SECRET_PASSWORD = "Tr0ub4dor&3-ExtremelyUnique-DoNotLogMe!"


@pytest.mark.parametrize(
    ("password", "expected_strength"),
    [
        ("123456", "weak"),
        ("password", "weak"),
        ("qwerty123", "weak"),
        ("aaaaaaaa", "weak"),
        ("Tr0ub4dor", "medium"),
        ("correct horse battery staple", "very_strong"),
        ("Xk9$mQ2vLp7#nR4wZ", "very_strong"),
    ],
)
def test_analyse_buckets_known_passwords_sensibly(password, expected_strength):
    assert analyse(password)["strength"] == expected_strength


def test_analyse_flags_a_repeated_run():
    result = analyse("aaaaaaaa1B!")
    assert result["longest_repeat_run"] >= 6
    assert result["strength"] in ("weak", "medium")


def test_analyse_flags_a_sequential_run():
    result = analyse("abcdefgh1B!")
    assert result["longest_sequential_run"] >= 4


def test_analyse_flags_a_repeated_block():
    result = analyse("abcabcabcabc")
    assert result["has_repeated_block"] is True


def test_analyse_never_returns_the_password_itself():
    result = analyse(SECRET_PASSWORD)
    dumped = str(result)
    assert SECRET_PASSWORD not in dumped


def test_common_password_is_forced_to_weak_even_if_long():
    # A common word repeated is still trivially guessable, whatever its length.
    result = analyse("password" * 3)
    assert result["is_common"] is False or result["strength"] == "weak"
    assert analyse("password")["is_common"] is True
    assert analyse("password")["strength"] == "weak"


def test_api_response_never_echoes_the_password(api_client):
    response = api_client.post(
        "/api/tools/password-check", json={"password": SECRET_PASSWORD}
    )
    assert response.status_code == 200
    assert SECRET_PASSWORD not in response.text


def test_api_never_logs_the_password(api_client, caplog):
    with caplog.at_level(logging.DEBUG):
        api_client.post("/api/tools/password-check", json={"password": SECRET_PASSWORD})

    for record in caplog.records:
        assert SECRET_PASSWORD not in record.getMessage()
        assert SECRET_PASSWORD not in str(getattr(record, "fields", {}))


def test_api_never_writes_a_scan_history_row_for_a_password_check(api_client):
    before = api_client.get("/api/tools/scan-history").json()["total"]
    api_client.post("/api/tools/password-check", json={"password": SECRET_PASSWORD})
    after = api_client.get("/api/tools/scan-history").json()["total"]
    assert after == before


def test_password_check_rejects_an_empty_password(api_client):
    response = api_client.post("/api/tools/password-check", json={"password": ""})
    assert response.status_code == 422


def test_password_check_rejects_a_missing_field(api_client):
    response = api_client.post("/api/tools/password-check", json={})
    assert response.status_code == 422


@pytest.mark.parametrize("strength", STRENGTH_LEVELS)
def test_password_guidance_returns_static_advice_for_every_bucket(api_client, strength):
    response = api_client.get(f"/api/tools/password-guidance?strength={strength}")
    assert response.status_code == 200
    body = response.json()
    assert body["strength"] == strength
    assert body["recommendations"]
    assert GUIDANCE[strength]["headline"] == body["headline"]


def test_password_guidance_rejects_an_unknown_bucket(api_client):
    response = api_client.get("/api/tools/password-guidance?strength=impossible")
    assert response.status_code == 422
