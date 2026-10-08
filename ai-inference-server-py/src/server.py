from __future__ import annotations

import hmac
import json
import logging
import re
import sqlite3
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from . import __version__
from . import openapi as docs
from .config import Settings
from .engines import ConfigError, validate_config
from .inference import VALID_TYPES, InferenceStore, Store, StoreFull
from .logging_config import configure_logging
from .metrics import Metrics
from .middleware import BodyLimitMiddleware, BodyTooLarge
from .ratelimit import RateLimiter
from .schemas import (
    BatchRequest,
    DeletedResponse,
    HealthResponse,
    InferenceListResponse,
    InferenceResponse,
    InferRequest,
    ModelCreate,
    ModelListResponse,
    ModelResponse,
    ProbeResponse,
)
from .sqlite_store import SqliteStore

logger = logging.getLogger("ai_inference_server")

STATIC_DIR = Path(__file__).parent / "static"

TYPE_ERROR = "type must be one of: text-generation, text-classification, embedding"
_HTTP_MESSAGES = {404: "not found", 405: "method not allowed", 401: "unauthorized"}
_PUBLIC_PATHS = frozenset(
    {"/", "/health", "/livez", "/readyz", "/docs", "/redoc", "/openapi.json"}
)
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._\-]{1,128}$")
_SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
}
_UNLIMITED_PATHS = frozenset({"/metrics"})  # scrapers poll this; auth already protects it
_CORS_HEADERS = ["authorization", "content-type", "x-api-key", "x-request-id"]
_PUBLIC_PREFIXES = ("/assets/",)  # landing page assets; never need an API key


def _is_public(path: str) -> bool:
    return path in _PUBLIC_PATHS or path.startswith(_PUBLIC_PREFIXES)
MAX_PAGE_SIZE = 1_000
_TOKEN_RE = re.compile(r"\S+\s*")


def _ok(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def _fail(error: str) -> dict[str, Any]:
    return {"success": False, "data": None, "error": error}


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=_fail(message))


async def _json_object(request: Request) -> dict[str, Any]:
    """Parse the request body as a JSON object; anything else yields ``{}``."""
    try:
        body = await request.json()
    except BodyTooLarge:
        raise
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


def _client_id(request: Request, trust_proxy: bool) -> str:
    """Identify the caller for rate limiting: peer address, or the last proxy-added hop."""
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"


def _is_exempt(path: str) -> bool:
    """Probes, docs, the landing page and metrics are never rate limited."""
    return _is_public(path) or path in _UNLIMITED_PATHS


def _is_static(path: str) -> bool:
    """Landing page, its assets and the API docs may be cached; API responses may not."""
    return path == "/" or path.startswith(("/assets/", "/docs", "/redoc"))


def _page_params(request: Request) -> tuple[int | None, int] | str:
    """Parse ``limit``/``offset`` query params; returns an error message on bad input."""
    params = request.query_params
    limit: int | None = None
    offset = 0
    try:
        if "limit" in params:
            limit = int(params["limit"])
            if not 1 <= limit <= MAX_PAGE_SIZE:
                raise ValueError
    except ValueError:
        return f"limit must be an integer between 1 and {MAX_PAGE_SIZE}"
    try:
        if "offset" in params:
            offset = int(params["offset"])
            if offset < 0:
                raise ValueError
    except ValueError:
        return "offset must be a non-negative integer"
    return limit, offset


def _list_response(items: list[Any], total: int) -> JSONResponse:
    return JSONResponse(content=_ok(items), headers={"x-total-count": str(total)})


def _authorized(request: Request, api_key: str) -> bool:
    supplied = request.headers.get("x-api-key", "")
    auth = request.headers.get("authorization", "")
    if not supplied and auth.lower().startswith("bearer "):
        supplied = auth[7:].strip()
    return hmac.compare_digest(supplied.encode(), api_key.encode())


def _sse(data: Any, event: str | None = None) -> str:
    prefix = f"event: {event}\n" if event else ""
    return f"{prefix}data: {json.dumps(data, separators=(',', ':'))}\n\n"


def open_store(settings: Settings) -> Store:
    """Pick the storage backend: SQLite when ``database_path`` is set, else memory."""
    if settings.database_path:
        return SqliteStore(
            settings.database_path,
            max_models=settings.max_models,
            max_inferences_per_model=settings.max_inferences_per_model,
        )
    return InferenceStore(
        max_models=settings.max_models,
        max_inferences_per_model=settings.max_inferences_per_model,
    )


