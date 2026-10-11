"""Check the shipped pages and the local destinations in the deployment routing."""

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit


def test_production_pages_and_local_rewrites():
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root / "scripts/build_frontend.py")], check=True)
    output = root / "public"
    for path in ("index.html", "docs/index.html", "redoc/index.html", "404.html"):
        html = (output / path).read_text()
        assert "<!-- site-" not in html
        assert "__DOCS_" not in html
        for ref in re.findall(r'(?:href|src)="(/assets/[^"]+)"', html):
            assert (output / urlsplit(ref).path.lstrip("/")).is_file(), ref
    config = json.loads((root / "vercel.json").read_text())
    rewrites = {rule["source"]: rule["destination"] for rule in config["rewrites"]}
    for route in ("/docs", "/redoc"):
        assert rewrites[route] == f"{route}/index.html"
        assert (output / rewrites[route].lstrip("/")).is_file()
    assert not list((output / "assets").glob("*.html"))
