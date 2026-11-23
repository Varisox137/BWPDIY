"""Pyodide 浏览器渲染原型的本地静态服务器；不提供任何渲染或写盘 API。"""

from __future__ import annotations

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[2]
PROTOTYPE_DIR = ROOT / "prototype" / "pyodide"
_ASSET_EXCLUDES = {"legacy", "psd_export", "ref"}


def _runtime_files():
    for path in sorted((ROOT / "bwpdiy").rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.suffix in {".py", ".json", ".png"}:
            yield path, path.relative_to(ROOT).as_posix()
    for path in sorted((ROOT / "assets").rglob("*")):
        if (path.is_file() and path.suffix != ".psd"
                and not _ASSET_EXCLUDES.intersection(path.relative_to(ROOT / "assets").parts)):
            yield path, path.relative_to(ROOT).as_posix()
    yield PROTOTYPE_DIR / "bridge.py", "bridge.py"


def build_runtime_zip() -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for path, name in _runtime_files():
            archive.write(path, name)
    return buf.getvalue()


class PrototypeHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path in {"/runtime.zip", "/prototype/pyodide/runtime.zip"}:
            data = build_runtime_zip()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        prefix = "/prototype/pyodide/"
        if path == "/":
            relative = "index.html"
        elif path.startswith(prefix):
            relative = path.removeprefix(prefix) or "index.html"
        elif path.startswith("/"):
            relative = path.removeprefix("/")
        else:
            self.send_error(404)
            return
        self.path = "/" + relative
        super().do_GET()

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description="BWPDIY 浏览器渲染原型")
    parser.add_argument("--port", type=int, default=8640)
    args = parser.parse_args()
    handler = partial(PrototypeHandler, directory=str(PROTOTYPE_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
    print(f"BWPDIY Pyodide 原型：http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
