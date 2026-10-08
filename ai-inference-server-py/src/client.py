"""A small, dependency-free client for the AI Inference Server.

    from src.client import Client

    ais = Client("http://localhost:3000")
    model = ais.create_model("sentiment", "text-classification")
    print(ais.infer(model["id"], "this is not bad at all")["output"])

Every method returns the unwrapped ``data`` of the server's response envelope and raises
``ApiError`` for error responses or ``ServerUnreachable`` when the server cannot be reached.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from typing import Any

DEFAULT_URL = "http://localhost:3000"


class ApiError(Exception):
    """The server answered with an error envelope."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class ServerUnreachable(Exception):
    """No HTTP response could be obtained (connection refused, DNS failure, timeout...)."""


class Page(list[Any]):
    """A list of items plus ``total``, the count across all pages."""

    total: int

    def __init__(self, items: list[Any], total: int) -> None:
        super().__init__(items)
        self.total = total


class Client:
    def __init__(
        self, base_url: str = DEFAULT_URL, api_key: str | None = None, timeout: float = 30.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    # ---- transport -------------------------------------------------------------------

    def _request(
        self, method: str, path: str, body: Any = None, query: dict[str, Any] | None = None
    ) -> urllib.request.Request:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        headers = {"accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["content-type"] = "application/json"
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return urllib.request.Request(url, data=data, method=method, headers=headers)

    def _open(self, req: urllib.request.Request) -> Any:
        try:
            return urllib.request.urlopen(req, timeout=self.timeout)  # noqa: S310
        except urllib.error.HTTPError as exc:
            raise ApiError(exc.code, _error_message(exc)) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise ServerUnreachable(f"cannot reach {self.base_url}: {reason}") from None

    def _call(
        self, method: str, path: str, body: Any = None, query: dict[str, Any] | None = None
    ) -> tuple[Any, Any]:
        with self._open(self._request(method, path, body, query)) as resp:
            envelope = json.loads(resp.read())
            return envelope["data"], resp.headers

    # ---- API -------------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        data, _ = self._call("GET", "/health")
        return data  # type: ignore[no-any-return]

    def metrics(self) -> str:
        with self._open(self._request("GET", "/metrics")) as resp:
            return resp.read().decode()  # type: ignore[no-any-return]

    def create_model(
        self, name: str, type: str, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"name": name, "type": type}
        if config:
            body["config"] = config
        data, _ = self._call("POST", "/models", body)
        return data  # type: ignore[no-any-return]

    def list_models(self, limit: int | None = None, offset: int = 0) -> Page:
        data, headers = self._call("GET", "/models", query={"limit": limit, "offset": offset})
        return Page(data, int(headers.get("x-total-count", len(data))))

    def get_model(self, model_id: str) -> dict[str, Any]:
        data, _ = self._call("GET", f"/models/{urllib.parse.quote(model_id, safe='')}")
        return data  # type: ignore[no-any-return]

    def delete_model(self, model_id: str) -> dict[str, Any]:
        data, _ = self._call("DELETE", f"/models/{urllib.parse.quote(model_id, safe='')}")
        return data  # type: ignore[no-any-return]

    def find_model(self, ref: str) -> dict[str, Any]:
        """Resolve a model by id or by name; raises ``ApiError(404)`` if neither matches."""
        try:
            return self.get_model(ref)
        except ApiError as exc:
            if exc.status != 404:
                raise
        offset = 0
        while True:
            page = self.list_models(limit=1000, offset=offset)
            for model in page:
                if model["name"] == ref:
                    found: dict[str, Any] = model
                    return found
            offset += len(page)
            if not page or offset >= page.total:
                raise ApiError(404, f"model not found: {ref}")

    def infer(self, model_id: str, text: str) -> dict[str, Any]:
        data, _ = self._call("POST", f"/models/{_q(model_id)}/infer", {"input": text})
        return data  # type: ignore[no-any-return]

    def batch(self, model_id: str, texts: list[str]) -> list[dict[str, Any]]:
        data, _ = self._call("POST", f"/models/{_q(model_id)}/infer/batch", {"inputs": texts})
        return data  # type: ignore[no-any-return]

    def stream(self, model_id: str, text: str) -> Iterator[tuple[str, dict[str, Any]]]:
        """Yield ``(event, data)`` pairs: many ``token`` events, then one ``done``.

        The ``done`` payload is the full, stored inference.
        """
        req = self._request("POST", f"/models/{_q(model_id)}/infer/stream", {"input": text})
        req.add_header("accept", "text/event-stream")
        with self._open(req) as resp:
            event, data_lines = "message", []
            for raw in resp:
                line = raw.decode().rstrip("\r\n")
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
                elif line == "" and data_lines:
                    yield event, json.loads("\n".join(data_lines))
                    event, data_lines = "message", []

    def stream_text(self, model_id: str, text: str) -> Iterator[str]:
        """Yield generated tokens as they arrive."""
        for event, data in self.stream(model_id, text):
            if event == "token":
                yield data["token"]

    def list_inferences(self, model_id: str, limit: int | None = None, offset: int = 0) -> Page:
        data, headers = self._call(
            "GET", f"/models/{_q(model_id)}/inferences", query={"limit": limit, "offset": offset}
        )
        return Page(data, int(headers.get("x-total-count", len(data))))

    def get_inference(self, model_id: str, inference_id: str) -> dict[str, Any]:
        data, _ = self._call("GET", f"/models/{_q(model_id)}/inferences/{_q(inference_id)}")
        return data  # type: ignore[no-any-return]


def _q(part: str) -> str:
    return urllib.parse.quote(part, safe="")


def _error_message(exc: urllib.error.HTTPError) -> str:
    try:
        envelope = json.loads(exc.read())
        return str(envelope.get("error") or exc.reason)
    except Exception:
        return str(exc.reason)
