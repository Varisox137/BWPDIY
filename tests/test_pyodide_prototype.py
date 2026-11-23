from functools import partial
from http.client import HTTPConnection
from io import BytesIO
import shutil
import subprocess
from threading import Thread
from zipfile import ZipFile

import pytest

from prototype.pyodide.server import (
    PROTOTYPE_DIR, PrototypeHandler, PrototypeServer, build_runtime_zip)


def test_runtime_zip_contains_renderer_and_real_assets():
    data = build_runtime_zip()
    assert build_runtime_zip() is data
    archive = ZipFile(BytesIO(data))
    names = set(archive.namelist())

    assert "bwpdiy/render/pipeline.py" in names
    assert "bwpdiy/render/default_layout.json" in names
    assert "bwpdiy/web/sample_art.png" in names
    assert "bridge.py" in names
    assert any(name.startswith("assets/fonts/") for name in names)
    assert any(name.startswith("assets/frames/") for name in names)
    assert not any(name.startswith("assets/ref/") for name in names)
    assert not any(name.endswith(".psd") for name in names)
    assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)


def test_static_server_serves_root_without_redirect():
    handler = partial(PrototypeHandler, directory=str(PROTOTYPE_DIR))
    server = PrototypeServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status == 200
        assert "在线本地版" in response.read().decode("utf-8")
        assert response.getheader("Location") is None
        assert "default-src 'self'" in response.getheader("Content-Security-Policy")
        assert "frame-ancestors 'none'" in response.getheader("Content-Security-Policy")
        assert response.getheader("X-Frame-Options") == "DENY"
        assert response.getheader("Referrer-Policy") == "no-referrer"
        connection.request("HEAD", "/")
        response = connection.getresponse()
        assert response.status == 200
        assert response.read() == b""
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_tutorial_assets_are_public_static_files():
    handler = partial(PrototypeHandler, directory=str(PROTOTYPE_DIR))
    server = PrototypeServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        for path in ("/tutorial.js", "/tutorial.css"):
            connection.request("GET", path)
            response = connection.getresponse()
            assert response.status == 200
            response.read()
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_static_server_only_exposes_prototype_root():
    handler = partial(PrototypeHandler, directory=str(PROTOTYPE_DIR))
    server = PrototypeServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        for path in ("/README.md", "/prototype/pyodide/", "/prototype/pyodide/runtime.zip",
                     "/../server.py", "/%2e%2e/server.py", "/assets/fonts/", "/api/render",
                     "/runtime.zip", "/runtime-chunks/999"):
            connection.request("GET", path)
            response = connection.getresponse()
            assert response.status == 404
            response.read()
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_global_request_rate_limit():
    handler = partial(PrototypeHandler, directory=str(PROTOTYPE_DIR))
    server = PrototypeServer(("127.0.0.1", 0), handler, request_rate=1, request_burst=2)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        statuses = []
        for _ in range(3):
            connection.request("GET", "/")
            response = connection.getresponse()
            statuses.append(response.status)
            response.read()
        assert statuses == [200, 200, 429]
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")
def test_same_origin_resources_use_versioned_cache():
    script = r"""
const fs = require('fs');
const vm = require('vm');
const listeners = {};
const entries = new Map();
let networkRequests = 0;
const key = request => typeof request === 'string' ? request : request.url;
const cache = {
  match: async request => entries.get(key(request)),
  put: async (request, response) => entries.set(key(request), response),
};
const context = {
  URL,
  self: {
    location: {origin: 'http://local'},
    addEventListener: (type, listener) => { listeners[type] = listener; },
  },
  caches: {open: async () => cache},
  fetch: async () => {
    networkRequests += 1;
    return {ok: true, clone() { return this; }};
  },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
(async () => {
  async function dispatch(request) {
    const event = {request, handled: false, respondWith(promise) {
      this.handled = true; this.promise = promise;
    }};
    listeners.fetch(event);
    if (event.handled) await event.promise;
    return event.handled;
  }
  for (const url of ['http://local/runtime-chunks/0', 'http://local/runtime-chunks/0?a=1',
                     'http://local/runtime-chunks/0?a=2']) {
    if (!await dispatch({method: 'GET', url})) throw new Error('已知资源未被缓存处理');
  }
  if (networkRequests !== 1) throw new Error(`重复或查询变体进入网络 ${networkRequests} 次`);
  if (await dispatch({method: 'GET', url: 'http://local/api/render'})) {
    throw new Error('Service Worker 不应拦截未知地址');
  }
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(PROTOTYPE_DIR / "sw.js")],
        capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")
def test_worker_rejects_unsafe_artwork_before_runtime_initialization():
    script = r"""
