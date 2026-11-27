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
equal(ui.missingCharacters('山 风𪚥𪚥', new Set('山风')), ['𪚥'], '缺字去重');
equal(ui.missingCharacters('山风', '山风'), [], '字符清单');
equal(ui.precisionStep('offset_x', false), 5, '普通偏移步长');
equal(ui.precisionStep('offset_y', true), 1, '精细偏移步长');
equal(ui.precisionStep('scale', false), 0.05, '普通缩放步长');
equal(ui.precisionStep('scale', true), 0.01, '精细缩放步长');
equal(ui.precisionStep('rotate', true), 0.1, '精细旋转步长');
equal(ui.stepNumeric('1.05', 'scale', 1, true), 1.06, '缩放精调避免浮点误差');
equal(ui.stepNumeric('0.01', 'scale', -1, true), 0.01, '缩放不得小于下限');
equal(ui.stepNumeric('-2', 'offset_x', 1, false), 3, '偏移精调');
equal(ui.stepNumeric('0', 'rotate', -1, true), -0.1, '旋转精调');
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
                       "export-image", "export-bg-toggle", "export-download",
                       "c-fullscreen", "b-fullscreen", "gesture-lock",
                       "copy-diagnostics", "export-diagnostics"):
        assert f'id="{element_id}"' in html
    assert html.count('class="preview-toggle"') == 2
    assert 'id="fine-adjustment"' in html
    assert '<script src="ui-utils.js"></script>' in html
    css = (PROTOTYPE_DIR / "style.css").read_text(encoding="utf-8")
    assert ".mobile-only { display: inline-flex; align-items: center; justify-content: center; }" in css
    advanced_at = html.index('<details class="advanced-section">')
    for field in ("level", "rarity", "special_type", "faction"):
        assert 0 <= html.index(f'data-card="{field}"') < advanced_at
    sw = (PROTOTYPE_DIR / "sw.js").read_text(encoding="utf-8")
    assert '"/ui-utils.js"' in sw


@pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")
def test_mobile_keyboard_uses_current_focus_after_focusout_race():
    script = r"""
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('  function initializeKeyboardAvoidance()');
const end = source.indexOf('\n  function initialize()', start);
if (start < 0 || end < 0) throw new Error('找不到软键盘避让函数');
const viewportListeners = {};
const documentListeners = {};
const input = {matches: () => true, scrollIntoView: () => {}};
const panel = {classList: {contains: () => false}};
const viewport = {height: 844, addEventListener: (type, listener) => { viewportListeners[type] = listener; }};
let collapsed = false;
let exitedFullscreen = false;
const context = {
  window: {visualViewport: viewport},
  document: {activeElement: input, querySelector: () => panel,
    addEventListener: (type, listener) => { documentListeners[type] = listener; }},
  matchMedia: () => ({matches: true}),
  setTimeout: () => {},
  exitFullscreen: () => { exitedFullscreen = true; },
  setPreviewCollapsed: () => { collapsed = true; },
};
vm.createContext(context);
vm.runInContext(source.slice(start, end) + '\nthis.initializeKeyboard = initializeKeyboardAvoidance;', context);
context.initializeKeyboard();
documentListeners.focusin({target: input});
documentListeners.focusout();
viewport.height = 400;
viewportListeners.resize();
if (!collapsed || !exitedFullscreen) {
  throw new Error(`真实焦点仍在输入框时未避让：collapsed=${collapsed}, fullscreenExit=${exitedFullscreen}`);
}
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(PROTOTYPE_DIR / "mobile.js")],
        capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")
def test_online_library_backup_roundtrip_and_validation():
    script = r"""
