from backend.config.settings import get_settings


def test_system_health_response_has_no_secrets(client):
    settings = get_settings()

    response = client.get("/api/system/health")
    body_text = response.text

    assert settings.db_password not in body_text
    assert settings.jwt_secret not in body_text
    assert settings.secret_key not in body_text
    for key in ("db_password", "jwt_secret", "secret_key", "database_url"):
        assert key not in response.json()
        for check in response.json().get("checks", {}).values():
            assert key not in check
