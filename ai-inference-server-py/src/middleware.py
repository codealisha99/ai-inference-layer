"""ASGI-level protections that run before any route code."""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send


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