const library = require(process.argv[1]);
function equal(actual, expected, label) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${label}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`);
  }
}
equal(library.workTitle({state: {tab: 'card', card: {name: ' 山风 '}}}), '山风', '卡牌标题');
equal(library.workTitle({state: {tab: 'mechanism', mechanism: {name: ''}}}), '未命名机制', '机制空标题');
const blank = library.blankDraft({tab: 'card', card: {name: '旧卡'}}, 'mechanism');
equal(blank.state.tab, 'mechanism', '新机制标签');
equal(blank.state.card.name, '旧卡', '空白表单模板不被深拷贝修改');
equal(blank.artwork, null, '新作品不带旧卡图');
const source = {schema: 2, current_id: 'old', layouts: {schema: 1, layouts: {}}, works: [{
  schema: 1, id: 'old', project: '项目', saved_at: '2026-11-26T00:00:00Z',
  state: {tab: 'card', card: {name: '测试'}},
  artwork: {name: 'a.png', path: 'artwork.png', bytes: new Uint8Array([1, 2, 3]).buffer},
}]};
const encoded = library.encodeBackup(source);
if (typeof encoded.works[0].artwork.bytes !== 'string') throw new Error('备份卡图未编码');
const decoded = library.decodeBackup(encoded);
equal([...new Uint8Array(decoded.works[0].artwork.bytes)], [1, 2, 3], '卡图字节往返');
equal(decoded.works[0].state.card.name, '测试', '作品内容往返');
if (!decoded.applyLayouts) throw new Error('完整卡库应允许恢复全局布局');
const single = library.decodeBackup({schema: 1, state: {tab: 'card'}, artwork: null});
if (single.applyLayouts || single.works.length !== 1) throw new Error('单作品备份不应覆盖全局布局');
for (const invalid of [null, {schema: 2, works: []}, {schema: 2, works: [{}]},
                       {schema: 1, state: null}, {schema: 3, works: []}]) {
  let rejected = false;
  try { library.decodeBackup(invalid); } catch (error) { rejected = true; }
  if (!rejected) throw new Error(`未拒绝异常备份 ${JSON.stringify(invalid)}`);
}
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(PROTOTYPE_DIR / "library.js")],
        capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr


def test_online_library_and_mobile_navigation_structure():
    html = (PROTOTYPE_DIR / "index.html").read_text(encoding="utf-8")
    for element_id in ("work-list", "new-card-work", "new-mechanism-work", "delete-work",
                       "project-name", "export-library", "mobile-workspace-nav"):
        assert f'id="{element_id}"' in html
    for target in ("library", "editor", "mechanism", "more"):
        assert f'data-mobile-target="{target}"' in html
    assert '<script src="library.js"></script>' in html


@pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")
def test_mobile_navigation_switches_instead_of_converting_work_type():
    script = r"""
const fs = require('fs');
const vm = require('vm');
const context = {console, structuredClone, btoa, atob, Uint8Array, ArrayBuffer, Date, Math, JSON, Object, String, Array,
  tutorialMode: false};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8') + '\nthis.selectKind = selectEditorKind;', context);
const navigation = {hidden: true};
context.document = {body: {dataset: {}}, querySelectorAll: () => [],
  getElementById: () => navigation};
context.matchMedia = () => ({matches: false});
context.activeMainTab = 'cards';
context.showMobileWorkspace('editor');
if (navigation.hidden) throw new Error('首次制作页未显示手机底部导航');
let tab = 'mechanism';
const calls = [];
context.readUiState = () => ({tab});
context.showMobileWorkspace = target => calls.push(['show', target]);
context.switchWork = async id => { calls.push(['switch', id]); tab = 'card'; };
context.createWork = async kind => { calls.push(['create', kind]); };
vm.runInContext("libraryIndex = {works: [{id: 'card-1', kind: 'card'}, {id: 'mech-1', kind: 'mechanism'}]};", context);
(async () => {
  await context.selectKind('card');
  if (JSON.stringify(calls) !== JSON.stringify([['switch', 'card-1']])) {
    throw new Error(`机制被原地转换或选择错误：${JSON.stringify(calls)}`);
  }
  calls.length = 0;
  await context.selectKind('card');
  if (JSON.stringify(calls) !== JSON.stringify([['show', 'editor']])) {
    throw new Error(`同类型不应重复切换：${JSON.stringify(calls)}`);
  }
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(PROTOTYPE_DIR / "library.js")],
        capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="node 不可用")
def test_online_library_storage_transactions():
    script = r"""
const values = new Map();
function finish(tx) {
  if (tx.pending || tx.done) return;
  tx.done = true;
  if (tx.oncomplete) tx.oncomplete();
}
function request(tx, action) {
  const result = {};
  tx.pending += 1;
  queueMicrotask(() => {
    try { result.result = action(); if (result.onsuccess) result.onsuccess(); }
    catch (error) { result.error = error; if (result.onerror) result.onerror(); }
    tx.pending -= 1;
    queueMicrotask(() => finish(tx));
  });
  return result;
}
const database = {transaction: () => {
  const tx = {pending: 0, done: false};
  tx.objectStore = () => ({
    get: key => request(tx, () => values.get(key)),
    put: (value, key) => request(tx, () => { values.set(key, value); }),
    delete: key => request(tx, () => { values.delete(key); }),
    getAllKeys: () => request(tx, () => [...values.keys()]),
  });
  return tx;
}};
global.indexedDB = {open: () => {
  const result = {};
  queueMicrotask(() => { result.result = database; result.onsuccess(); });
  return result;
}};
const store = require(process.argv[1]);
const draft = name => ({schema: 1, state: {tab: 'card', card: {name}}, artwork: null});
const meta = name => ({title: name, project: '项目', kind: 'card', saved_at: 'now'});
(async () => {
  await store.saveWork('a', draft('甲'), meta('甲'));
  await store.saveWork('b', draft('乙'), meta('乙'));
  const index = await store.listWorks();
  if (index.current_id !== 'b' || index.works.length !== 2) throw new Error('作品索引保存失败');
  if ((await store.loadWork('a')).state.card.name !== '甲') throw new Error('作品读取失败');
  await store.setCurrentWork('a');
  if ((await store.listWorks()).current_id !== 'a') throw new Error('当前作品切换失败');
  await store.deleteWork('a');
  if (await store.loadWork('a')) throw new Error('作品未删除');
  if ((await store.listWorks()).current_id !== 'b') throw new Error('删除后未回退到已有作品');
  await store.saveLayout({schema: 1, layouts: {}});
  await store.clearWorks();
  if ((await store.listWorks()).works.length || await store.loadWork('b')) throw new Error('卡库未清空');
  if (!(await store.loadLayout())) throw new Error('清空卡库误删全局布局');
})().catch(error => { console.error(error); process.exit(1); });
"""
    result = subprocess.run(
        [shutil.which("node"), "-e", script, str(PROTOTYPE_DIR / "storage.js")],
        capture_output=True, text=True, encoding="utf-8", timeout=10)
    assert result.returncode == 0, result.stderr


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


def test_online_font_archive_reduces_runtime_without_changing_font_paths():
    import json
    from PIL import ImageFont

    root = PROTOTYPE_DIR.parents[1]
    data = build_runtime_zip()
    runtime = ZipFile(BytesIO(data))
    with ZipFile(PROTOTYPE_DIR / "runtime-fonts.zip") as fonts:
        assert set(fonts.namelist()) == {"方正北魏楷书.ttf", "田氏颜体大字库2.0.ttf"}
        coverage = json.loads(runtime.read("font-coverage.json"))
        assert set(coverage) == set(fonts.namelist())
        for name in fonts.namelist():
            assert set("山风贯通，觉醒≥1。他们來對時開軍") <= set(coverage[name])
            packed = fonts.read(name)
            assert runtime.read(f"assets/fonts/{name}") == packed
            original_path = root / "assets" / "fonts" / name
            assert len(packed) < original_path.stat().st_size
            for size in (12, 24, 48):
                original = ImageFont.truetype(str(original_path), size)
                reduced = ImageFont.truetype(BytesIO(packed), size)
                for text in ("山风贯通，觉醒≥1。", "他们來對時開軍"):
                    original_mask, original_offset = original.getmask2(text)
                    reduced_mask, reduced_offset = reduced.getmask2(text)
                    assert original.getbbox(text) == reduced.getbbox(text)
                    assert original.getlength(text) == reduced.getlength(text)
                    assert original_offset == reduced_offset
                    assert bytes(original_mask) == bytes(reduced_mask)
    assert len(data) < 12 * 1024 * 1024


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
        for path in ("/tutorial.js", "/tutorial.css", "/ui-utils.js", "/mobile.js", "/library.js"):
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
  fetch: async (url, options) => {
    networkRequests += 1;
    if (!options || options.cache !== 'reload') throw new Error('缓存 miss 未绕过旧 HTTP 缓存');
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
def test_ui_cache_upgrade_preserves_runtime_downloads():
    script = r"""
const fs = require('fs');
const vm = require('vm');
const listeners = {};
const stores = new Map();
const store = name => {
  if (!stores.has(name)) stores.set(name, new Map());
  return stores.get(name);
};
const cache = name => ({
  match: async request => store(name).get(request),
  put: async (request, response) => store(name).set(request, response),
});
const context = {
  URL,
  self: {
    location: {origin: 'http://local'},
    clients: {claim: async () => {}},
    addEventListener: (type, listener) => { listeners[type] = listener; },
  },
  caches: {
    open: async name => cache(name),
    keys: async () => [...stores.keys()],
    delete: async name => stores.delete(name),
  },
  fetch: async () => ({ok: true, clone() { return this; }}),
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), context);
(async () => {
  const resourceCache = vm.runInContext('RESOURCE_CACHE', context);
  const runtimeCache = vm.runInContext('RUNTIME_CACHE', context);
  if (resourceCache === runtimeCache) throw new Error('界面与运行时仍共用缓存');
  async function dispatch(path) {
    const event = {request: {method: 'GET', url: 'http://local' + path}, pending: [],
      respondWith(promise) { this.promise = promise; },
      waitUntil(promise) { this.pending.push(promise); }};
    listeners.fetch(event);
    if (!event.promise) throw new Error(`未处理资源 ${path}`);
    await event.promise;
    await Promise.all(event.pending);
  }
  await dispatch('/app.js');
  await dispatch('/runtime.json');
  await dispatch('/runtime-chunks/0');
  if (!store(resourceCache).has('/app.js')) throw new Error('界面文件未进入界面缓存');
  for (const path of ['/runtime.json', '/runtime-chunks/0']) {
    if (!store(runtimeCache).has(path) || store(resourceCache).has(path)) {
      throw new Error(`运行时缓存分类错误：${path}`);
    }
  }
  stores.set('bwpdiy-online-resources-v13', new Map());
  const pending = [];
  listeners.activate({waitUntil: promise => pending.push(promise)});
  await Promise.all(pending);
  if (!stores.has(runtimeCache)) throw new Error('界面升级删除了运行时缓存');
  if (stores.has('bwpdiy-online-resources-v13')) throw new Error('旧界面缓存未清理');
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
