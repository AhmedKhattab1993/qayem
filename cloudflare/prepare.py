"""Bundle the same comparison code as the local API, with no ingestion dependencies."""
from pathlib import Path
import argparse
import hashlib
import shutil

root = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--assets-dir", type=Path, default=root.parent / "web/dist")
args = parser.parse_args()
package = root / "build" / "qayem"
package.mkdir(parents=True, exist_ok=True)
(package / "__init__.py").write_text("")
for name in ("valuation.py", "website_data.py", "web_common.py", "cloud_web.py", "cloud_media.py"):
    shutil.copyfile(root.parent / "src" / "qayem" / name, package / name)
films = {name: {"size": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
         for name in ("explainer-v4-720.mp4", "explainer-v4-1080.mp4")
         for path in [args.assets_dir / "media" / name]}
(root / "build" / "main.py").write_text(
    "from urllib.parse import urlsplit\nfrom workers import WorkerEntrypoint, asgi\n"
    "from qayem.cloud_web import create_cloud_app\nfrom qayem.cloud_media import serve_film\n"
    + f"app = create_cloud_app()\nFILMS = {films!r}\n"
    "class Default(WorkerEntrypoint):\n"
    "    async def fetch(self, request):\n"
    "        path = urlsplit(request.url).path\n"
    "        if path.startswith('/media/') and path.endswith('.mp4'):\n"
    "            return await serve_film(request, self.env, FILMS)\n"
    "        return await asgi.fetch(app, request, self.env, self.ctx)\n"
)