const fs = require('fs');
const vm = require('vm');
const messages = [];
const context = {
  URL, performance, Uint8Array,
  self: {postMessage: message => messages.push(message)},
  importScripts: () => { throw new Error('运行时不应被加载'); },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
(async () => {
  await context.self.onmessage({data: {type: 'render', id: 7,
    artwork: new ArrayBuffer(4), payload: {artwork_path: '../../bridge.py'}}});
  await context.self.onmessage({data: {type: 'render', id: 8,
    artwork: {byteLength: 64 * 1024 * 1024 + 1}, payload: {artwork_path: 'artwork.png'}}});
  for (const [id, text] of [[7, '卡图路径非法'], [8, '卡图文件过大']]) {
    const message = messages.find(item => item.id === id);
    if (!message || message.type !== 'error' || !message.message.includes(text)) {
      throw new Error(`未拦截非法卡图 ${id}: ${JSON.stringify(messages)}`);
    }
  }
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(PROTOTYPE_DIR / "worker.js")],
        capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr


def test_response_timeout_does_not_abort_large_download_at_header_limit():
    from types import SimpleNamespace
    handler = object.__new__(PrototypeHandler)
    timeouts = []
    handler.connection = SimpleNamespace(settimeout=timeouts.append)
    handler.server = SimpleNamespace(rate_limiter=SimpleNamespace(allow=lambda: True))
    handler.path = "/missing"
    handler.send_error = lambda status: None
    handler._dispatch(send_body=False)
    assert timeouts == [PrototypeHandler.response_timeout]


@pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")
def test_worker_retries_required_resource_downloads():
    script = r"""
const fs = require('fs');
const vm = require('vm');
let attempts = 0;
const context = {
  URL, performance, Uint8Array, setTimeout,
  self: {postMessage: () => {}},
  fetch: async () => {
    attempts += 1;
    return attempts < 3 ? {ok: false, status: 503} : {ok: true};
  },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
(async () => {
  const response = await context.fetchRequired('runtime.zip');
  if (!response.ok || attempts !== 3) throw new Error(`下载重试次数异常：${attempts}`);
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(PROTOTYPE_DIR / "worker.js")],
        capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")
def test_worker_reports_runtime_byte_progress():
    script = r"""
const fs = require('fs');
const vm = require('vm');
const messages = [];
const requested = [];
const chunks = [new Uint8Array([1, 2]), new Uint8Array([3, 4]), new Uint8Array([5, 6])];
const context = {
  URL, Uint8Array, setTimeout, performance,
  self: {postMessage: message => messages.push(message)},
  fetch: async url => {
    requested.push(url);
    if (url === 'runtime.json') return {ok: true, json: async () => ({size: 6, chunk_size: 2, chunks: 3})};
    const match = /^runtime-chunks\/(\d)$/.exec(url);
    if (!match) return {ok: false, status: 404};
    const chunk = chunks[Number(match[1])];
    return {ok: true, arrayBuffer: async () => chunk.buffer};
  },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
(async () => {
  const bytes = await context.downloadRuntime();
  if (bytes.length !== 6 || bytes[5] !== 6) throw new Error('下载字节拼接错误');
  if (requested.join(',') !== 'runtime.json,runtime-chunks/0,runtime-chunks/1,runtime-chunks/2') {
    throw new Error(`分包顺序错误：${requested}`);
  }
  const status = messages.filter(item => item.type === 'status').map(item => item.message).join('\n');
  for (const percent of ['33%', '66%', '100%']) {
    if (!status.includes(percent)) throw new Error(`缺少下载进度 ${percent}: ${status}`);
  }
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(PROTOTYPE_DIR / "worker.js")],
        capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr


def test_client_disconnect_is_logged_without_exception_stack(caplog):
    caplog.set_level("INFO", logger="bwpdiy.online")

    class DisconnectHandler:
        def __init__(self, *args):
            raise BrokenPipeError(32, "Broken pipe")

    class Request:
        def shutdown(self, how): pass
        def close(self): pass

    server = PrototypeServer(("127.0.0.1", 0), DisconnectHandler)
    server.connection_slots.acquire()
    server.process_request_thread(Request(), ("127.0.0.1", 0))
    server.server_close()
    assert "客户端中断连接：BrokenPipeError" in caplog.text
    assert "Traceback" not in caplog.text


def test_runtime_chunks_reassemble_exact_archive():
    from prototype.pyodide.server import runtime_chunk, runtime_manifest
    data = build_runtime_zip()
    manifest = runtime_manifest()
    assert manifest["size"] == len(data)
    assert manifest["chunk_size"] == 2 * 1024 * 1024
    assert manifest["chunks"] == (len(data) + manifest["chunk_size"] - 1) // manifest["chunk_size"]
    assert b"".join(runtime_chunk(index) for index in range(manifest["chunks"])) == data
    for index in (-1, manifest["chunks"]):
        with pytest.raises(ValueError):
            runtime_chunk(index)
