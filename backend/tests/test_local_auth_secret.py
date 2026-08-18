"""Persistent, runtime-generated Local Auth secret behavior."""
from backend.config.settings import Settings
from backend.core.local_auth_secret import load_or_create_local_auth_secret


def test_generates_a_secret_when_file_absent(tmp_path):
    path = tmp_path / "secret-dir" / "jwt-secret"

    secret = load_or_create_local_auth_secret(str(path))

    assert secret
    assert len(secret) >= 32  # secrets.token_urlsafe(48) is well above this
    assert path.exists()


def test_reuses_the_same_secret_across_calls(tmp_path):
    path = tmp_path / "jwt-secret"

    first = load_or_create_local_auth_secret(str(path))
    second = load_or_create_local_auth_secret(str(path))

    assert first == second


def test_two_startups_do_not_change_the_secret(tmp_path):
    """Simulates two separate process starts reading the same volume."""
    path = tmp_path / "jwt-secret"

    startup_1 = load_or_create_local_auth_secret(str(path))
    startup_2 = load_or_create_local_auth_secret(str(path))
    startup_3 = load_or_create_local_auth_secret(str(path))

    assert startup_1 == startup_2 == startup_3


def test_different_paths_get_different_secrets(tmp_path):
    secret_a = load_or_create_local_auth_secret(str(tmp_path / "a"))
    secret_b = load_or_create_local_auth_secret(str(tmp_path / "b"))

    assert secret_a != secret_b


def test_falls_back_to_a_random_in_memory_secret_when_path_unwritable(monkeypatch, tmp_path):
    # Point at a path whose parent is a file, not a directory - mkdir must
    # fail with a real OSError (NotADirectoryError), not silently succeed.
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    unwritable_path = blocker / "jwt-secret"

    secret = load_or_create_local_auth_secret(str(unwritable_path))

    assert secret  # still genuinely random, never a fixed fallback constant
    assert len(secret) >= 32


def test_settings_generates_local_secret_when_app_env_local(tmp_path):
    path = tmp_path / "jwt-secret"

    settings = Settings(_env_file=None, app_env="local", LOCAL_AUTH_SECRET_PATH=str(path))

    assert settings.supabase_jwt_secret
    assert path.exists()
    assert path.read_text(encoding="utf-8").strip() == settings.supabase_jwt_secret


def test_settings_reuses_persisted_secret_on_next_construction(tmp_path):
    path = tmp_path / "jwt-secret"

    first = Settings(_env_file=None, app_env="local", LOCAL_AUTH_SECRET_PATH=str(path))
    second = Settings(_env_file=None, app_env="local", LOCAL_AUTH_SECRET_PATH=str(path))

    assert first.supabase_jwt_secret == second.supabase_jwt_secret


def test_real_supabase_secret_always_wins_over_generated_one(tmp_path):
    path = tmp_path / "jwt-secret"

    settings = Settings(
        _env_file=None,
        app_env="local",
        LOCAL_AUTH_SECRET_PATH=str(path),
        SUPABASE_JWT_SECRET="a-real-configured-secret",
    )

    assert settings.supabase_jwt_secret == "a-real-configured-secret"
    assert not path.exists()  # never touched when a real secret is already set
