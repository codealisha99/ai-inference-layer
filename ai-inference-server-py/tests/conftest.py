import socket
import threading
import time

import pytest
import uvicorn

from src.config import Settings
from src.server import build_app


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class LiveServer:
    def __init__(self, settings: Settings) -> None:
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        config = uvicorn.Config(
            build_app(settings=settings), host="127.0.0.1", port=self.port, log_level="warning"
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def start(self) -> None:
        self._thread.start()
        deadline = time.time() + 10
        while not self._server.started:
            if time.time() > deadline:
                raise RuntimeError("test server did not start")
            time.sleep(0.02)

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=10)


@pytest.fixture
def live_server(tmp_path):
    """A real HTTP server (SQLite-backed) on a free port, for client and CLI tests."""
    server = LiveServer(Settings(database_path=str(tmp_path / "live.db")))
    server.start()
    yield server
    server.stop()


@pytest.fixture
def secured_server(tmp_path):
    server = LiveServer(Settings(database_path=str(tmp_path / "sec.db"), api_key="s3cret"))
    server.start()
    yield server
    server.stop()


@pytest.fixture
def dead_url():
    return f"http://127.0.0.1:{_free_port()}"  # nothing is listening here
