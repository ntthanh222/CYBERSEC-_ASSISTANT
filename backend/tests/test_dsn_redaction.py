import pytest

from backend.core.dsn import describe_dsn_problem, redact_dsn


def test_redacts_username_and_password():
    url = "postgresql+psycopg://myuser:s3cr3t@pooler.supabase.com:5432/postgres"
    redacted = redact_dsn(url)
    assert "myuser" not in redacted
    assert "s3cr3t" not in redacted
    assert "pooler.supabase.com" in redacted
    assert "postgres" in redacted


def test_preserves_query_string():
    url = "postgresql+psycopg://u:p@host:5432/db?sslmode=require"
    redacted = redact_dsn(url)
    assert "sslmode=require" in redacted
    assert "u:p" not in redacted


def test_empty_string_is_unchanged():
    assert redact_dsn("") == ""


def test_url_without_userinfo_is_unchanged():
    url = "postgresql+psycopg://host:5432/db"
    assert redact_dsn(url) == url


def test_does_not_raise_on_garbage_input():
    assert redact_dsn("not a url at all") == "not a url at all"


class TestDescribeDsnProblem:
    def test_accepts_a_well_formed_dsn(self):
        url = "postgresql+psycopg://user:pass@db.example.com:5432/postgres?sslmode=require"
        assert describe_dsn_problem(url) is None

    def test_accepts_a_percent_encoded_password(self):
        # %22 is an encoded double-quote, %40 an encoded "@" - both fine.
        url = "postgresql+psycopg://user:p%40ss%2233@db.example.com:5432/postgres"
        assert describe_dsn_problem(url) is None

    def test_rejects_empty(self):
        assert "empty" in describe_dsn_problem("")

    def test_rejects_missing_scheme(self):
        assert "scheme" in describe_dsn_problem("user:pass@host:5432/db")

    def test_accepts_a_hostless_sqlite_url(self):
        # SQLite file URLs have no netloc by design and are used as a
        # Postgres stand-in by the test suite - requiring a host here would
        # break every preflight call in tests.
        assert describe_dsn_problem("sqlite:///C:/tmp/test.db") is None
        assert describe_dsn_problem("sqlite+aiosqlite:///./local.db") is None

    def test_still_requires_a_host_for_postgres_urls(self):
        assert "host" in describe_dsn_problem("postgresql+psycopg:///postgres")

    @pytest.mark.parametrize("char", ['"', " ", "|", "^", "<", ">", "{", "}", "`", "\\"])
    def test_flags_unencoded_special_characters(self, char):
        url = f"postgresql+psycopg://user:pa{char}ss@db.example.com:5432/postgres"
        problem = describe_dsn_problem(url)
        assert problem is not None
        assert "unencoded" in problem

    def test_flags_an_unencoded_at_sign_specifically(self):
        url = "postgresql+psycopg://user:pa@ss@db.example.com:5432/postgres"
        problem = describe_dsn_problem(url)
        assert problem is not None
        assert "%40" in problem

    def test_never_echoes_the_password_in_the_problem_message(self):
        secret = 'Sup3rSecret"Value'
        url = f"postgresql+psycopg://user:{secret}@db.example.com:5432/postgres"
        problem = describe_dsn_problem(url)
        assert problem is not None
        assert secret not in problem
        assert "Sup3rSecret" not in problem

    def test_flags_a_malformed_port(self):
        url = "postgresql+psycopg://user:pass@db.example.com:not-a-port/postgres"
        problem = describe_dsn_problem(url)
        assert problem is not None
        assert "malformed" in problem


def test_redact_dsn_returns_placeholder_for_an_unparseable_uri():
    # An IPv6-looking netloc with an unclosed bracket makes urlsplit raise.
    assert redact_dsn("postgresql://u:p@[::1:5432/db") == "<unparseable-dsn>"
