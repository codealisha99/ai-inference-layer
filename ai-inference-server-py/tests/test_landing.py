import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from src.config import Settings
from src.server import STATIC_DIR, build_app


@pytest.fixture
def client():
    with TestClient(build_app()) as c:
        yield c


class TestLandingPage:
    def test_serves_html_at_root(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert "<h1" in r.text

    def test_not_listed_in_openapi(self, client):
        assert "/" not in client.get("/openapi.json").json()["paths"]

    @pytest.mark.parametrize(
        ("path", "kind"),
        [
            ("/assets/styles.css", "text/css"),
            ("/assets/app.js", "javascript"),
            ("/assets/favicon.svg", "image/svg+xml"),
        ],
    )
    def test_assets_are_served(self, client, path, kind):
        r = client.get(path)
        assert r.status_code == 200
        assert kind in r.headers["content-type"]

    def test_missing_asset_uses_error_envelope(self, client):
        r = client.get("/assets/nope.css")
        assert r.status_code == 404
        assert r.json() == {"success": False, "data": None, "error": "not found"}

    def test_page_references_only_existing_local_assets(self):
        html = (STATIC_DIR / "index.html").read_text()
        refs = re.findall(r'(?:href|src)="(/assets/[^"]+)"', html)
        assert refs
        for ref in refs:
            assert Path(STATIC_DIR, urlsplit(ref).path.removeprefix("/assets/")).is_file(), ref

    def test_page_links_resolve(self, client):
        html = client.get("/").text
        for path in ("/docs", "/redoc", "/openapi.json", "/health"):
            assert f'href="{path}"' in html
            assert client.get(path).status_code == 200


class TestLandingWithApiKey:
    @pytest.fixture
    def secured(self):
        with TestClient(build_app(settings=Settings(api_key="s3cret"))) as c:
            yield c

    def test_page_and_assets_stay_public(self, secured):
        assert secured.get("/").status_code == 200
        assert secured.get("/assets/styles.css").status_code == 200

    def test_api_still_requires_key(self, secured):
        assert secured.get("/models").status_code == 401
        assert secured.get("/models", headers={"x-api-key": "s3cret"}).status_code == 200


@pytest.mark.parametrize("path", ["/", "/docs", "/redoc"])
def test_shared_shell_and_versioned_assets(client, path):
    page = client.get(path).text
    assert '<header class="header">' in page
    assert '<footer class="footer">' in page
    assert "<!-- site-" not in page
    assert "__DOCS_" not in page
    references = re.findall(r'(?:href|src)="(/assets/[^"]+)"', page)
    assert references
    for reference in references:
        assert "?v=" in reference
        assert client.get(reference).status_code == 200


def test_documentation_routes_stay_out_of_api_contract(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert not {"/docs", "/redoc", "/docs/oauth2-redirect"} & set(paths)
    assert client.get("/docs/oauth2-redirect").status_code == 200


def test_browser_404_preserves_machine_readable_errors(client):
    page = client.get("/missing-page", headers={"accept": "text/html"})
    assert page.status_code == 404
    assert "Page not found" in page.text
    assert '<header class="header">' in page.text
    for path in ("/missing-page", "/models/missing", "/assets/missing.css"):
        response = client.get(
            path, headers={"accept": "text/html" if path != "/missing-page" else "application/json"}
        )
        assert response.status_code == 404
        assert response.json()["success"] is False
