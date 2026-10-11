"""Build the Vercel site from the API's shared static files."""

import importlib.util
import shutil
from pathlib import Path

root = Path(__file__).resolve().parent.parent
module = importlib.util.spec_from_file_location("web", root / "ai-inference-server-py/src/web.py")
assert module and module.loader
web = importlib.util.module_from_spec(module)
module.loader.exec_module(web)
source = web.STATIC_DIR
target = root / "public"
target.mkdir(exist_ok=True)
(target / "index.html").write_text(web.render_page("index.html"))
shutil.copytree(source, target / "assets", dirs_exist_ok=True)
# HTML templates are server/build inputs, not public assets.
for template in (target / "assets").glob("*.html"):
    template.unlink()
