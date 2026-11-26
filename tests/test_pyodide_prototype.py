from contextlib import contextmanager
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


@contextmanager
def serve_http(**options):
    handler = partial(PrototypeHandler, directory=str(PROTOTYPE_DIR))
    server = PrototypeServer(("127.0.0.1", 0), handler, **options)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        yield connection
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_initial_form_is_neutral_and_tutorial_last_step_has_no_next():
    from html.parser import HTMLParser

    class FormParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.inputs = []
            self.selects = []
            self.current_select = None

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "input":
                self.inputs.append(attrs)
            elif tag == "select":
                self.current_select = {"attrs": attrs, "options": []}
                self.selects.append(self.current_select)
            elif tag == "option" and self.current_select is not None:
                self.current_select["options"].append(attrs)

        def handle_endtag(self, tag):
            if tag == "select":
                self.current_select = None

    parser = FormParser()
    parser.feed((PROTOTYPE_DIR / "index.html").read_text(encoding="utf-8"))
    card_type = next(item for item in parser.selects if item["attrs"].get("data-card") == "type")
    assert card_type["options"][0]["value"] == "式神"
    for select in parser.selects:
        selected = [index for index, option in enumerate(select["options"]) if "selected" in option]
        assert selected in ([], [0]), select["attrs"]
    for attrs in parser.inputs:
        input_type = attrs.get("type", "text")
        if input_type != "number":
            if input_type not in ("checkbox", "file", "hidden", "button"):
                assert attrs.get("value", "") == "", attrs
            continue
        if attrs.get("id") == "width":
            assert attrs.get("value", "") == ""
            continue
        maximum = float(attrs["max"]) if "max" in attrs else None
        minimum = float(attrs["min"]) if "min" in attrs else None
        expected = "-1" if maximum is not None and maximum <= 0 else "1" if minimum is not None and minimum > 0 else "0"
        assert attrs.get("value") == expected, attrs

    tutorial = (PROTOTYPE_DIR / "tutorial.js").read_text(encoding="utf-8")
    assert "tutorialNext.hidden = tutorialStep === TUTORIAL_STEPS.length - 1;" in tutorial


@pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")
def test_online_editor_text_and_export_helpers():
    script = r"""
const ui = require(process.argv[1]);
function equal(actual, expected, label) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${label}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`);
  }
}
equal(ui.insertText('abcdef', 2, 4, '[[贯通]]'),
      {value: 'ab[[贯通]]ef', cursor: 8}, '替换选区');
equal(ui.insertText('ab', 1, 1, '#ll'), {value: 'a#llb', cursor: 4}, '光标插入');
equal(ui.insertText('abcd', 99, 99, 'x'), {value: 'abcdx', cursor: 5}, '越界光标');
equal(ui.insertText('abcd', -2, 99, 'x'), {value: 'x', cursor: 1}, '异常选区');
equal(ui.pngFilename('  山风/测试:*?  '), '山风_测试___.png', '安全文件名');
equal(ui.pngFilename('   '), 'BWPDIY.png', '空文件名');
for (const ua of [
  'Mozilla/5.0 MicroMessenger/8.0.50',
  'Mozilla/5.0 MQQBrowser/14.0',
  'Mozilla/5.0 QQ/9.1.0',
  'Mozilla/5.0 Quark/7.0',
]) {
  if (!ui.isEmbeddedBrowser(ua)) throw new Error(`未识别内置浏览器：${ua}`);
}
for (const ua of [
  'Mozilla/5.0 Chrome/130.0.0.0 Safari/537.36',
  'Mozilla/5.0 (iPhone) Version/17.0 Mobile/15E148 Safari/604.1',
  '',
]) {
  if (ui.isEmbeddedBrowser(ua)) throw new Error(`误识别普通浏览器：${ua}`);
}
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(PROTOTYPE_DIR / "ui-utils.js")],
        capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr


def test_online_mobile_preview_and_save_dialog_structure():
    html = (PROTOTYPE_DIR / "index.html").read_text(encoding="utf-8")
    for element_id in ("c-preview-body", "b-preview-body", "export-modal",
                       "export-image", "export-bg-toggle", "export-download"):
        assert f'id="{element_id}"' in html
    assert html.count('class="preview-toggle"') == 2
    assert '<script src="ui-utils.js"></script>' in html
    sw = (PROTOTYPE_DIR / "sw.js").read_text(encoding="utf-8")
    assert '"/ui-utils.js"' in sw


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
        for path in ("/tutorial.js", "/tutorial.css", "/ui-utils.js"):
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
    server = PrototypeServer(("127.0.0.1", 0), handler, abuse_limit=100)
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


def test_abuse_limit_is_independent_from_valid_resource_requests():
    with serve_http(request_rate=1000, request_burst=1000, abuse_limit=3,
                    abuse_window=60, abuse_cooldown=300) as connection:
        statuses = []
        for index in range(3):
            connection.request("GET", f"/missing-{index}")
            response = connection.getresponse()
            statuses.append(response.status)
            response.read()
        assert statuses == [404, 404, 429]
        assert response.getheader("Retry-After") is not None
        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status == 200
        response.read()


def test_unsupported_methods_do_not_consume_valid_resource_quota():
    with serve_http(request_rate=0.001, request_burst=1, abuse_limit=2,
                    abuse_window=60, abuse_cooldown=300) as connection:
        connection.request("POST", "/")
        response = connection.getresponse()
        assert response.status == 405
        assert response.getheader("Allow") == "GET, HEAD"
        response.read()
        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status == 200
        response.read()
        connection.request("BREW", "/")
        response = connection.getresponse()
        assert response.status == 429
        response.read()


def test_forwarded_client_ip_is_used_only_when_explicitly_configured():
    with serve_http(request_rate=1000, request_burst=1000, abuse_limit=2,
                    abuse_window=60, abuse_cooldown=300,
                    client_ip_header="X-Forwarded-For") as connection:
        for client in ("198.51.100.1", "198.51.100.2"):
            connection.request("GET", "/missing", headers={"X-Forwarded-For": client})
            response = connection.getresponse()
            assert response.status == 404
            response.read()
        connection.request("GET", "/missing", headers={"X-Forwarded-For": "198.51.100.1"})
        response = connection.getresponse()
        assert response.status == 429
        response.read()


def test_forwarded_client_ip_is_ignored_by_default():
    with serve_http(request_rate=1000, request_burst=1000, abuse_limit=2,
                    abuse_window=60, abuse_cooldown=300) as connection:
        for client, expected in (("198.51.100.1", 404), ("198.51.100.2", 429)):
            connection.request("GET", "/missing", headers={"X-Forwarded-For": client})
            response = connection.getresponse()
            assert response.status == expected
            response.read()


def test_abuse_limiter_expires_and_bounds_state():
    from prototype.pyodide.server import AbuseRequestLimiter
    now = [0.0]
    limiter = AbuseRequestLimiter(limit=2, window=10, cooldown=300,
                                  max_clients=2, clock=lambda: now[0])
    assert limiter.allow("a") is None
    assert limiter.allow("a") == 300
    now[0] = 1
    assert limiter.allow("a") == 299
    now[0] = 301
    assert limiter.allow("a") is None
    now[0] = 302
    assert limiter.allow("b") is None
    now[0] = 303
    assert limiter.allow("c") is not None
    assert len(limiter.states) == 2
    now[0] = 400
    assert limiter.allow("c") is None


@pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")
def test_same_origin_resources_use_versioned_cache():
    script = r"""
