"""Shared document shell for the playground and API documentation."""

import hashlib
import re
from pathlib import Path

STATIC_DIR = Path(__file__).parent / "static"


def render_page(filename: str, *, docs_kind: str = "swagger") -> str:
    page = (STATIC_DIR / filename).read_text()
    for part in ("header", "footer"):
        page = page.replace(f"<!-- site-{part} -->", (STATIC_DIR / f"{part}.html").read_text())
    page = page.replace("__DOCS_KIND__", docs_kind).replace(
        "__DOCS_TITLE__", "API reference" if docs_kind == "swagger" else "Schema reference"
    )
    page = page.replace(
        "__DOCS_INTRO__",
        (
            "Explore endpoints and send real requests to this server. "
            "Changes made here affect its models and history."
        )
        if docs_kind == "swagger"
        else (
            "Read request shapes, response examples, and model schemas. "
            "To send a request, open the interactive API view."
        ),
    )

    def version_asset(match: re.Match[str]) -> str:
        path = match.group(1)
        asset = STATIC_DIR / path.removeprefix("/assets/")
        digest = hashlib.sha256(asset.read_bytes()).hexdigest()[:12]
        return f'"{path}?v={digest}"'

    return re.sub(r'"(/assets/[^"?]+)"', version_asset, page)