def build_app(store: Store | None = None, settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    owns_store = store is None
    store = store or open_store(settings)
    backend = store

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        if owns_store:  # a store passed in by the caller is the caller's to close
            backend.close()

    metrics = Metrics()
    limiter = (
        RateLimiter(settings.rate_limit_per_minute, settings.rate_limit_burst)
        if settings.rate_limit_per_minute
        else None
    )
    started_at = time.monotonic()

    app = FastAPI(
        title="AI Inference Server",
        version=__version__,
        description=docs.DESCRIPTION,
        openapi_tags=docs.TAGS,
        contact={"name": "Alisha Karma", "url": "https://alishakarma.com"},
        lifespan=lifespan,
    )

    docs.install(app)

    # ---- middleware & error handling -------------------------------------------------
    # Added first = innermost: oversized bodies surface as errors inside the logging/metrics
    # layer below, so they are counted and logged like any other response.
    app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_body_bytes)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        supplied_id = request.headers.get("x-request-id", "")
        request_id = supplied_id if _REQUEST_ID_RE.match(supplied_id) else uuid.uuid4().hex
        start = time.perf_counter()
        limit_headers: dict[str, str] = {}
        limited = False
        path = request.url.path
        if limiter is not None and request.method != "OPTIONS" and not _is_exempt(path):
            decision = limiter.check(_client_id(request, settings.trust_proxy))
            limit_headers = {
                "x-ratelimit-limit": str(decision.limit),
                "x-ratelimit-remaining": str(decision.remaining),
                "x-ratelimit-reset": str(decision.reset),
            }
            if not decision.allowed:
                limited = True
                limit_headers["retry-after"] = str(decision.retry_after)
        if limited:
            response: Response = _error(429, "rate limit exceeded")
        elif (
            settings.api_key
            and not _is_public(request.url.path)
            and not _authorized(request, settings.api_key)
        ):
            response = _error(401, "unauthorized")
            response.headers["www-authenticate"] = "Bearer"
        else:
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("unhandled error request_id=%s", request_id)
                response = _error(500, "internal server error")
        elapsed = time.perf_counter() - start
        elapsed_ms = elapsed * 1000
        route = getattr(request.scope.get("route"), "path", "unmatched")
        metrics.observe_request(request.method, route, response.status_code, elapsed)
        for name, value in limit_headers.items():
            response.headers[name] = value
        response.headers["x-request-id"] = request_id
        response.headers["x-response-time-ms"] = f"{elapsed_ms:.2f}"
        for name, value in _SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if not _is_static(request.url.path):
            response.headers.setdefault("cache-control", "no-store")
        logger.info(
            "%s %s -> %d (%.2fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(elapsed_ms, 2),
            },
        )
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = _HTTP_MESSAGES.get(exc.status_code) or str(exc.detail)
        return _error(exc.status_code, message)

    @app.exception_handler(BodyTooLarge)
    async def body_too_large(_request: Request, exc: BodyTooLarge) -> JSONResponse:
        return _error(413, str(exc))

    @app.exception_handler(sqlite3.Error)
    async def storage_unavailable(_request: Request, exc: sqlite3.Error) -> JSONResponse:
        logger.error("storage error: %s", exc)
        response = _error(503, "storage temporarily unavailable")
        response.headers["retry-after"] = "1"
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return _error(400, "invalid request")

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=_CORS_HEADERS,
            expose_headers=["x-request-id", "x-total-count", "x-response-time-ms"],
            max_age=600,
        )

    # ---- landing page ----------------------------------------------------------------

    app.mount("/assets", StaticFiles(directory=STATIC_DIR), name="assets")

    @app.get("/", include_in_schema=False)
    async def landing() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html", media_type="text/html")

    # ---- routes ----------------------------------------------------------------------

    def _count(model_id: str, n: int = 1) -> None:
        model = store.get_model(model_id)
        if model:
            metrics.observe_inferences(model["type"], n)

    @app.get(
        "/livez",
        tags=["operations"],
        summary="Liveness probe",
        responses=docs.success(200, ProbeResponse, "The process is alive."),
    )
    async def livez() -> dict[str, Any]:
        """The process is up and serving requests. Never touches storage."""
        return _ok({"status": "alive"})

    @app.get(
        "/readyz",
        tags=["operations"],
        summary="Readiness probe",
        response_model=None,
        responses={
            **docs.success(200, ProbeResponse, "Storage answers; ready for traffic."),
            **docs.errors(503),
        },
    )
    async def readyz() -> JSONResponse:
        """Ready to take traffic: 200 when storage answers, 503 otherwise."""
        if store.ping():
            return JSONResponse(content=_ok({"status": "ready", "storage": store.kind}))
        response = _error(503, "storage unavailable")
        response.headers["retry-after"] = "1"
        return response

    @app.get(
        "/health",
        tags=["operations"],
        summary="Status, version, storage backend and counts",
        responses=docs.success(200, HealthResponse, "Server status."),
    )
    async def health() -> dict[str, Any]:
        return _ok(
            {
                "status": "ok",
                "version": __version__,
                "storage": store.kind,
                "uptimeSeconds": round(time.monotonic() - started_at, 3),
                **store.stats(),
            }
        )

    @app.post(
        "/models",
        tags=["models"],
        summary="Register a model",
        status_code=201,
        responses={
            **docs.success(201, ModelResponse, "The created model."),
            **docs.errors(400, 401, 409, 413, 429, 503),
        },
        openapi_extra=docs.with_params(body=ModelCreate),
    )
    async def create_model(request: Request) -> JSONResponse:
        body = await _json_object(request)

        name = body.get("name")
        if not name:
            return _error(400, "name is required")
        if not isinstance(name, str):
            return _error(400, "name must be a string")
        name = name.strip()
        if not name:
            return _error(400, "name is required")
        if len(name) > settings.max_name_chars:
            return _error(400, f"name must be at most {settings.max_name_chars} characters")

        typ = body.get("type")
        if not isinstance(typ, str) or typ not in VALID_TYPES:
            return _error(400, TYPE_ERROR)

        config = body.get("config")
        if config is None:
            config = {}
        elif not isinstance(config, dict):
            return _error(400, "config must be an object")
        try:
            validate_config(typ, config)
        except ConfigError as exc:
            return _error(400, str(exc))

        try:
            model = store.create_model(name, typ, config)
        except StoreFull:
            return _error(429, "model limit reached")
        if model is None:
            return _error(409, "model with that name already exists")
        return JSONResponse(status_code=201, content=_ok(model))

    @app.get(
        "/metrics",
        tags=["operations"],
        summary="Prometheus metrics",
        response_class=PlainTextResponse,
        responses={200: {"description": "Metrics in the Prometheus text exposition format."}},
    )
    async def prometheus() -> PlainTextResponse:
        stats = store.stats()
        body = metrics.render(
            models=stats["models"],
            stored_inferences=stats["inferences"],
            uptime_seconds=time.monotonic() - started_at,
        )
        return PlainTextResponse(body, media_type="text/plain; version=0.0.4")

    @app.get(
        "/models",
        tags=["models"],
        summary="List models",
        responses={
            **docs.success(
                200, ModelListResponse, "Models in creation order.", docs.TOTAL_COUNT_HEADER
            ),
            **docs.errors(400, 401, 429, 503),
        },
        openapi_extra=docs.with_params(*docs.PAGING_PARAMS),
    )
    async def list_models(request: Request) -> JSONResponse:
        page = _page_params(request)
        if isinstance(page, str):
            return _error(400, page)
        items, total = store.list_models(*page)
        return _list_response(items, total)

    @app.get(
        "/models/{model_id}",
        tags=["models"],
        summary="Get a model",
        responses={
            **docs.success(200, ModelResponse, "The model."),
            **docs.errors(401, 404, 429, 503),
        },
    )
    async def get_model(model_id: str) -> JSONResponse:
        model = store.get_model(model_id)
        if not model:
            return _error(404, "model not found")
        return JSONResponse(content=_ok(model))

    @app.delete(
        "/models/{model_id}",
        tags=["models"],
        summary="Delete a model and its inference history",
        responses={
            **docs.success(200, DeletedResponse, "The model was removed."),
            **docs.errors(401, 404, 429, 503),
        },
    )
    async def delete_model(model_id: str) -> JSONResponse:
        if not store.delete_model(model_id):
            return _error(404, "model not found")
        return JSONResponse(content=_ok({"id": model_id, "removed": True}))

    @app.post(
        "/models/{model_id}/infer",
        tags=["inference"],
        summary="Run one input through a model",
        status_code=201,
        responses={
            **docs.success(201, InferenceResponse, "The stored inference."),
            **docs.errors(400, 401, 404, 413, 429, 503),
        },
        openapi_extra=docs.with_params(body=InferRequest),
    )
    async def infer(model_id: str, request: Request) -> JSONResponse:
        body = await _json_object(request)
        inp = body.get("input")
        if not inp:
            return _error(400, "input is required")
        if not isinstance(inp, str):
            return _error(400, "input must be a string")
        if len(inp) > settings.max_input_chars:
            return _error(413, f"input must be at most {settings.max_input_chars} characters")
        result = store.run_inference(model_id, inp)
        if result is None:
            return _error(404, "model not found")
        _count(model_id)
        return JSONResponse(status_code=201, content=_ok(result))

    @app.post(
        "/models/{model_id}/infer/batch",
        tags=["inference"],
        summary="Run many inputs in one atomic request",
        status_code=201,
        responses={
            **docs.success(201, InferenceListResponse, "One inference per input, in order."),
            **docs.errors(400, 401, 404, 413, 429, 503),
        },
        openapi_extra=docs.with_params(body=BatchRequest),
    )
    async def infer_batch(model_id: str, request: Request) -> JSONResponse:
        body = await _json_object(request)
        inputs = body.get("inputs")
        if inputs is None or inputs == []:
            return _error(400, "inputs is required")
        if not isinstance(inputs, list):
            return _error(400, "inputs must be an array")
        if len(inputs) > settings.max_batch_size:
            return _error(400, f"inputs must contain at most {settings.max_batch_size} items")
        for i, item in enumerate(inputs):
            if not isinstance(item, str) or not item:
                return _error(400, f"inputs[{i}] must be a non-empty string")
            if len(item) > settings.max_input_chars:
                return _error(
                    413, f"inputs[{i}] must be at most {settings.max_input_chars} characters"
                )
        results = store.run_batch(model_id, inputs)
        if results is None:
            return _error(404, "model not found")
        _count(model_id, len(results))
        return JSONResponse(status_code=201, content=_ok(results))

    @app.post(
        "/models/{model_id}/infer/stream",
        tags=["inference"],
        summary="Stream a text-generation result (Server-Sent Events)",
        response_class=StreamingResponse,
        responses={
            200: {
                "description": (
                    "One `token` event per word, then a final `done` event whose data is the "
                    "stored inference."
                ),
                "content": {
                    "text/event-stream": {
                        "schema": {"type": "string"},
                        "example": (
                            'event: token\ndata: {"index":0,"token":"Generated "}\n\n'
                            'event: done\ndata: {"id":"...","status":"completed",...}\n\n'
                        ),
                    }
                },
            },
            **docs.errors(400, 401, 404, 413, 429, 503),
        },
        openapi_extra=docs.with_params(body=InferRequest),
    )
    async def infer_stream(model_id: str, request: Request) -> Response:
        """Server-Sent Events: one ``token`` event per word, then a final ``done`` event."""
        model = store.get_model(model_id)
        if model is None:
            return _error(404, "model not found")
        if model["type"] != "text-generation":
            return _error(400, "streaming is only supported for text-generation models")
        body = await _json_object(request)
        inp = body.get("input")
        if not inp:
            return _error(400, "input is required")
        if not isinstance(inp, str):
            return _error(400, "input must be a string")
        if len(inp) > settings.max_input_chars:
            return _error(413, f"input must be at most {settings.max_input_chars} characters")
        result = store.run_inference(model_id, inp)
        if result is None:  # model deleted between the lookup and the run
            return _error(404, "model not found")
        _count(model_id)

        async def events() -> Any:
            for index, token in enumerate(_TOKEN_RE.findall(result["output"]["text"])):
                yield _sse({"index": index, "token": token}, "token")
            yield _sse(result, "done")

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    @app.get(
        "/models/{model_id}/inferences",
        tags=["inference"],
        summary="List a model's inference history",
        responses={
            **docs.success(
                200,
                InferenceListResponse,
                "Inferences, oldest first.",
                docs.TOTAL_COUNT_HEADER,
            ),
            **docs.errors(400, 401, 404, 429, 503),
        },
        openapi_extra=docs.with_params(*docs.PAGING_PARAMS),
    )
    async def list_inferences(model_id: str, request: Request) -> JSONResponse:
        page = _page_params(request)
        if isinstance(page, str):
            return _error(400, page)
        found = store.list_inferences(model_id, *page)
        if found is None:
            return _error(404, "model not found")
        return _list_response(*found)

    @app.get(
        "/models/{model_id}/inferences/{inference_id}",
        tags=["inference"],
        summary="Get one inference",
        responses={
            **docs.success(200, InferenceResponse, "The inference."),
            **docs.errors(401, 404, 429, 503),
        },
    )
    async def get_inference(model_id: str, inference_id: str) -> JSONResponse:
        res = store.get_inference(model_id, inference_id)
        if not res["modelFound"]:
            return _error(404, "model not found")
        if not res.get("inf"):
            return _error(404, "inference not found")
        return JSONResponse(content=_ok(res["inf"]))

    return app


def create_app() -> FastAPI:
    """Factory used by ``uvicorn --factory`` and the ``__main__`` entry point."""
    settings = Settings.from_env()
    configure_logging(settings.log_level, settings.log_format)
    return build_app(settings=settings)


def main() -> None:
    import uvicorn

    settings = Settings.from_env()
    uvicorn.run(
        "src.server:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
