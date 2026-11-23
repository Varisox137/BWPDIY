"""Pyodide 浏览器渲染原型的静态服务器；不提供任何渲染或写盘 API。"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from functools import lru_cache, partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from threading import BoundedSemaphore, Lock
from time import monotonic
from urllib.parse import unquote, urlsplit
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[2]
PROTOTYPE_DIR = ROOT / "prototype" / "pyodide"
_ASSET_EXCLUDES = {"legacy", "psd_export", "ref"}
_STATIC_NAMES = ("index.html", "style.css", "storage.js", "layout.js", "app.js",
                 "worker.js", "bridge.py", "sw.js", "log-admin.html",
                 "log-admin.js", "log-admin.css")
_STATIC_FILES = {"/": PROTOTYPE_DIR / "index.html"}
_STATIC_FILES.update({f"/{name}": PROTOTYPE_DIR / name for name in _STATIC_NAMES})
_STATIC_FILES["/log-admin"] = PROTOTYPE_DIR / "log-admin.html"
_STATIC_FILES["/log-admin/"] = PROTOTYPE_DIR / "log-admin.html"


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


RUNTIME_CHUNK_SIZE = 2 * 1024 * 1024


def runtime_manifest() -> dict:
    size = len(build_runtime_zip())
    return {"size": size, "chunk_size": RUNTIME_CHUNK_SIZE,
            "chunks": (size + RUNTIME_CHUNK_SIZE - 1) // RUNTIME_CHUNK_SIZE}


def runtime_chunk(index: int) -> bytes:
    data = build_runtime_zip()
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < runtime_manifest()["chunks"]:
        raise ValueError("运行时分包序号无效")
    start = index * RUNTIME_CHUNK_SIZE
    return data[start:start + RUNTIME_CHUNK_SIZE]


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
                 request_burst=30, max_connections=8, log_admin=None):
        if max_connections < 1:
            raise ValueError("并发上限必须为正整数")
        self.rate_limiter = RequestRateLimiter(request_rate, request_burst)
        self.connection_slots = BoundedSemaphore(max_connections)
        self.log_admin = log_admin
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

    def handle_error(self, request, client_address):
        error = sys.exc_info()[1]
        if isinstance(error, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            logging.getLogger("bwpdiy.online").info(
                "客户端中断连接：%s", type(error).__name__)
            return
        if isinstance(error, TimeoutError):
            logging.getLogger("bwpdiy.online").warning("连接处理超时")
            return
        super().handle_error(request, client_address)


class PrototypeHandler(SimpleHTTPRequestHandler):
    timeout = 20
    response_timeout = 120
    server_version = "BWPDIY"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(self.timeout)

    def _send_json(self, payload, send_body: bool):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if send_body:
            self.wfile.write(data)

    def _dispatch_log_admin(self, path: str, send_body: bool):
        service = self.server.log_admin
        if service is None:
            self.send_error(404)
            return
        client = self.client_address[0] if self.client_address else "unknown"
        if not service.authenticate(self.headers.get("Authorization"), client):
            self.send_response(401)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/api/log-admin/logs":
            self._send_json({"logs": service.list_logs()}, send_body)
            return
        prefix = "/api/log-admin/logs/"
        parts = path.removeprefix(prefix).split("/")
        if len(parts) != 2 or parts[1] not in {"preview", "download"}:
            self.send_error(404)
            return
        name, action = unquote(parts[0]), parts[1]
        try:
            if action == "preview":
                text, truncated = service.preview(name)
                self._send_json({"text": text, "truncated": truncated}, send_body)
                return
            file = service.log_path(name)
        except ValueError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(file.stat().st_size))
        self.send_header("Content-Disposition", f'attachment; filename="{file.name}"')
        self.end_headers()
        if send_body:
            with file.open("rb") as source:
                while chunk := source.read(64 * 1024):
                    self.wfile.write(chunk)

    def _dispatch(self, send_body: bool):
        self.connection.settimeout(self.response_timeout)
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
        self.request_path = path
        if path == "/api/log-admin/logs" or path.startswith("/api/log-admin/logs/"):
            self._dispatch_log_admin(path, send_body)
            return
        if path == "/runtime.json":
            self._send_json(runtime_manifest(), send_body)
            return
        if path.startswith("/runtime-chunks/"):
            try:
                data = runtime_chunk(int(path.removeprefix("/runtime-chunks/")))
            except ValueError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
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

    def log_request(self, code="-", size="-"):
        try:
            path = getattr(self, "request_path", urlsplit(self.path).path)
        except ValueError:
            path = "<无效地址>"
        logging.getLogger("bwpdiy.online.access").info("%s %s %s", self.command, path, code)

    def log_message(self, format, *args):
        logging.getLogger("bwpdiy.online").info(format, *args)

    def log_error(self, format, *args):
        logging.getLogger("bwpdiy.online").warning(format, *args)

    def do_GET(self):
        self._dispatch(send_body=True)

    def do_HEAD(self):
        self._dispatch(send_body=False)

    def end_headers(self):
        if (self.path.startswith("/api/log-admin/") or self.path.startswith("/log-admin")
                or self.path.startswith("/runtime") or self.path == "/log-admin.html"):
            self.send_header("Cache-Control", "no-store")
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
    import sys
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from bwpdiy.runlog import setup_run_logging
    from prototype.pyodide.log_admin import OnlineLogService, private_permissions

    log_path = setup_run_logging()
    private_permissions(log_path.parent, directory=True)
    private_permissions(log_path)
    log_admin = OnlineLogService(log_path.parent, log_path)
    log_admin.start()
    build_runtime_zip()
    logging.getLogger("bwpdiy.online").info("在线服务启动：port=%s", args.port)
    handler = partial(PrototypeHandler, directory=str(PROTOTYPE_DIR))
    server = PrototypeServer(
        ("127.0.0.1", args.port), handler,
        request_rate=args.request_rate / 60, request_burst=args.request_burst,
        max_connections=args.max_connections, log_admin=log_admin)
    print(f"BWPDIY Pyodide 原型：http://127.0.0.1:{args.port}/", flush=True)
    print(f"日志运维：http://127.0.0.1:{args.port}/log-admin/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        log_admin.close()
        logging.getLogger("bwpdiy.online").info("在线服务停止")


if __name__ == "__main__":
    main()
