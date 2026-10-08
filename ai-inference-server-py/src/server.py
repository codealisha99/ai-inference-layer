from __future__ import annotations

import hmac
import json
import logging
import re
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

from . import __version__
from .config import Settings
from .engines import ConfigError, validate_config
from .inference import VALID_TYPES, InferenceStore, Store, StoreFull
from .metrics import Metrics
from .sqlite_store import SqliteStore

logger = logging.getLogger("ai_inference_server")

STATIC_DIR = Path(__file__).parent / "static"

TYPE_ERROR = "type must be one of: text-generation, text-classification, embedding"
_HTTP_MESSAGES = {404: "not found", 405: "method not allowed", 401: "unauthorized"}
_PUBLIC_PATHS = frozenset({"/", "/health", "/docs", "/redoc", "/openapi.json"})
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
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


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
    started_at = time.monotonic()

    app = FastAPI(
        title="AI Inference Server",
        version=__version__,
        description="A small model registry and inference API with deterministic engines.",
        lifespan=lifespan,
    )

    # ---- middleware & error handling -------------------------------------------------

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        start = time.perf_counter()
        if (
            settings.api_key
            and not _is_public(request.url.path)
            and not _authorized(request, settings.api_key)
        ):
            response: Response = _error(401, "unauthorized")
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
        response.headers["x-request-id"] = request_id
        response.headers["x-response-time-ms"] = f"{elapsed_ms:.2f}"
        logger.info(
            "%s %s -> %d (%.2fms) request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        message = _HTTP_MESSAGES.get(exc.status_code) or str(exc.detail)
        return _error(exc.status_code, message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return _error(400, "invalid request")

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

    @app.get("/health")
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

    @app.post("/models")
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

    @app.get("/metrics", include_in_schema=False)
    async def prometheus() -> PlainTextResponse:
        stats = store.stats()
        body = metrics.render(
            models=stats["models"],
            stored_inferences=stats["inferences"],
            uptime_seconds=time.monotonic() - started_at,
        )
        return PlainTextResponse(body, media_type="text/plain; version=0.0.4")

    @app.get("/models")
    async def list_models(request: Request) -> JSONResponse:
        page = _page_params(request)
        if isinstance(page, str):
            return _error(400, page)
        items, total = store.list_models(*page)
        return _list_response(items, total)

    @app.get("/models/{mid}")
    async def get_model(mid: str) -> JSONResponse:
        model = store.get_model(mid)
        if not model:
            return _error(404, "model not found")
        return JSONResponse(content=_ok(model))

    @app.delete("/models/{mid}")
    async def delete_model(mid: str) -> JSONResponse:
        if not store.delete_model(mid):
            return _error(404, "model not found")
        return JSONResponse(content=_ok({"id": mid, "removed": True}))

    @app.post("/models/{mid}/infer")
    async def infer(mid: str, request: Request) -> JSONResponse:
        body = await _json_object(request)
        inp = body.get("input")
        if not inp:
            return _error(400, "input is required")
        if not isinstance(inp, str):
            return _error(400, "input must be a string")
        if len(inp) > settings.max_input_chars:
            return _error(413, f"input must be at most {settings.max_input_chars} characters")
        result = store.run_inference(mid, inp)
        if result is None:
            return _error(404, "model not found")
        _count(mid)
        return JSONResponse(status_code=201, content=_ok(result))

    @app.post("/models/{mid}/infer/batch")
    async def infer_batch(mid: str, request: Request) -> JSONResponse:
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
        results = store.run_batch(mid, inputs)
        if results is None:
            return _error(404, "model not found")
        _count(mid, len(results))
        return JSONResponse(status_code=201, content=_ok(results))

    @app.post("/models/{mid}/infer/stream")
    async def infer_stream(mid: str, request: Request) -> Response:
        """Server-Sent Events: one ``token`` event per word, then a final ``done`` event."""
        model = store.get_model(mid)
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
        result = store.run_inference(mid, inp)
        if result is None:  # model deleted between the lookup and the run
            return _error(404, "model not found")
        _count(mid)

        async def events() -> Any:
            for index, token in enumerate(_TOKEN_RE.findall(result["output"]["text"])):
                yield _sse({"index": index, "token": token}, "token")
            yield _sse(result, "done")

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    @app.get("/models/{mid}/inferences")
    async def list_inferences(mid: str, request: Request) -> JSONResponse:
        page = _page_params(request)
        if isinstance(page, str):
            return _error(400, page)
        found = store.list_inferences(mid, *page)
        if found is None:
            return _error(404, "model not found")
        return _list_response(*found)

    @app.get("/models/{mid}/inferences/{inference_id}")
    async def get_inference(mid: str, inference_id: str) -> JSONResponse:
        res = store.get_inference(mid, inference_id)
        if not res["modelFound"]:
            return _error(404, "model not found")
        if not res.get("inf"):
            return _error(404, "inference not found")
        return JSONResponse(content=_ok(res["inf"]))

    return app


def create_app() -> FastAPI:
    """Factory used by ``uvicorn --factory`` and the ``__main__`` entry point."""
    settings = Settings.from_env()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
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
