"""ASGI-level protections that run before any route code."""

from __future__ import annotations

import hmac
import logging
import re
import time
import uuid

from fastapi.responses import JSONResponse
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import Settings
from .metrics import Metrics
from .ratelimit import RateLimiter


class BodyTooLarge(Exception):
    """The request body exceeded the configured limit."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"request body too large (max {limit} bytes)")
        self.limit = limit


class BodyLimitMiddleware:
    """Cap request body size, including chunked uploads that send no Content-Length.

    The body is counted as the application reads it; once the cap is crossed the next read
    raises ``BodyTooLarge``, which the app turns into a 413. A declared Content-Length that is
    already over the cap is rejected on the first read without buffering anything.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = _content_length(scope)
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            if declared is not None and declared > self.max_bytes:
                raise BodyTooLarge(self.max_bytes)
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise BodyTooLarge(self.max_bytes)
            return message

        await self.app(scope, limited_receive, send)


def _content_length(scope: Scope) -> int | None:
    for name, value in scope["headers"]:
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


# ---- request context: ids, rate limiting, auth, metrics, headers, access log -----------

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")
_PUBLIC_PATHS = frozenset({"/", "/health", "/livez", "/readyz", "/docs", "/redoc", "/openapi.json"})
_PUBLIC_PREFIXES = ("/assets/",)  # landing page assets; never need an API key
_UNLIMITED_PATHS = frozenset({"/metrics"})  # scrapers poll this; auth already protects it
_SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}


def is_public(path: str) -> bool:
    """Paths that never need an API key."""
    return path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES)


def is_exempt(path: str) -> bool:
    """Probes, docs, the landing page and metrics are never rate limited."""
    return is_public(path) or path in _UNLIMITED_PATHS


def is_static(path: str) -> bool:
    """Landing page, its assets and the API docs may be cached; API responses may not."""
    return path == "/" or path.startswith(("/assets/", "/docs", "/redoc"))


def authorized(headers: Headers, api_key: str) -> bool:
    supplied = headers.get("x-api-key", "")
    auth = headers.get("authorization", "")
    if not supplied and auth.lower().startswith("bearer "):
        supplied = auth[7:].strip()
    return hmac.compare_digest(supplied.encode(), api_key.encode())


def client_id(scope: Scope, headers: Headers, trust_proxy: bool) -> str:
    """Identify the caller for rate limiting: peer address, or the last proxy-added hop."""
    if trust_proxy:
        hops = [h.strip() for h in headers.get("x-forwarded-for", "").split(",") if h.strip()]
        if hops:
            return hops[-1]
    peer = scope.get("client")
    return str(peer[0]) if peer else "unknown"


def _envelope(status: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"success": False, "data": None, "error": message}
    )


class RequestContextMiddleware:
    """Everything that wraps a request, as pure ASGI.

    Order of work: assign a request id, rate limit, authenticate, run the app, then stamp the
    response (request id, timing, security and rate-limit headers), record metrics and write the
    access log. Implemented as raw ASGI rather than ``BaseHTTPMiddleware`` because the latter
    roughly halves throughput (measured: 13.8k -> 6.8k req/s on a trivial endpoint).
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        metrics: Metrics,
        limiter: RateLimiter | None,
        logger: logging.Logger,
    ) -> None:
        self.app = app
        self.settings = settings
        self.metrics = metrics
        self.limiter = limiter
        self.logger = logger

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        headers = Headers(scope=scope)
        method: str = scope["method"]
        path: str = scope["path"]
        supplied = headers.get("x-request-id", "")
        request_id = supplied if _REQUEST_ID_RE.match(supplied) else uuid.uuid4().hex

        extra_headers: dict[str, str] = {}
        rejection: Response | None = None

        if self.limiter is not None and method != "OPTIONS" and not is_exempt(path):
            decision = self.limiter.check(client_id(scope, headers, self.settings.trust_proxy))
            extra_headers = {
                "x-ratelimit-limit": str(decision.limit),
                "x-ratelimit-remaining": str(decision.remaining),
                "x-ratelimit-reset": str(decision.reset),
            }
            if not decision.allowed:
                extra_headers["retry-after"] = str(decision.retry_after)
                rejection = _envelope(429, "rate limit exceeded")

        if (
            rejection is None
            and self.settings.api_key
            and not is_public(path)
            and not authorized(headers, self.settings.api_key)
        ):
            rejection = _envelope(401, "unauthorized")
            extra_headers["www-authenticate"] = "Bearer"

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start" and not response_started:
                response_started = True
                status: int = message["status"]
                elapsed = time.perf_counter() - started
                out = MutableHeaders(scope=message)
                for name, value in extra_headers.items():
                    out[name] = value
                out["x-request-id"] = request_id
                out["x-response-time-ms"] = f"{elapsed * 1000:.2f}"
                for name, value in _SECURITY_HEADERS.items():
                    out.setdefault(name, value)
                if not is_static(path):
                    out.setdefault("cache-control", "no-store")
                route = getattr(scope.get("route"), "path", "unmatched")
                self.metrics.observe_request(method, route, status, elapsed)
                self.logger.info(
                    "%s %s -> %d (%.2fms)",
                    method,
                    path,
                    status,
                    elapsed * 1000,
                    extra={
                        "request_id": request_id,
                        "method": method,
                        "path": path,
                        "status": status,
                        "duration_ms": round(elapsed * 1000, 2),
                    },
                )
            await send(message)

        if rejection is not None:
            await rejection(scope, receive, send_wrapper)
            return
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            self.logger.exception("unhandled error request_id=%s", request_id)
            if response_started:
                raise  # too late to send an error response; let the server drop the connection
            await _envelope(500, "internal server error")(scope, receive, send_wrapper)
