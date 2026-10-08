"""Helpers that make the generated OpenAPI document describe the real contract."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel

from .schemas import SCHEMAS, ErrorResponse

DESCRIPTION = """\
A small model registry and inference API. Register a model, run text through it, read the
history back.

Every JSON response uses one envelope: `{"success": bool, "data": ..., "error": string | null}`.
Errors always use it too, including 404, 405, 413, 429 and 500.

If the server was started with `API_KEY`, send `X-API-Key: <key>` or `Authorization: Bearer <key>`
(except on `/health`, `/livez`, `/readyz`, this documentation and the landing page).
"""

TAGS = [
    {"name": "models", "description": "Register, list, inspect and delete models."},
    {"name": "inference", "description": "Run inputs through a model and read the history."},
    {"name": "operations", "description": "Health, probes and metrics."},
]

_ERROR_TEXT = {
    400: "Missing or invalid field, query parameter or config.",
    401: "Missing or invalid API key (only when the server requires one).",
    404: "Unknown route, model or inference.",
    409: "A model with that name already exists.",
    413: "Input or request body is larger than the configured limit.",
    429: "Rate limit exceeded (see `Retry-After`) or the model limit was reached.",
    503: "Storage is temporarily unavailable (see `Retry-After`).",
}

_ID = {"in": "path", "required": True, "schema": {"type": "string"}}
PAGING_PARAMS: list[dict[str, Any]] = [
    {
        "name": "limit",
        "in": "query",
        "required": False,
        "description": "Page size, 1-1000. Omit to return everything.",
        "schema": {"type": "integer", "minimum": 1, "maximum": 1000},
    },
    {
        "name": "offset",
        "in": "query",
        "required": False,
        "description": "Items to skip. Default 0.",
        "schema": {"type": "integer", "minimum": 0, "default": 0},
    },
]
TOTAL_COUNT_HEADER: dict[str, Any] = {
    "X-Total-Count": {
        "description": "Total items across all pages.",
        "schema": {"type": "integer"},
    }
}


def errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    """``responses=`` entries documenting the envelope for each error status."""
    return {c: {"model": ErrorResponse, "description": _ERROR_TEXT[c]} for c in codes}


def success(
    status: int, model: type[BaseModel], description: str, headers: dict[str, Any] | None = None
) -> dict[int | str, dict[str, Any]]:
    entry: dict[str, Any] = {"model": model, "description": description}
    if headers:
        entry["headers"] = headers
    return {status: entry}


def request_body(model: type[BaseModel]) -> dict[str, Any]:
    """``openapi_extra`` describing a JSON body that the handler validates by hand."""
    return {
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {"schema": {"$ref": f"#/components/schemas/{model.__name__}"}}
            },
        }
    }


def with_params(*params: dict[str, Any], body: type[BaseModel] | None = None) -> dict[str, Any]:
    extra: dict[str, Any] = request_body(body) if body else {}
    if params:
        extra["parameters"] = list(params)
    return extra


def install(app: FastAPI) -> None:
    """Replace ``app.openapi`` so hand-validated request models are included."""

    def build() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=DESCRIPTION,
            routes=app.routes,
            tags=TAGS,
            contact=app.contact,
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for model in SCHEMAS:
            doc = model.model_json_schema(ref_template="#/components/schemas/{model}")
            components.update(doc.pop("$defs", {}))
            components[model.__name__] = doc
        app.openapi_schema = schema
        return schema

    app.openapi = build  # type: ignore[method-assign]
