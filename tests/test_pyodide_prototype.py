from functools import partial
from http.client import HTTPConnection
from io import BytesIO
import shutil
import subprocess
from threading import Thread
from zipfile import ZipFile

import pytest

from prototype.pyodide.server import (
    PROTOTYPE_DIR, PrototypeHandler, ThreadingHTTPServer, build_runtime_zip)


def test_runtime_zip_contains_renderer_and_real_assets():
    archive = ZipFile(BytesIO(build_runtime_zip()))
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
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status == 200
        assert "在线本地版" in response.read().decode("utf-8")
        assert response.getheader("Location") is None
        connection.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_static_server_only_exposes_prototype_root():
    handler = partial(PrototypeHandler, directory=str(PROTOTYPE_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        for path in ("/README.md", "/prototype/pyodide/", "/prototype/pyodide/runtime.zip"):
            connection.request("GET", path)
            response = connection.getresponse()
            assert response.status == 404
            response.read()
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
const cache = {
  match: async request => entries.get(request.url),
  put: async (request, response) => entries.set(request.url, response),
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
  const request = {method: 'GET', url: 'http://local/runtime.zip'};
  for (let index = 0; index < 2; index += 1) {
    const event = {request, respondWith(promise) { this.promise = promise; }};
    listeners.fetch(event);
    await event.promise;
  }
  if (networkRequests !== 1) throw new Error(`重复请求进入网络 ${networkRequests} 次`);
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(PROTOTYPE_DIR / "sw.js")],
        capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr
