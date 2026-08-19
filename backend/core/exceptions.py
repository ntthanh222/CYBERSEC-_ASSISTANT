"""Application error hierarchy.

Every business failure in Phase 2 raises an ``AppError`` subclass instead of
letting a driver/provider exception escape. The handler registered in
``backend.main`` turns it into the exact same JSON envelope Phase 1.5 already
uses for HTTP and validation errors::

    {"error": "<slug>", "message": "<safe text>", "request_id": "<id>"}

Two rules hold for every subclass:

1. ``message`` is written for an end user and must never contain a stack
   trace, a connection string, an API key, a password or an upstream body.
2. ``error`` is a stable machine-readable slug the frontend can branch on;
   changing one is an API-contract change.
"""
from typing import Optional


class AppError(Exception):
    """Base class for all expected, mapped application failures."""

    error: str = "application_error"
    message: str = "The request could not be completed."
    status_code: int = 500

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        error: Optional[str] = None,
        status_code: Optional[int] = None,
    ) -> None:
        if message is not None:
            self.message = message
        if error is not None:
            self.error = error
        if status_code is not None:
            self.status_code = status_code
        # Exception args carry the safe message only, so even an accidental
        # str(exc) in a log line cannot leak internals.
        super().__init__(self.message)


class InvalidRequestError(AppError):
    error = "invalid_request"
    message = "The request was not valid."
    status_code = 400


class NotFoundError(AppError):
    error = "not_found"
    message = "The requested resource does not exist."
    status_code = 404


class RateLimitedError(AppError):
    error = "rate_limited"
    message = "Too many requests. Please slow down and try again shortly."
    status_code = 429


class ConfigurationMissingError(AppError):
    """A required integration is not configured (e.g. no API key present).

    Deliberately distinct from ``ProviderUnavailableError``: the frontend must
    be able to tell "the operator never configured this" apart from "the
    upstream is down right now", and must never be told an integration ran
    when it was not configured at all.
    """

    error = "configuration_missing"
    message = "This feature is not configured on the server."
    status_code = 503


class ProviderUnavailableError(AppError):
    error = "provider_unavailable"
    message = "The upstream provider is currently unavailable."
    status_code = 502


class ProviderAuthenticationError(AppError):
    """The upstream rejected the operator's own configured credentials.

    Deliberately distinct from ``NotFoundError``: an upstream that responds
    "your API key is invalid" must never be silently reported to the caller
    as "this record does not exist" - that hides a fixable operator-side
    configuration problem behind a misleading result. Also distinct from
    ``ConfigurationMissingError`` (no key present at all) - here a key *is*
    configured, the upstream is just refusing to honor it.
    """

    error = "provider_authentication_failed"
    message = "The upstream provider rejected the configured credentials."
    status_code = 502


class ProviderTimeoutError(AppError):
    error = "provider_timeout"
    message = "The upstream provider did not respond in time."
    status_code = 504


class ProviderRateLimitedError(AppError):
    error = "provider_rate_limited"
    message = "The upstream provider rate-limited this request. Try again later."
    status_code = 429


class UpstreamMalformedError(AppError):
    error = "upstream_malformed"
    message = "The upstream provider returned a response that could not be understood."
    status_code = 502


class AuthenticationError(AppError):
    """Missing, malformed, or otherwise unverifiable bearer token.

    Deliberately a single generic message and status for every failure mode
    (missing header, bad signature, expired, wrong issuer/audience, unknown
    kid) - the response must never tell a caller *which* part of the token
    was wrong, only that it was rejected.
    """

    error = "unauthorized"
    message = "Authentication required."
    status_code = 401


class AuthorizationError(AppError):
    """The caller is authenticated but lacks permission for this action.

    Deliberately distinct from :class:`AuthenticationError` (401): this is a
    verified identity that is not allowed to do the thing, not an
    unverifiable one.
    """

    error = "forbidden"
    message = "You do not have permission to perform this action."
    status_code = 403


class ConflictError(AppError):
    """The action cannot proceed because of existing state (e.g. already set up)."""

    error = "conflict"
    message = "This action conflicts with the current state."
    status_code = 409


class PayloadTooLargeError(AppError):
    """An uploaded file exceeds a configured size/page/chunk limit."""

    error = "payload_too_large"
    message = "The uploaded file exceeds the allowed size."
    status_code = 413


class UnsupportedMediaTypeError(AppError):
    """An upload's actual byte content is not a supported type, or contradicts
    its declared ``Content-Type``/filename extension.

    Deliberately distinct from :class:`InvalidRequestError`: a client can only
    fix this by supplying different file content, not by fixing a malformed
    request. The message never echoes the declared/detected MIME type,
    filename, or any file content back to the caller.
    """

    error = "unsupported_media_type"
    message = "The uploaded file's content is not a supported type."
    status_code = 415


class InvalidTransitionError(AppError):
    """A Finding status transition is not reachable from its current status
    at all (not in ``finding_state_machine.ALLOWED_TRANSITIONS``), regardless
    of who is asking. Distinct from :class:`ForbiddenTransitionError` (a
    reachable transition the *actor* specifically may not perform)."""

    error = "invalid_transition"
    message = "That status transition is not allowed."
    status_code = 422


class ForbiddenTransitionError(AppError):
    """The transition is a valid state-machine edge, but this actor's role
    does not permit performing it (e.g. a developer trying to verify/close a
    finding)."""

    error = "forbidden_transition"
    message = "You do not have permission to perform this status transition."
    status_code = 403


class ReasonRequiredError(AppError):
    """A ``false_positive``/``accepted_risk`` transition was attempted
    without a non-empty ``reason``."""

    error = "reason_required"
    message = "A reason is required for this transition."
    status_code = 422


class BlockedTargetError(AppError):
    """A scan target was rejected by the SSRF guard.

    The message intentionally states *that* the target was refused without
    echoing resolved IP addresses back to the caller, which would turn the
    scanner into an internal-network discovery oracle.
    """

    error = "blocked_target"
    message = "That target is not allowed to be scanned."
    status_code = 400
