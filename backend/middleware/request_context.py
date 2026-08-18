"""Assigns/validates X-Request-ID and emits one structured access log line."""
import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from backend.core.context import reset_request_id, set_request_id
from backend.core.correlation import reset_correlation_id, set_correlation_id
from backend.core.metrics import observe_error, observe_request

logger = logging.getLogger("backend.access")

# Conservative allowlist: avoids header/log injection via crafted client ids.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def resolve_request_id(raw: str | None) -> str:
    if raw and _VALID_REQUEST_ID.match(raw):
        return raw
    return str(uuid.uuid4())


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path or request.url.path


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = resolve_request_id(request.headers.get("x-request-id"))
        correlation_id = resolve_request_id(request.headers.get("x-correlation-id"))
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        id_token = set_request_id(request_id)
        corr_token = set_correlation_id(correlation_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            route = _route_template(request)
            observe_error(request.method, route, "unhandled_exception")
            observe_request(request.method, route, 500, duration_ms / 1000)
            logger.exception(
                "request_failed",
                extra={
                    "request_id": request_id,
                    "fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "correlation_id": correlation_id,
                        "duration_ms": duration_ms,
                    },
                },
            )
            raise
        else:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            route = _route_template(request)
            observe_request(request.method, route, response.status_code, duration_ms / 1000)
            if response.status_code >= 500:
                observe_error(request.method, route, "server_error")
            logger.info(
                "request_completed",
                extra={
                    "request_id": request_id,
                    "fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "correlation_id": correlation_id,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                    },
                },
            )
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            reset_request_id(id_token)
            reset_correlation_id(corr_token)
