"""Build the Vercel site from the API's shared static files."""

from pathlib import Path
import shutil

root = Path(__file__).resolve().parent.parent
source = root / "ai-inference-server-py" / "src" / "static"
target = root / "public"
target.mkdir(exist_ok=True)
shutil.copy2(source / "index.html", target / "index.html")
shutil.copytree(source, target / "assets", dirs_exist_ok=True)