const fs = require('fs');
const vm = require('vm');
const listeners = {};
const entries = new Map();
let networkRequests = 0;
const key = request => typeof request === 'string' ? request : request.url;
let holdCache = false;
let releaseCache = null;
const cache = {
  match: async request => entries.get(key(request)),
  put: async (request, response) => {
    if (holdCache) return new Promise(resolve => { releaseCache = resolve; });
    entries.set(key(request), response);
  },
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
  function makeEvent(request) {
    return {request, handled: false, pending: [], respondWith(promise) {
      this.handled = true; this.promise = promise;
    }, waitUntil(promise) { this.pending.push(promise); }};
  }
  async function dispatch(request) {
    const event = makeEvent(request);
    listeners.fetch(event);
    if (event.handled) {
      await event.promise;
      await Promise.all(event.pending);
    }
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
  holdCache = true;
  const event = makeEvent({method: 'GET', url: 'http://local/runtime-chunks/1'});
  listeners.fetch(event);
  let timer;
  try {
    await Promise.race([event.promise, new Promise((resolve, reject) => {
      timer = setTimeout(() => reject(new Error('响应被缓存完成阻塞')), 100);
    })]);
  } finally {
    releaseCache();
    clearTimeout(timer);
  }
  await event.promise;
  await Promise.all(event.pending);
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
    handler.server = SimpleNamespace(
        rate_limiter=SimpleNamespace(allow=lambda: True),
        abuse_limiter=SimpleNamespace(allow=lambda client: None), client_ip_header=None)
    handler.command = "GET"
    handler.client_address = ("127.0.0.1", 0)
    handler.path = "/missing"
    handler._send_empty = lambda status, **kwargs: None
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
  const status = messages.filter(item => item.type === 'progress').map(item => item.message).join('\n');
  for (const percent of ['33%', '66%', '100%']) {
    if (!status.includes(percent)) throw new Error(`缺少下载进度 ${percent}: ${status}`);
  }
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(PROTOTYPE_DIR / "worker.js")],
        capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")
def test_worker_reports_streaming_progress_within_each_chunk():
    script = r"""
const fs = require('fs');
const vm = require('vm');
const messages = [];
let now = 0;
const parts = [new Uint8Array(1024), new Uint8Array(2048), new Uint8Array(3072)];
const context = {
  URL, Uint8Array, setTimeout,
  performance: {now: () => { now += 100; return now; }},
  self: {postMessage: message => messages.push(message)},
  fetch: async url => {
    if (url === 'runtime.json') {
      return {ok: true, json: async () => ({size: 6144, chunk_size: 6144, chunks: 1})};
    }
    let index = 0;
    return {ok: true, body: {getReader: () => ({read: async () => index < parts.length
      ? {done: false, value: parts[index++]} : {done: true}})},
      arrayBuffer: async () => { throw new Error('流式下载不应回退'); }};
  },
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
(async () => {
  const bytes = await context.downloadRuntime();
  if (bytes.length !== 6144) throw new Error('流式分包大小错误');
  const progress = messages.filter(item => item.type === 'progress').map(item => item.message);
  for (const text of ['第 1/1 包 1.0 / 6.0 KiB', '第 1/1 包 3.0 / 6.0 KiB',
                      '第 1/1 包 6.0 / 6.0 KiB', '16%', '50%', '100%']) {
    if (!progress.some(message => message.includes(text))) {
      throw new Error(`缺少包内进度 ${text}: ${progress.join('\n')}`);
    }
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
