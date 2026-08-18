"""Prometheus metrics registry.

Route templates (not raw URLs) are used as labels everywhere to keep
cardinality bounded — never label with a request path containing an ID.
"""
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest

registry = CollectorRegistry()

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "route", "status_code"],
    registry=registry,
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "route"],
    registry=registry,
)

HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "HTTP requests currently being processed",
    ["method", "route"],
    registry=registry,
)

HTTP_ERRORS_TOTAL = Counter(
    "http_errors_total",
    "Total HTTP requests that resulted in an error",
    ["method", "route", "error_type"],
    registry=registry,
)

APP_INFO = Gauge(
    "app_info",
    "Static application build/version info (value is always 1)",
    ["version", "environment"],
    registry=registry,
)

DEPENDENCY_PROBE_STATUS = Gauge(
    "dependency_probe_status",
    "Dependency health probe status (1=healthy, 0=not healthy)",
    ["dependency"],
    registry=registry,
)

DEPENDENCY_PROBE_LATENCY_MS = Gauge(
    "dependency_probe_latency_ms",
    "Dependency health probe latency in milliseconds",
    ["dependency"],
    registry=registry,
)


RATE_LIMIT_REJECTIONS_TOTAL = Counter(
    "rate_limit_rejections_total",
    "Requests rejected by the rate limiter",
    ["bucket"],
    registry=registry,
)

# --- Phase 2: assistant -----------------------------------------------------
# `intent` and `provider` are closed enumerations defined in code; neither is
# derived from user input, so cardinality stays bounded.

ASSISTANT_REQUESTS_TOTAL = Counter(
    "assistant_requests_total",
    "Assistant chat requests by provider, classified intent and outcome",
    ["provider", "intent", "result"],
    registry=registry,
)

ASSISTANT_PROVIDER_LATENCY_SECONDS = Histogram(
    "assistant_provider_latency_seconds",
    "Latency of the assistant's LLM provider call",
    ["provider"],
    registry=registry,
)

ASSISTANT_PROVIDER_FAILURES_TOTAL = Counter(
    "assistant_provider_failures_total",
    "Assistant provider failures by reason",
    ["provider", "reason"],
    registry=registry,
)

# --- Phase 2: security toolkit ---------------------------------------------
# Never labelled with the scanned URL, the CVE id, the actor or an IP address.

URL_SCANS_TOTAL = Counter(
    "url_scans_total",
    "URL scans by outcome",
    ["result"],
    registry=registry,
)

URL_SCAN_DURATION_SECONDS = Histogram(
    "url_scan_duration_seconds",
    "End-to-end URL scan duration in seconds",
    registry=registry,
)

PASSWORD_CHECKS_TOTAL = Counter(
    "password_checks_total",
    "Password strength checks by resulting strength bucket",
    ["strength"],
    registry=registry,
)

CVE_LOOKUPS_TOTAL = Counter(
    "cve_lookups_total",
    "CVE lookups by outcome",
    ["result"],
    registry=registry,
)

CVE_CACHE_TOTAL = Counter(
    "cve_cache_total",
    "CVE cache outcomes (hit/miss/error)",
    ["outcome"],
    registry=registry,
)


def observe_request(method: str, route: str, status_code: int, duration_seconds: float) -> None:
    HTTP_REQUESTS_TOTAL.labels(method=method, route=route, status_code=str(status_code)).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, route=route).observe(duration_seconds)


def observe_error(method: str, route: str, error_type: str) -> None:
    HTTP_ERRORS_TOTAL.labels(method=method, route=route, error_type=error_type).inc()


def observe_dependency_probe(dependency: str, status: str, latency_ms: float | None) -> None:
    DEPENDENCY_PROBE_STATUS.labels(dependency=dependency).set(1 if status == "healthy" else 0)
    if latency_ms is not None:
        DEPENDENCY_PROBE_LATENCY_MS.labels(dependency=dependency).set(latency_ms)


def set_app_info(version: str, environment: str) -> None:
    APP_INFO.labels(version=version, environment=environment).set(1)


def observe_rate_limit(bucket: str) -> None:
    RATE_LIMIT_REJECTIONS_TOTAL.labels(bucket=bucket).inc()


def observe_assistant_request(provider: str, intent: str, result: str) -> None:
    ASSISTANT_REQUESTS_TOTAL.labels(provider=provider, intent=intent, result=result).inc()


def observe_assistant_latency(provider: str, duration_seconds: float) -> None:
    ASSISTANT_PROVIDER_LATENCY_SECONDS.labels(provider=provider).observe(duration_seconds)


def observe_assistant_failure(provider: str, reason: str) -> None:
    ASSISTANT_PROVIDER_FAILURES_TOTAL.labels(provider=provider, reason=reason).inc()


def observe_url_scan(result: str, duration_seconds: float | None = None) -> None:
    URL_SCANS_TOTAL.labels(result=result).inc()
    if duration_seconds is not None:
        URL_SCAN_DURATION_SECONDS.observe(duration_seconds)


def observe_password_check(strength: str) -> None:
    PASSWORD_CHECKS_TOTAL.labels(strength=strength).inc()


def observe_cve_lookup(result: str) -> None:
    CVE_LOOKUPS_TOTAL.labels(result=result).inc()


def observe_cve_cache(outcome: str) -> None:
    CVE_CACHE_TOTAL.labels(outcome=outcome).inc()


def render_latest() -> bytes:
    return generate_latest(registry)
