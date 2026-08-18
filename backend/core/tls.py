"""Canonical TLS/sslmode enforcement for staging and production Postgres targets.

One rule, one implementation, three call sites (Settings' own validator,
Alembic's env.py, db_preflight.py) - all three call this module rather than
each re-deriving "is TLS actually on" independently, which is how a gap
like "sslmode=disable silently accepted" gets missed in one of the three
and not the others.

Never logs or raises with a DSN's credentials embedded: every message here
identifies the *target* by a caller-supplied label (e.g. "DATABASE_URL"),
never the URL itself.
"""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

#: sslmode values that mean the connection is actually encrypted (and, for
#: verify-ca/verify-full, certificate-verified). "require" encrypts but does
#: not verify the server certificate; still accepted because Supabase's own
#: connection strings use it by default and it is materially safer than the
#: alternative below.
SECURE_SSLMODES = frozenset({"require", "verify-ca", "verify-full"})

#: sslmode values that are libpq-valid but do not guarantee an encrypted
#: connection ("allow"/"prefer" fall back to plaintext if TLS negotiation
#: fails; "disable" never even attempts it). Listed explicitly (rather than
#: inferred as "anything not in SECURE_SSLMODES") only so error messages can
#: name the specific known-weak mode; an unrecognised value is rejected by
#: the same "not in SECURE_SSLMODES" check regardless.
INSECURE_SSLMODES = frozenset({"disable", "allow", "prefer"})

_TLS_REQUIRED_ENVS = frozenset({"staging", "production"})


class InsecureTlsConfigurationError(ValueError):
    """Raised when a staging/production target would not use verified TLS."""


def apply_ssl_mode(url: str, database_ssl_mode: str) -> str:
    """Inject ``sslmode`` into ``url``'s query string if not already present.

    The single canonical place this happens - Settings' database_url/
    database_migration_url properties and db_preflight.py's TLS check both
    call this, so "what got validated" and "what actually gets handed to
    the driver" can never drift apart. ``setdefault`` semantics are
    deliberate: a DSN that already declares its own ``sslmode`` keeps it
    (see the conflict case documented on ``effective_sslmode`` above).

    A no-op for anything that is not a Postgres DSN (e.g. the ``sqlite://``
    URLs the test suite uses as a Postgres stand-in) - ``sslmode`` is a
    libpq concept and injecting it into an unrelated driver's URL would
    corrupt it rather than configure anything.
    """
    if not database_ssl_mode or not url or not url.startswith("postgresql"):
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.setdefault("sslmode", database_ssl_mode)
    return urlunsplit(parts._replace(query=urlencode(query)))


def dsn_sslmode(url: str) -> str | None:
    """Return the ``sslmode`` declared on ``url``'s own query string, or None."""
    if not url:
        return None
    query = dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))
    return query.get("sslmode") or None


def effective_sslmode(url: str, database_ssl_mode: str) -> str | None:
    """The sslmode that will actually reach the driver for ``url``.

    The DSN's own ``sslmode`` query parameter always wins over
    ``DATABASE_SSL_MODE`` (matching ``apply_ssl_mode``'s ``setdefault``
    behaviour) - so a DSN that already declares ``sslmode=disable`` stays
    disabled even if ``DATABASE_SSL_MODE=require`` is set. That conflict is
    exactly what ``require_secure_tls`` below must catch, not silently
    resolve in the safer direction.
    """
    return dsn_sslmode(url) or (database_ssl_mode or None)


def require_secure_tls(*, url: str, database_ssl_mode: str, app_env: str, label: str) -> None:
    """Raise :class:`InsecureTlsConfigurationError` if ``url`` is unsafe for ``app_env``.

    A no-op outside staging/production - local Docker Postgres has no TLS
    configured by design and must keep working unmodified.

    ``label`` identifies which target failed (e.g. ``"DATABASE_URL"``,
    ``"DATABASE_MIGRATION_URL"``) in the raised message; the DSN itself is
    never included.
    """
    if app_env.lower() not in _TLS_REQUIRED_ENVS:
        return

    if database_ssl_mode and database_ssl_mode not in SECURE_SSLMODES:
        raise InsecureTlsConfigurationError(
            f"DATABASE_SSL_MODE={database_ssl_mode!r} is not a secure sslmode for "
            f"APP_ENV=staging|production - use one of {sorted(SECURE_SSLMODES)}."
        )

    mode = effective_sslmode(url, database_ssl_mode)
    if mode not in SECURE_SSLMODES:
        reason = f"declares sslmode={mode!r}" if mode else "has no sslmode set"
        raise InsecureTlsConfigurationError(
            f"{label} {reason}, which is not secure for APP_ENV=staging|production - "
            f"use one of {sorted(SECURE_SSLMODES)} (e.g. set DATABASE_SSL_MODE=require)."
        )
