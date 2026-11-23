"""Pyodide 浏览器渲染原型的静态服务器；不提供任何渲染或写盘 API。"""

from __future__ import annotations

import argparse
from functools import lru_cache, partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from threading import BoundedSemaphore, Lock
from time import monotonic
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[2]
PROTOTYPE_DIR = ROOT / "prototype" / "pyodide"
_ASSET_EXCLUDES = {"legacy", "psd_export", "ref"}
_STATIC_NAMES = ("index.html", "style.css", "storage.js", "layout.js", "app.js",
                 "worker.js", "bridge.py", "sw.js")
_STATIC_FILES = {"/": PROTOTYPE_DIR / "index.html"}
_STATIC_FILES.update({f"/{name}": PROTOTYPE_DIR / name for name in _STATIC_NAMES})


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


@lru_cache(maxsize=1)
def build_runtime_zip() -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for path, name in _runtime_files():
            archive.write(path, name)
    return buf.getvalue()


class RequestRateLimiter:
    def __init__(self, rate: float, burst: int):
        if rate <= 0 or burst < 1:
            raise ValueError("请求速率与突发上限必须为正数")
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.updated = monotonic()
        self.lock = Lock()

    def allow(self) -> bool:
        with self.lock:
            now = monotonic()
            self.tokens = min(self.burst, self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens < 1:
                return False
            self.tokens -= 1
            return True


class PrototypeServer(ThreadingHTTPServer):
    request_queue_size = 32
    daemon_threads = True
    block_on_close = False

    def __init__(self, server_address, handler, *, request_rate=2.0,
                 request_burst=30, max_connections=8):
        if max_connections < 1:
            raise ValueError("并发上限必须为正整数")
        self.rate_limiter = RequestRateLimiter(request_rate, request_burst)
        self.connection_slots = BoundedSemaphore(max_connections)
        super().__init__(server_address, handler)

    def process_request(self, request, client_address):
        self.connection_slots.acquire()
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.connection_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connection_slots.release()


class PrototypeHandler(SimpleHTTPRequestHandler):
    timeout = 20
    server_version = "BWPDIY"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(self.timeout)

    def _dispatch(self, send_body: bool):
        if not self.server.rate_limiter.allow():
            self.send_response(429)
            self.send_header("Retry-After", "1")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        try:
            path = urlsplit(self.path).path
        except ValueError:
            self.send_error(400)
            return
        if path == "/runtime.zip":
            data = build_runtime_zip()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            if send_body:
                self.wfile.write(data)
            return
        file = _STATIC_FILES.get(path)
        if file is None:
            self.send_error(404)
            return
        self.path = f"/{file.name}"
        if send_body:
            super().do_GET()
        else:
            super().do_HEAD()

    def do_GET(self):
        self._dispatch(send_body=True)

    def do_HEAD(self):
        self._dispatch(send_body=False)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'wasm-unsafe-eval'; "
            "worker-src 'self'; connect-src 'self' https://cdn.jsdelivr.net; "
            "img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; "
            "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        super().end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(description="BWPDIY 浏览器渲染原型")
    parser.add_argument("--port", type=int, default=8640)
    parser.add_argument("--request-rate", type=int, default=120, help="全服务每分钟请求数")
    parser.add_argument("--request-burst", type=int, default=30, help="瞬时请求上限")
    parser.add_argument("--max-connections", type=int, default=8, help="同时处理连接数")
    args = parser.parse_args()
    if min(args.request_rate, args.request_burst, args.max_connections) < 1:
        parser.error("请求速率、突发与并发上限必须为正整数")
    build_runtime_zip()
    handler = partial(PrototypeHandler, directory=str(PROTOTYPE_DIR))
    server = PrototypeServer(
        ("127.0.0.1", args.port), handler,
        request_rate=args.request_rate / 60, request_burst=args.request_burst,
        max_connections=args.max_connections)
    print(f"BWPDIY Pyodide 原型：http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
