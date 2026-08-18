"""Redaction and validation helpers for Postgres DSNs.

REDACT_KEYS in core.logging covers dict fields, but a raw DSN string
(e.g. surfaced by a preflight script or a connection error) is not a dict
value keyed "database_url" - it is the value itself. This mirrors the
existing rule in core.logging: never emit str(exc) for anything that might
carry credentials, and never emit a DSN's userinfo component.

Everything here describes a DSN's *shape* - character classes, which
component is malformed - and never its content.
"""
from urllib.parse import urlsplit, urlunsplit

_REDACTED_USERINFO = "***:***"

# Characters that RFC 3986 reserves and that therefore must be
# percent-encoded inside a DSN's userinfo (username/password) component.
# An unencoded "@" or "/" silently reshapes the whole parse - the driver
# then reports a confusing "unknown host" or "invalid port" rather than
# "your password needs escaping", which is the failure this catches.
_MUST_ENCODE_IN_USERINFO = (
    "@", "/", "?", "#", "[", "]", " ", '"', "\\", "^", "|", "<", ">", "{", "}", "`",
)


def redact_dsn(url: str) -> str:
    """Return `url` with any embedded username:password replaced.

    Safe to call on a non-DSN string (e.g. empty, already redacted, or
    malformed) - returns it unchanged if there is no userinfo component to
    strip. On a string urlsplit cannot parse at all, returns a fixed
    placeholder rather than risking echoing the raw value.
    """
    if not url or "@" not in url:
        return url
    try:
        parts = urlsplit(url)
        netloc = parts.netloc
    except ValueError:
        return "<unparseable-dsn>"
    if not netloc or "@" not in netloc:
        return url
    _, _, hostport = netloc.rpartition("@")
    redacted_netloc = f"{_REDACTED_USERINFO}@{hostport}" if hostport else _REDACTED_USERINFO
    return urlunsplit(parts._replace(netloc=redacted_netloc))


def describe_dsn_problem(url: str) -> str | None:
    """Return a human-readable reason `url` is unusable, or None if it looks fine.

    Describes the *shape* of the problem only - which component, which
    character class - never the credential itself. Exists because an
    unencoded special character in a password produces a driver error that
    points at the wrong thing ("could not translate host name", "invalid
    integer value for port"), sending whoever is debugging it down the
    wrong path entirely.
    """
    if not url:
        return "the connection string is empty"

    try:
        parts = urlsplit(url)
    except ValueError:
        return "the connection string is not a parseable URI"

    # Checked before parts.scheme: urlsplit reads "user:pass@host/db" as
    # scheme="user", so a missing "://" looks like a present scheme and
    # would otherwise be reported as the wrong problem.
    if "://" not in url or not parts.scheme:
        return "the connection string has no scheme (expected postgresql+psycopg://...)"

    # Only network DSNs require a host. A file-backed SQLite URL
    # ("sqlite:///path/to.db") is legitimately hostless and is used as a
    # Postgres stand-in by the test suite, so it must pass this check.
    if parts.scheme.startswith("postgres") and not parts.netloc:
        return "the connection string has no host component"

    if "@" in parts.netloc:
        userinfo, _, _ = parts.netloc.rpartition("@")
        # More than one unencoded "@" means the split above already guessed
        # wrong about where userinfo ends - the password almost certainly
        # contains a literal "@".
        if "@" in userinfo:
            return (
                "the username or password contains an unencoded '@' - "
                "percent-encode it as %40"
            )
        offenders = sorted({ch for ch in _MUST_ENCODE_IN_USERINFO if ch in userinfo})
        if offenders:
            rendered = ", ".join(repr(ch) for ch in offenders)
            return (
                f"the username or password contains unencoded character(s): {rendered} - "
                "percent-encode them (see docs/SUPABASE_SETUP.md)"
            )

    # .port raises ValueError when an earlier unencoded character shifted
    # the parse and left something non-numeric after the final colon.
    try:
        _ = parts.port
    except ValueError:
        return (
            "the host/port component is malformed - this usually means an unencoded "
            "special character in the password shifted the URI parse"
        )

    return None
