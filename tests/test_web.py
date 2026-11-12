"""web 层（FastAPI 编辑器后端）测试：布局读写 API 与样卡预览。"""

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bwpdiy.web.app import create_app

ASSETS = Path(__file__).resolve().parent.parent / "assets"


@pytest.fixture()
def assets_dir(web_assets_dir) -> Path:
    return web_assets_dir


@pytest.fixture()
def client(assets_dir):
    client = TestClient(create_app(assets_dir))
    config = Path.home() / ".bwpdiy" / "layout.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps(client.get("/api/layout").json()), encoding="utf-8")
    return client


def test_get_layout(client):
    r = client.get("/api/layout")
    assert r.status_code == 200
    assert "战斗" in r.json()


def test_editor_static_assets(client):
    """拆分后的 HTML 引用必须由真实服务提供，且不得遮蔽现有 API。"""
    for name in ("editor.css", "editor-core.js", "editor-cards.js", "editor-battle.js",
                 "editor-mech.js", "editor-layout.js", "editor-main.js"):
        r = client.get(f"/{name}")
        assert r.status_code == 200 and r.content
    assert client.get("/api/version").status_code == 200


def test_idle_activity_tracks_requests(client, monkeypatch):
    """空闲统计：普通请求刷新活动时间；/api/update/check（前端 1min 自动轮询）不刷新。"""
    from bwpdiy import updater
    monkeypatch.setattr(updater, "check_update",
                        lambda: {"current": "x", "frozen": False, "has_update": False})
    app = client.app
    client.get("/")
    t1 = app.state.last_activity
    client.get("/api/update/check")
    assert app.state.last_activity == t1
    client.get("/api/layout")
    assert app.state.last_activity >= t1


def test_idle_watchdog_fires(tmp_path):
    """看门狗：超过 idle_timeout 无操作触发 on_idle（默认实现为打印并退出进程）。"""
    import threading
    fired = threading.Event()
    create_app(ASSETS, library_dir=tmp_path / "library", idle_timeout=0.1,
               on_idle=fired.set)
    assert fired.wait(3)


def test_manual_shutdown(assets_dir, tmp_path, caplog):
    """手动退出按钮：响应成功、调用退出回调，并以 INFO 记录明确原因。"""
    import logging
    called = []
    client = TestClient(create_app(
        assets_dir, library_dir=tmp_path / "library", on_shutdown=lambda: called.append(True)))
    with caplog.at_level(logging.INFO):
        r = client.post("/api/shutdown")
    assert r.status_code == 200 and r.json()["ok"]
    assert called == [True]
    assert any(rec.name == "bwpdiy.web" and rec.getMessage() == "手动按钮关闭"
               for rec in caplog.records)


def test_host_guard(client):
    """Host 校验（防 DNS rebinding）：非回环 Host 一律 400；回环/testserver 放行。"""
    assert client.get("/api/layout", headers={"host": "evil.example.com"}).status_code == 400
    assert client.get("/api/layout", headers={"host": "attacker.com:8630"}).status_code == 400
    for ok in ("127.0.0.1:8630", "localhost:8630", "[::1]:8630", "testserver"):
        assert client.get("/api/version", headers={"host": ok}).status_code == 200


def test_cross_site_write_is_rejected(client):
    """Host 正确也不能替代 CSRF 防护：浏览器跨站写操作一律 403。"""
    r = client.post("/api/update/apply", headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 403 and "跨站" in r.json()["detail"]


def test_layout_rejects_nonfinite_numbers(client):
    import json
    layouts = client.get("/api/layout").json()
    layouts["战斗"]["elements"]["name"]["pos"][0] = float("nan")
    r = client.put("/api/layout", content=json.dumps(layouts),
                   headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_version_carries_changelog(client):
    """/api/version 附带当前版本更新说明（「最近更新」弹窗数据源）与本次启动 boot_id。"""
    from bwpdiy import __version__
    from bwpdiy.changelog import CHANGELOG
    data = client.get("/api/version").json()
    assert data["version"] == __version__
    assert isinstance(data["boot_id"], int)
    assert data["notes"] == CHANGELOG.get(__version__, [])
    assert CHANGELOG.get(__version__), "当前版本必须在 changelog.py 登记更新说明"


def test_client_debug_log_and_write_operation_log(client, caplog):
    """GUI 事件与本地写操作均落 DEBUG；控制字符不得伪造额外日志行。"""
    import logging
    with caplog.at_level(logging.DEBUG):
        r = client.post("/api/client-log", json={
            "event": "button.click", "detail": "保存\n伪造级别"})
        assert r.status_code == 200 and r.json()["ok"]
        client.put("/api/layout", json=client.get("/api/layout").json())
    gui = next(rec for rec in caplog.records if rec.name == "bwpdiy.gui")
    assert gui.levelno == logging.DEBUG
    assert gui.getMessage() == "button.click | 保存 伪造级别"
    assert any(rec.name == "bwpdiy.web" and "本地写操作 PUT /api/layout -> HTTP 200"
               in rec.getMessage() for rec in caplog.records)


@pytest.mark.parametrize("body", [
    {}, {"event": "bad event"}, {"event": "x" * 81},
    {"event": "button.click", "detail": 1},
    {"event": "button.click", "detail": "x" * 501},
])
def test_client_debug_log_rejects_invalid_payload(client, body):
    assert client.post("/api/client-log", json=body).status_code == 422


def test_preview_rejects_artwork_path_escape(client):
    """预览接口的卡图路径不得越出基准目录（绝对路径/.. 一律 422）。"""
    body = {"type": "式神", "layout": client.get("/api/layout").json()["式神"]}
    for bad in ("/etc/passwd.png", "C:/Windows/x.png", "../escape.png"):
        b = dict(body, card={"artwork": {"images": [{"path": bad}]}})
        r = client.post("/api/preview", json=b)
        assert r.status_code == 422 and "越出基准目录" in r.json()["detail"]


def test_put_layout_roundtrip(client, assets_dir, tmp_path):
    r = client.get("/api/layout")
    layouts = r.json()
    layouts["战斗"]["elements"]["rarity"]["pos"] = [200, 200]
    r = client.put("/api/layout", json=layouts)
    assert r.status_code == 200 and r.json()["ok"]
    assert client.get("/api/layout").json()["战斗"]["elements"]["rarity"]["pos"] == [200, 200]
    # 写盘字节格式：UTF-8 未转义中文 + indent=2 风格
    raw = (Path.home() / ".bwpdiy" / "layout.json").read_text(encoding="utf-8")
    assert '"战斗"' in raw and "\\u" not in raw
    assert '\n  "战斗"' in raw


def test_frozen_put_layout_writes_home_not_packaged_assets(assets_dir, tmp_path, monkeypatch):
    from bwpdiy import resources

    home = tmp_path / "home"
    monkeypatch.setattr(resources, "is_frozen", lambda: True)
    monkeypatch.setattr(resources.Path, "home", lambda: home)
    client = TestClient(create_app(assets_dir, library_dir=tmp_path / "library"))
    layouts = client.get("/api/layout").json()
    layouts["战斗"]["elements"]["name"]["pos"] = [9, 10]

    assert client.put("/api/layout", json=layouts).status_code == 200
    config = home / ".bwpdiy" / "layout.json"
    assert config.is_file()
    assert client.get("/api/layout").json()["战斗"]["elements"]["name"]["pos"] == [9, 10]
    assert not (assets_dir / "layout.json").exists()


def test_put_layout_frame_variant_sparse_roundtrip(client, assets_dir):
    import json

    layouts = client.get("/api/layout").json()
    base = {key: layouts["战斗"][key] for key in ("elements", "text_regions")}
    sparse = {"elements": {"name": {"pos": [12, 34]}}}
    assert client.put("/api/layout", json={
        "战斗": {**base, "frame_variants": {"black": sparse}},
    }).status_code == 200

    loaded = client.get("/api/layout").json()
    assert loaded["战斗"]["elements"]["name"]["pos"] != [12, 34]
    assert loaded["战斗"]["frame_variants"]["black"]["elements"]["name"]["pos"] == [12, 34]
    assert loaded["战斗"]["frame_variants"]["blue"] == base
    raw = json.loads((Path.home() / ".bwpdiy" / "layout.json").read_text(encoding="utf-8"))
    assert raw["战斗"]["frame_variants"] == {"black": sparse}


@pytest.mark.parametrize("card_type,variants", [
    ("战斗", []),
    ("战斗", {"gold": {}}),
    ("协战", {"gold": {}}),
    ("战斗", {"black": {"elements": []}}),
])
def test_put_layout_rejects_invalid_frame_variants(client, assets_dir, card_type, variants):
    layouts = client.get("/api/layout").json()
    base = {key: layouts[card_type][key] for key in ("elements", "text_regions")}
    before = (Path.home() / ".bwpdiy" / "layout.json").read_bytes()
    response = client.put("/api/layout", json={
        card_type: {**base, "frame_variants": variants},
    })
    assert response.status_code == 422
    assert (Path.home() / ".bwpdiy" / "layout.json").read_bytes() == before


def test_put_layout_partial_types(client, assets_dir):
    """允许只保存部分类型；独立段缺失时 load_layouts 从包内默认补齐。"""
    r = client.put("/api/layout", json={"战斗": client.get("/api/layout").json()["战斗"]})
    assert r.status_code == 200 and r.json()["ok"]
    assert list(client.get("/api/layout").json()) == ["战斗", "对局式神", "机制"]


def test_put_layout_entity_section(client, assets_dir):
    layouts = client.get("/api/layout").json()
    entity = layouts["对局式神"]
    assert set(entity) == {"version", "art_window", "elements"}
    assert entity["version"] == 2
    entity["elements"]["level"]["pos"] = [30, 88]
    entity["art_window"]["offset_y"] = 2
    assert client.put("/api/layout", json={"对局式神": entity}).status_code == 200
    assert client.get("/api/layout").json()["对局式神"] == entity
    before = (Path.home() / ".bwpdiy" / "layout.json").read_bytes()
    assert client.put("/api/layout", json={"对局式神": {"elements": []}}).status_code == 422
    assert (Path.home() / ".bwpdiy" / "layout.json").read_bytes() == before


@pytest.mark.parametrize("patch", [
    {"version": 1}, {"version": 2.0}, {"version": True}, {"art_window": []},
    {"art_window": {"center": [48], "width": 84, "height": 132,
                    "frame_center": True, "offset_y": 0}},
    {"art_window": {"center": [48, 72], "width": 0, "height": 132,
                    "frame_center": True, "offset_y": 0}},
    {"art_window": {"center": [48, 72], "width": 8001, "height": 8000,
                    "frame_center": True, "offset_y": 0}},
    {"art_window": {"center": [48, 72], "width": 8000.50001, "height": 7999.5,
                    "frame_center": True, "offset_y": 0}},
    {"art_window": {"center": [48, 72], "width": 84, "height": 132,
                    "frame_center": 1, "offset_y": 0}},
    {"art_window": {"center": [48, 72], "width": 84, "height": 132,
                    "frame_center": True, "offset_y": "2"}},
])
def test_put_layout_rejects_invalid_entity_window(client, assets_dir, patch):
    entity = client.get("/api/layout").json()["对局式神"]
    entity.update(patch)
    before = (Path.home() / ".bwpdiy" / "layout.json").read_bytes()
    response = client.put("/api/layout", json={"对局式神": entity})
    assert response.status_code == 422
    assert (Path.home() / ".bwpdiy" / "layout.json").read_bytes() == before


@pytest.mark.parametrize("element", ["energy", "countdown", "defeated"])
def test_put_layout_rejects_invalid_counter_font_size(client, element):
    entity = client.get("/api/layout").json()["对局式神"]
    entity["elements"][element]["font_size"] = 0
    before = (Path.home() / ".bwpdiy" / "layout.json").read_bytes()
    response = client.put("/api/layout", json={"对局式神": entity})
    assert response.status_code == 422
    assert "font_size" in response.json()["detail"]
    assert (Path.home() / ".bwpdiy" / "layout.json").read_bytes() == before


def test_put_layout_mech_section(client, assets_dir):
    """「机制」段为扁平参数映射（无 elements/text_regions），可保存并回读。"""
    layouts = client.get("/api/layout").json()
    assert "机制" in layouts  # 缺段时 load_layouts 已补齐包内默认
    layouts["机制"]["text_size"] = 28
    assert client.put("/api/layout", json=layouts).status_code == 200
    assert client.get("/api/layout").json()["机制"]["text_size"] == 28
    # 机制段形状非法（非对象）拒绝且不动文件
    before = (Path.home() / ".bwpdiy" / "layout.json").read_bytes()
    r = client.put("/api/layout", json={"机制": "不是对象"})
    assert r.status_code == 422
    assert (Path.home() / ".bwpdiy" / "layout.json").read_bytes() == before


def test_mech_layout_preview(client):
    """布局设置「机制」页预览端点：三框逐次渲染 PNG；badge 仅 seal 保留不报错；
    layout 可显式覆盖，缺省用已保存「机制」段。"""
    for frame in ("invocation", "skill", "seal"):
        r = client.post("/api/mech-preview", json={
            "frame": frame,
            "mechanism": {"name": "示例", "text": "获得[[迅捷]]。", "badge": "bless"},
            "layout": {"text_size": 24},
        })
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
        # 实际文本块矩形随响应头返回（GUI 浅绿轮廓数据源）：4 个整数、宽高为正
        rect = [int(v) for v in r.headers["x-text-rect"].split(",")]
        assert len(rect) == 4 and rect[2] > 0 and rect[3] > 0
    # 缺省 mechanism/layout 也能渲染（内置示例 + 已保存机制段）
    r = client.post("/api/mech-preview", json={"frame": "skill"})
    assert r.status_code == 200
    assert client.post("/api/mech-preview", json={"frame": "unknown"}).status_code == 400
    r = client.post("/api/mech-preview", json={"frame": "skill", "layout": "bad"})
    assert r.status_code == 400


def test_entity_layout_preview(client):
    body = {
        "card": {"type": "形态", "name": "样例"},
        "state": {"level": 3, "level_color": "cyan", "power": 2,
                  "health": 5, "combat_power": -1, "shield": 4},
    }
    response = client.post("/api/entity-preview", json=body)
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert "x-crop-offset" in response.headers
    entity_layout = client.get("/api/layout").json()["对局式神"]
    assert client.post("/api/entity-preview",
                       json={**body, "layout": entity_layout}).status_code == 200
    assert client.post("/api/entity-preview",
                       json={**body, "layout": "bad"}).status_code == 422


def test_entity_preview_native_size_parameters(client):
    from io import BytesIO
    from PIL import Image

    body = {
        "card": {"type": "式神", "name": "尺寸样例"},
        "state": {"level": 2, "power": 12, "health": 34},
    }
    baseline = client.post("/api/entity-preview", json=body)
    assert baseline.status_code == 200
    base_size = Image.open(BytesIO(baseline.content)).size
    expected = (base_size[0] * 2, base_size[1] * 2)
    for size in ({"width": expected[0]},
                 {"width": expected[0], "height": expected[1]}):
        response = client.post("/api/entity-preview", json={**body, **size})
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert Image.open(BytesIO(response.content)).size == expected


@pytest.mark.parametrize("size", [
    {"width": 0},
    {"height": -1},
    {"width": "200"},
    {"width": 200, "height": 100},
])
def test_entity_preview_rejects_invalid_native_size(client, size):
    body = {
        "card": {"type": "式神", "name": "尺寸样例"},
        "state": {"level": 2, "power": 12, "health": 34},
        **size,
    }
    response = client.post("/api/entity-preview", json=body)
    assert response.status_code == 422
    assert "渲染失败" in response.json()["detail"]


def test_entity_layout_preview_forces_packaged_sample_art(client, tmp_path):
    from PIL import Image
    outside = tmp_path / "outside.png"
    Image.new("RGB", (32, 32), "red").save(outside)
    body = {"card": {"type": "式神", "name": "样例"}, "state": {}}
    baseline = client.post("/api/entity-preview", json=body)
    hostile = {
        "card": {"type": "式神", "name": "样例", "_base_dir": str(tmp_path),
                 "_private": "discard",
                 "artwork": {"images": [{"path": str(outside.resolve())}]}},
        "state": {},
    }
    response = client.post("/api/entity-preview", json=hostile)
    assert response.status_code == 200
    assert response.content == baseline.content


def test_put_layout_backup(client, assets_dir):
    """二次 PUT 前旧文件留 layout.json.bak。"""
    layouts = client.get("/api/layout").json()
    assert client.put("/api/layout", json=layouts).status_code == 200
    bak = Path.home() / ".bwpdiy" / "layout.json.bak"
    assert bak.is_file()
    assert not (Path.home() / ".bwpdiy" / "layout.json.tmp").exists()


@pytest.mark.parametrize("bad", [
    {},  # 空布局视同误操作
    {"战斗": "不是对象"},
    {"战斗": {"elements": {}}},  # 缺 text_regions
    {"战斗": {"text_regions": {}}},  # 缺 elements
])
def test_put_layout_invalid_shape(client, assets_dir, bad):
    before = (Path.home() / ".bwpdiy" / "layout.json").read_bytes()
    r = client.put("/api/layout", json=bad)
    assert r.status_code == 422
    assert (Path.home() / ".bwpdiy" / "layout.json").read_bytes() == before  # 校验失败不得动文件


def test_preview_png(client):
    from bwpdiy.render.layout import load_layouts, get_type_layout
    tl = get_type_layout(load_layouts(client.app.state.assets_dir), "战斗")
    r = client.post("/api/preview", json={"type": "战斗", "layout": tl})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert len(r.content) > 10000
    # 紧致裁剪原尺寸（无 512 画布留白）+ 裁剪原点响应头（卡面空间，与布局坐标同系；
    # 探出框左缘元素时 ox 可为负；布局页覆盖层据此换算）
    from io import BytesIO
    from PIL import Image
    img = Image.open(BytesIO(r.content))
    assert 511 <= img.height <= 512 and img.width < 512
    ox, oy = (int(v) for v in r.headers["x-crop-offset"].split(","))
    assert oy >= 0 and oy + img.height <= 512 and ox + img.width <= 512


@pytest.mark.parametrize("card_type", ["式神", "战斗", "法术", "形态", "幻境", "协战"])
def test_preview_all_types(client, card_type):
    from bwpdiy.render.layout import load_layouts, get_type_layout
    tl = get_type_layout(load_layouts(client.app.state.assets_dir), card_type)
    r = client.post("/api/preview", json={"type": card_type, "layout": tl})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    from io import BytesIO
    from PIL import Image
    img = Image.open(BytesIO(r.content))
    assert 511 <= img.height <= 512 and img.width < 512
    assert r.headers["x-crop-offset"].count(",") == 1


def test_preview_bad_type(client):
    r = client.post("/api/preview", json={"type": "不存在", "layout": {"elements": {}, "text_regions": {}}})
    assert r.status_code == 400


def _battle_layout(client):
    from bwpdiy.render.layout import load_layouts, get_type_layout
    return get_type_layout(load_layouts(client.app.state.assets_dir), "战斗")


def test_preview_card_override(client):
    """body.card 覆盖样卡指定字段：嵌套 artwork 不丢、样卡全局不被污染。"""
    tl = _battle_layout(client)
    base = client.post("/api/preview", json={"type": "战斗", "layout": tl})
    assert base.status_code == 200
    r = client.post("/api/preview", json={
        "type": "战斗", "layout": tl,
        "card": {"name": "测试异名", "shield+": -2, "description": "改后的描述文本。"}})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content != base.content  # 覆盖生效
    again = client.post("/api/preview", json={"type": "战斗", "layout": tl})
    assert again.content == base.content  # SAMPLE_CARDS 未被污染（artwork 深拷贝）


def test_preview_card_override_artwork_merge(client):
    """覆盖 artwork 子键时与其余 artwork 键合并而非整体替换。"""
    tl = _battle_layout(client)
    r = client.post("/api/preview", json={
        "type": "战斗", "layout": tl, "card": {"artwork": {"offset_x": 20}}})
    assert r.status_code == 200  # images 列表仍在，渲染不丢卡图


def test_preview_card_override_invalid(client):
    tl = _battle_layout(client)
    r = client.post("/api/preview", json={"type": "战斗", "layout": tl, "card": "不是对象"})
    assert r.status_code == 400


def test_preview_frame_variant_passthrough(client):
    """预览请求 card 覆盖的 frame_variant 无白名单过滤、透传渲染（样卡本身不携带该字段）。"""
    tl = _battle_layout(client)
    r = client.post("/api/preview", json={
        "type": "战斗", "layout": tl, "card": {"frame_variant": "blue"}})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    base = client.post("/api/preview", json={"type": "战斗", "layout": tl})
    assert base.status_code == 200  # 覆盖不污染样卡（SAMPLE_CARDS 深拷贝）


def test_samples_api(client):
    """GET /api/samples：六类型样卡字段（剥内部键），供 GUI 内容输入框预填。"""
    r = client.get("/api/samples")
    assert r.status_code == 200
    samples = r.json()
    assert set(samples) == {"式神", "战斗", "法术", "形态", "幻境", "协战"}
    battle = samples["战斗"]
    assert battle["name"] == "义道" and battle["shield+"] == 2
    assert "_base_dir" not in battle and "artwork" not in battle


def test_help_button_and_modal():
    """中央区「使用说明」按钮在「强制刷新」左边；弹窗含基础功能说明要点。"""
    html = EDITOR_HTML.read_text(encoding="utf-8")
    assert html.index('id="c-btn-help"') < html.index('id="c-btn-refresh"')
    modal = html.split('id="help-modal"', 1)[1]
    for needle in ("[[关键字]]", "#ll", "八分之一宽空格", "扩展选项", "自适应",
                   "项目、主要式神与卡牌/衍生物均按 ID 升序排列"):
        assert needle in modal
    assert "协战仅常规" not in modal


# --- 编辑器静态 JS 纯函数测试（node 驱动：抽取函数源码 + 桩驱动运行） ---
# 布局设置 tab 自 layout.html 迁入 editor.html，被测函数名保持不变

NODE = shutil.which("node")
EDITOR_HTML = Path(__file__).resolve().parent.parent / "bwpdiy" / "web" / "static" / "editor.html"


def _script() -> str:
    html = EDITOR_HTML.read_text(encoding="utf-8")
    scripts = []
    for chunk in html.split('<script src="')[1:]:
        src = chunk.split('"', 1)[0]
        scripts.append((EDITOR_HTML.parent / src).read_text(encoding="utf-8"))
    assert scripts, "editor.html 必须按依赖顺序引用静态脚本"
    return "\n".join(scripts)


def _extract_js(script: str, decl: str) -> str:
    """按花括号配对从内嵌脚本中抽取一个声明（函数/const 对象字面量）。"""
    start = script.index(decl)
    brace = script.index(") {", start) + 2 if decl.startswith("function ") \
        else script.index("{", start)
    depth = 0
    for i in range(brace, len(script)):
        if script[i] == "{":
            depth += 1
        elif script[i] == "}":
            depth -= 1
            if depth == 0:
                return script[start:i + 1]
    raise AssertionError(f"{decl} 花括号不配对")


def _run_node(tmp_path, driver: str):
    import subprocess
    src = tmp_path / "driver.js"
    src.write_text(driver, encoding="utf-8")
    r = subprocess.run([NODE, str(src)], capture_output=True, text=True,
                       encoding="utf-8")  # node 输出 UTF-8；默认 locale(GBK) 解码中文会炸
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_mech_chars_per_line_js_validation(tmp_path):
    validate = _extract_js(_script(), "function validateMechJS(d)")
    driver = f"""
const assert = require('node:assert');
const MECH_FRAMES = [['invocation', '灵咒'], ['skill', '关键字'], ['seal', '加护蚀印']];
const MECH_BADGES = [['', '无'], ['bless', '加护'], ['eclipse', '蚀印']];
{validate}
const base = {{name: '示例', frame: 'skill', text: '', chars_per_line: 12}};
assert.deepStrictEqual(validateMechJS(base), []);
for (const value of [0, -1, 1.5, true, '12']) {{
  assert(validateMechJS({{...base, chars_per_line: value}}).some(e => e.includes('chars_per_line')));
}}
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_inline_faction_js_validation(tmp_path):
    script = _script()
    end = script.index(";", script.index("const STAT_VALUE_COLOR_VALUES =")) + 1
    consts = script[script.index("const TYPES ="):end]
    validate_card = _extract_js(script, "function validateCardJS(d)")
    validate_mech = _extract_js(script, "function validateMechJS(d)")
    driver = f"""
const assert = require('node:assert');
{consts}
const MECH_FRAMES = [['invocation', '灵咒'], ['skill', '关键字'], ['seal', '加护蚀印']];
const MECH_BADGES = [['', '无'], ['bless', '加护'], ['eclipse', '蚀印']];
function validDateStr() {{ return true; }}
{validate_card}
{validate_mech}
const card = {{type: '战斗', name: '斩', level: 1, rarity: 'R', shikigami: '山风',
              'power+': 1, 'shield+': 1, description: '#hl'}};
const mech = {{name: '示例', frame: 'skill', text: '#hl'}};
for (const style of [1, 2, 3]) {{
  assert.deepStrictEqual(validateCardJS({{...card, inline_faction_style: style}}), []);
  assert.deepStrictEqual(validateMechJS({{...mech, inline_faction_style: style}}), []);
}}
for (const style of [0, 4, true, 1.5, '1']) {{
  assert(validateCardJS({{...card, inline_faction_style: style}}).some(e => e.includes('inline_faction_style')));
  assert(validateMechJS({{...mech, inline_faction_style: style}}).some(e => e.includes('inline_faction_style')));
}}
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_inline_faction_controls_follow_marker_for_card_and_mechanism(tmp_path):
    script = _script()
    build_card = _extract_js(script, "function buildForm()")
    build_mech = _extract_js(script, "function buildMechForm()")
    driver = f"""
const assert = require('node:assert');
let activeAsk = null, cDirty = false, mDirty = false, curCard = null;
let formData = {{type: '法术', name: '测试', level: 1, rarity: 'R', shikigami: '山风',
                description: '#hl', inline_faction_style: 3}};
let mechForm = {{name: '示例', frame: 'skill', text: '#hl', inline_faction_style: 3}};
const extOptions = {{marker: false, layout: false}};
const labels = [];
function element(tag) {{ return {{tag, children: [], style: {{}}, textContent: '', value: '',
  set innerHTML(value) {{ if (value === '') this.children = []; }},
  appendChild(child) {{ this.children.push(child); return child; }} }}; }}
const div = element('div');
const document = {{getElementById: () => div, createElement: element}};
function syncCardFrameButtons() {{}}
function infoRow() {{}}
function textRow() {{}}
function versionRows() {{}}
function levelRow() {{}}
function shikigamiRow() {{}}
function checkRowC() {{}}
function numRowC() {{}}
function artRow() {{}}
function isMainShikigami() {{ return false; }}
function rarityOptions() {{ return ['R']; }}
function selRowC(div, label, opts, val, set) {{ labels.push({{label, val, set}}); }}
function showFormErrors() {{}}
function validateCardJS() {{ return []; }}
function validateMechJS() {{ return []; }}
function afterEdit() {{}}
function afterMechEdit() {{}}
function undoAll() {{}}
function undoLast() {{}}
function saveCard() {{}}
function openExport() {{}}
function saveMech() {{}}
function exportMech() {{}}
const MECH_FRAMES = [['invocation', '灵咒'], ['skill', '关键字'], ['seal', '加护蚀印']];
const MECH_BADGES = [['', '无'], ['bless', '加护'], ['eclipse', '蚀印']];
const EVOLVE_TYPES = new Set(['战斗', '法术', '形态', '幻境']);
const NONNEG_TYPES = new Set(['式神', '形态', '幻境']);
const STATS_BY_TYPE = {{法术: ['power+', 'health+']}};
const STAT_MATRIX = {{法术: {{'power+': '力量+', 'health+': '生命+'}}}};
{build_card}
{build_mech}
function inlineControl() {{ return labels.find(row => row.label === '内嵌派系样式'); }}
buildForm();
assert.strictEqual(inlineControl(), undefined);
assert.strictEqual(formData.inline_faction_style, 3);
buildMechForm();
assert.strictEqual(inlineControl(), undefined);
assert.strictEqual(mechForm.inline_faction_style, 3);
extOptions.marker = true;
labels.length = 0;
buildForm();
assert.strictEqual(inlineControl().val, '3');
inlineControl().set('1');
assert.strictEqual(formData.inline_faction_style, undefined);
inlineControl().set('2');
assert.strictEqual(formData.inline_faction_style, 2);
labels.length = 0;
buildMechForm();
assert.strictEqual(inlineControl().val, '3');
inlineControl().set('1');
assert.strictEqual(mechForm.inline_faction_style, undefined);
inlineControl().set('2');
assert.strictEqual(mechForm.inline_faction_style, 2);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_text_layout_js_validation(tmp_path):
    """前端若漏掉白名单会无法保存；漏掉枚举校验会把非法模式发往服务端。"""
    script = _script()
    end = script.index(";", script.index("const STAT_VALUE_COLOR_VALUES =")) + 1
    consts = script[script.index("const TYPES ="):end]
    validate = _extract_js(script, "function validateCardJS(d)")
    driver = f"""
const assert = require('node:assert');
{consts}
function validDateStr() {{ return true; }}
{validate}
const card = {{type: '战斗', name: '斩', level: 1, rarity: 'R', shikigami: '山风',
              'power+': 1, 'shield+': 1, description: '贯通。'}};
for (const mode of ['smart', 'wrap', 'off']) {{
  assert.deepStrictEqual(validateCardJS({{...card, text_layout: mode}}), []);
}}
for (const mode of ['auto', false, 1, null]) {{
  assert(validateCardJS({{...card, text_layout: mode}}).some(e => e.includes('text_layout')));
}}
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_text_layout_control_follows_marker_and_preserves_value(tmp_path):
    """扩展控件若重建表单时丢值或错误删值，会改变用户未保存的排版选择。"""
    build_card = _extract_js(_script(), "function buildForm()")
    driver = f"""
const assert = require('node:assert');
let activeAsk = null, cDirty = false;
let formData = {{type: '法术', name: '测试', level: 1, rarity: 'R', shikigami: '山风',
                description: '贯通。', text_layout: 'off'}};
const extOptions = {{marker: false, layout: false}};
const controls = [], events = [];
function element(tag) {{ return {{tag, children: [], style: {{}}, textContent: '', value: '',
  set innerHTML(value) {{ if (value === '') this.children = []; }},
  appendChild(child) {{ this.children.push(child); return child; }} }}; }}
const div = element('div');
const document = {{getElementById: () => div, createElement: tag => {{
  if (tag === 'textarea') events.push('description');
  return element(tag);
}}}};
function syncCardFrameButtons() {{}}
function infoRow() {{}}
function textRow() {{}}
function versionRows() {{}}
function levelRow() {{}}
function shikigamiRow() {{}}
function checkRowC() {{}}
function numRowC() {{}}
function artRow() {{}}
function isMainShikigami() {{ return false; }}
function rarityOptions() {{ return ['R']; }}
function selRowC(div, label, opts, val, set) {{
  controls.push({{label, opts, val, set}}); events.push(label);
}}
function showFormErrors() {{}}
function validateCardJS() {{ return []; }}
function afterEdit() {{}}
function undoAll() {{}}
function undoLast() {{}}
function saveCard() {{}}
function openExport() {{}}
const EVOLVE_TYPES = new Set(['战斗', '法术', '形态', '幻境']);
const NONNEG_TYPES = new Set(['式神', '形态', '幻境']);
const STATS_BY_TYPE = {{法术: ['power+', 'health+']}};
const STAT_MATRIX = {{法术: {{'power+': '力量+', 'health+': '生命+'}}}};
{build_card}
function layoutControl() {{ return controls.find(row => row.label === '自动排版'); }}
buildForm();
assert.strictEqual(layoutControl(), undefined);
assert.strictEqual(formData.text_layout, 'off');
extOptions.marker = true;
controls.length = 0; events.length = 0;
buildForm();
assert.deepStrictEqual(layoutControl().opts, ['smart', 'wrap', 'off']);
assert.strictEqual(layoutControl().val, 'off');
assert(events.indexOf('自动排版') < events.indexOf('description'));
layoutControl().set('smart');
assert.strictEqual(formData.text_layout, undefined);
layoutControl().set('wrap');
assert.strictEqual(formData.text_layout, 'wrap');
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_inline_faction_marker_toggle_rebuilds_card_and_mechanism(tmp_path):
    apply = _extract_js(_script(), "function applyExtOptions()")
    driver = f"""
const assert = require('node:assert');
const extOptions = {{layout: true, marker: false}};
let cardLayoutMode = false, formData = {{}}, mechForm = {{}};
let cardBuilds = 0, mechBuilds = 0;
const elements = {{
  'ext-layout': {{checked: false}}, 'ext-marker': {{checked: false}},
  'tab-layout': {{classList: {{contains: () => false}}}},
  'tab-battle': {{classList: {{contains: () => false}}}},
}};
const document = {{
  getElementById: id => elements[id],
  querySelector: () => ({{style: {{}}}}),
}};
function saveExtOptions() {{}}
function showTab() {{}}
function exitCardLayout() {{}}
function buildForm() {{ cardBuilds++; }}
function buildMechForm() {{ mechBuilds++; }}
function cPreviewPortrait() {{}}
{apply}
applyExtOptions();
assert.strictEqual(cardBuilds, 1);
assert.strictEqual(mechBuilds, 1);
formData = null;
applyExtOptions();
assert.strictEqual(cardBuilds, 1);
assert.strictEqual(mechBuilds, 2);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_derived_shikigami_skeleton_keeps_owner(tmp_path):
    """式神骨架有所属式神时保留引用，不能在提前返回时丢弃。"""
    skeleton = _extract_js(_script(), "function skeleton(type, name, shiki = {})")
    driver = f"""
const assert = require('node:assert');
{skeleton}
assert.deepStrictEqual(skeleton('式神', '召唤物', {{shikigami: '基础式神'}}),
  {{type: '式神', name: '召唤物', shikigami: '基础式神',
    faction: '红莲', power: 3, health: 4, description: ''}});
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_derived_shikigami_skips_portrait_preview(tmp_path):
    """衍生物式神不显示头像预览也不发请求；主要式神仍符合头像预览条件。"""
    script = _script()
    eligible = _extract_js(script, "function isMainShikigami(card)")
    preview = _extract_js(script, "async function cPreviewPortrait(withForm)")
    driver = f"""
const assert = require('node:assert');
let curProject = 'P', curCard = 'C';
let formData = {{type: '式神', shikigami: '基础'}};
let cPortraitSeq = 0, cPortraitAppliedSeq = 0;
const cPortraitImg = {{style: {{display: 'block'}}}};
let syncs = 0;
function syncSubpreviews() {{ syncs++; }}
function fetch() {{ throw new Error('衍生物不得请求头像预览'); }}
{eligible}
{preview}
(async () => {{
  assert.strictEqual(isMainShikigami(formData), false);
  assert.strictEqual(isMainShikigami({{type: '式神'}}), true);
  await cPreviewPortrait(true);
  assert.strictEqual(cPortraitImg.style.display, 'none');
  assert.strictEqual(cPortraitAppliedSeq, 1);
  assert.strictEqual(syncs, 1);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_sidebar_list_height_caps_at_eight_items(tmp_path):
    """各栏目八项内不限制高度，第九项起只显示前八项并内部滚动。"""
    fit = _extract_js(_script(), "function fitListHeight(div)")
    driver = f"""
const assert = require('node:assert');
{fit}
function list(count) {{
  return {{style: {{}}, children: Array.from({{length: count}}, (_, i) =>
    ({{offsetTop: i * 22, offsetHeight: 22}}))}};
}}
for (const count of [0, 1, 8]) assert.strictEqual(fitListHeight(list(count)).maxHeight, 'none');
assert.strictEqual(fitListHeight(list(9)).maxHeight, '176px');
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_delete_button_only_shows_for_selected_entry_group(tmp_path):
    """式神/卡牌/机制互斥选中时，仅当前条目所属栏目显示并启用删除按钮。"""
    sync = _extract_js(_script(), "function syncDeleteButtons()")
    driver = f"""
const assert = require('node:assert');
const ids = ['c-del-shiki', 'c-del-card', 'c-del-mech'];
const buttons = Object.fromEntries(ids.map(id => [id, {{style: {{}}, disabled: false}}]));
const document = {{getElementById: id => buttons[id]}};
const cards = {{
  shikigami: [{{stem: 's', versions: [{{stem: 's'}}]}}],
  cards: [{{stem: 'c', versions: [{{stem: 'c'}}]}}],
}};
let curCard = 's', curMech = null;
{sync}
function shown(id) {{ return buttons[id].style.display !== 'none' && !buttons[id].disabled; }}
syncDeleteButtons();
assert.deepStrictEqual(ids.map(shown), [true, false, false]);
curCard = 'c'; syncDeleteButtons();
assert.deepStrictEqual(ids.map(shown), [false, true, false]);
curCard = null; curMech = 'm'; syncDeleteButtons();
assert.deepStrictEqual(ids.map(shown), [false, false, true]);
curMech = null; syncDeleteButtons();
assert.deepStrictEqual(ids.map(shown), [false, false, false]);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_shiki_deck_valid_checks_every_date_and_ignores_assist(tmp_path):
    """每日期排除协战/衍生物式神后至少 4R/3SR/1SSR；额外普通卡不影响结果。"""
    valid = _extract_js(_script(), "function shikiDeckValid(shikiName, groups)")
    driver = f"""
const assert = require('node:assert');
{valid}
function v(date, rarity, shiki = '甲', assist = false, type = '战斗') {{
  return {{date, rarity, type, shikigami: assist ? null : shiki,
    shikigami1: assist ? shiki : null, shikigami2: assist ? '乙' : null}};
}}
function card(name, versions) {{ return {{name, versions}}; }}
const base = ['R', 'R', 'R', 'R', 'SR', 'SR', 'SR', 'SSR'].map((rarity, i) =>
  card('卡' + i, [v('20260101', rarity)]));
assert.strictEqual(shikiDeckValid('甲', base), true);
assert.strictEqual(shikiDeckValid('甲', base.slice(1)), false);
assert.strictEqual(shikiDeckValid('甲', base.map((g, i) => i === 0
  ? card(g.name, [v('20260101', 'SSR')]) : g)), false);
const swapped = base.map((g, i) => {{
  if (i === 0) return card(g.name, [v('20260201', 'SR'), ...g.versions]);
  if (i === 4) return card(g.name, [v('20260201', 'R'), ...g.versions]);
  return g;
}});
assert.strictEqual(shikiDeckValid('甲', swapped), true);
const oneChanged = base.map((g, i) => i === 0
  ? card(g.name, [v('20260201', 'SR'), ...g.versions]) : g);
assert.strictEqual(shikiDeckValid('甲', oneChanged), false);
assert.strictEqual(shikiDeckValid('甲', [...base,
  card('协战', [v('20260101', 'R', '甲', true)]),
  card('衍生物', [v('20260101', 'SSR', '甲', false, '式神')]),
  card('额外N', [v('20260101', 'N')])]), true);
assert.strictEqual(shikiDeckValid('甲', [...base.slice(1),
  card('衍生物', [v('20260101', 'SSR', '甲', false, '式神')])]), false);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_new_derived_shikigami_uses_main_owner_and_card_slot(tmp_path):
    """卡牌栏新建式神沿用当前主要式神，对话框放在卡牌栏而不是左栏底部。"""
    ask_new_card = _extract_js(_script(), "function askNewCard(")
    driver = f"""
const assert = require('node:assert');
function element(tag) {{
  return {{tag, style: {{}}, children: [], value: '', textContent: '',
    appendChild(child) {{ this.children.push(child); child.parent = this; return child; }},
    focus() {{}}, select() {{}}}};
}}
const box = element('div'), slot = element('div'), home = element('div');
const document = {{createElement: element,
  getElementById(id) {{ return id === 'c-ask' ? box : id === 'c-ask-home' ? home : slot; }}}};
const TYPES = ['式神', '战斗', '法术', '形态', '幻境', '协战'];
const mainShiki = '基础式神';
function shikigamiNames() {{ return [mainShiki]; }}
function beginAsk() {{ return true; }}
function endAsk() {{}}
{ask_new_card}
(async () => {{
  const pending = askNewCard('c-ask-card');
  assert.strictEqual(box.parent, slot);
  const nameInput = box.children[1], typeSel = box.children[2];
  nameInput.value = '召唤物'; typeSel.value = '式神'; typeSel.onchange();
  box.children.at(-1).children[0].onclick();
  const result = await pending;
  assert.deepStrictEqual(result, {{name: '召唤物', type: '式神',
                                    shiki: {{shikigami: '基础式神'}}}});
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_new_card_dialog_chooses_derivative_for_regular_cards(tmp_path):
    """非式神、非协战卡在新建时确定衍生标记，其他类型不返回隐藏值。"""
    ask_new_card = _extract_js(_script(), "function askNewCard(")
    driver = f"""
const assert = require('node:assert');
function element(tag) {{
  return {{tag, style: {{}}, children: [], value: '', textContent: '', checked: false,
    set innerHTML(value) {{ if (value === '') this.children = []; }},
    appendChild(child) {{ this.children.push(child); child.parent = this; return child; }},
    focus() {{}}, select() {{}}}};
}}
const box = element('div'), slot = element('div'), home = element('div');
const document = {{createElement: element,
  getElementById(id) {{ return id === 'c-ask' ? box : id === 'c-ask-home' ? home : slot; }}}};
const TYPES = ['式神', '战斗', '法术', '形态', '幻境', '协战'];
const mainShiki = '基础式神';
function shikigamiNames() {{ return [mainShiki]; }}
function beginAsk() {{ return true; }}
function endAsk() {{}}
{ask_new_card}
async function create(type, derivative = false) {{
  const pending = askNewCard('c-ask-card');
  box.children[1].value = '测试卡';
  box.children[2].value = type;
  box.children[2].onchange();
  const row = box.children[3];
  assert.strictEqual(row.textContent.trim(), '衍生牌');
  assert.strictEqual(row.style.display, ['式神', '协战'].includes(type) ? 'none' : '');
  row.children[0].checked = derivative;
  box.children.at(-1).children[0].onclick();
  return await pending;
}}
(async () => {{
  assert.deepStrictEqual(await create('战斗', true),
    {{name: '测试卡', type: '战斗', shiki: {{shikigami: '基础式神'}}, token: true}});
  assert.deepStrictEqual(await create('法术'),
    {{name: '测试卡', type: '法术', shiki: {{shikigami: '基础式神'}}, token: false}});
  assert.deepStrictEqual(await create('式神', true),
    {{name: '测试卡', type: '式神', shiki: {{shikigami: '基础式神'}}}});
  assert.deepStrictEqual(await create('协战', true),
    {{name: '测试卡', type: '协战', shiki: {{}}}});
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_new_derivative_card_omits_default_rarity(tmp_path):
    handler = _extract_js(
        _script(), "document.getElementById('c-new-card').onclick = async () =>")
    driver = f"""
const assert = require('node:assert');
const buttons = {{}};
const document = {{getElementById: id => buttons[id] = {{}}}};
let curProject = 'P', mainShiki = null, selectSeq = 0, derivative = false;
const bodies = [];
async function askNewCard() {{ return {{name: '卡', type: '战斗',
  shiki: {{shikigami: '甲'}}, token: derivative}}; }}
function sanitizeStem(value) {{ return value; }}
function uniqueStem(value) {{ return value; }}
function skeleton(type, name, shiki) {{ return {{type, name, ...shiki, level: 1, rarity: 'R'}}; }}
function enc(value) {{ return value; }}
function listErr() {{}}
async function fetch(url, options) {{ bodies.push(JSON.parse(options.body)); return {{ok: true}}; }}
async function loadProjectIds() {{}}
async function loadCards() {{}}
{handler}
(async () => {{
  await buttons['c-new-card'].onclick();
  derivative = true;
  await buttons['c-new-card'].onclick();
  assert.strictEqual(bodies[0].rarity, 'R');
  assert.strictEqual('token' in bodies[0], false);
  assert.strictEqual(bodies[1].token, true);
  assert.strictEqual('rarity' in bodies[1], false);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_inline_ask_locks_save_and_recovers(tmp_path):
    """新版本等内联输入未结束时禁止保存/重开；取消后输入框与按钮流程恢复。"""
    script = _script()
    ask = _extract_js(script, "function ask(")
    busy = _extract_js(script, "function askBusy()")
    begin = _extract_js(script, "function beginAsk(title)")
    end = _extract_js(script, "function endAsk()")
    save = _extract_js(script, "async function saveCard()")
    driver = f"""
const assert = require('node:assert');
function element(tag) {{
  return {{tag, style: {{}}, children: [], value: '', textContent: '',
    appendChild(child) {{ this.children.push(child); child.parent = this; return child; }},
    focus() {{}}, select() {{}}}};
}}
const box = element('div'), slot = element('div'), home = element('div');
const document = {{createElement: element,
  getElementById(id) {{ return id === 'c-ask' ? box : id === 'c-ask-home' ? home : slot; }}}};
let activeAsk = null, pendingStorageWrites = 0;
const errors = [];
function showFormErrors(messages) {{ errors.push(...messages); }}
function guiDebug() {{}}
function storageBusy() {{ return false; }}
function fetch() {{ throw new Error('输入未结束时不得发起写盘请求'); }}
{busy}
{begin}
{end}
{ask}
{save}
(async () => {{
  const pending = ask({{title: '新版本', target: 'c-version-ask'}});
  assert.strictEqual(box.parent, slot);
  assert.strictEqual(askBusy(), true);
  assert.strictEqual(await ask({{title: '新建机制', target: 'c-ask-mech'}}), null);
  assert.strictEqual(await saveCard(), false);
  box.children.at(-1).children[1].onclick();
  assert.strictEqual(await pending, null);
  assert.strictEqual(box.parent, home);
  assert.strictEqual(activeAsk, null);
  const reopened = ask({{title: '新建机制', target: 'c-ask-mech'}});
  box.children.at(-1).children[0].onclick();
  assert.deepStrictEqual(await reopened, {{text: '', sel: null}});
  assert.strictEqual(activeAsk, null);
  assert.strictEqual(box.parent, home);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_save_response_cannot_overwrite_new_selection_or_later_edits(tmp_path):
    """慢保存响应不得改写已切换卡牌；保存后的新编辑仍保持未保存状态。"""
    save = _extract_js(_script(), "async function saveCard()")
    driver = f"""
const assert = require('node:assert');
let selectSeq = 0, contentRev = 0, pendingStorageWrites = 0;
let curProject = 'P', curCard = 'A', formData = {{name: 'A'}}, cardData = null, cDirty = true;
const cStatusEl = {{textContent: ''}};
let resolveFetch, reloads = 0, metadataRefreshes = 0;
function askBusy() {{ return false; }}
function storageBusy() {{ return false; }}
function guiDebug() {{}}
function validateCardJS() {{ return []; }}
async function confirmFallbackNaming() {{ return true; }}
function deepCopy(value) {{ return JSON.parse(JSON.stringify(value)); }}
function enc(value) {{ return value; }}
function fetch() {{ return new Promise(resolve => {{ resolveFetch = resolve; }}); }}
function showFormErrors() {{}}
function resetUndo() {{ throw new Error('旧响应不得重置撤回栈'); }}
async function loadCards() {{ reloads++; }}
async function loadProjectIds() {{ metadataRefreshes++; }}
const document = {{getElementById: () => null}};
{save}
(async () => {{
  const first = saveCard();
  while (!resolveFetch) await Promise.resolve();
  selectSeq++; curCard = 'B'; formData = {{name: 'B'}};
  resolveFetch({{ok: true, json: async () => ({{stem: 'A', updated: [], id: '10510101'}})}});
  assert.strictEqual(await first, true);
  assert.strictEqual(curCard, 'B');
  assert.strictEqual(formData.name, 'B');
  assert.strictEqual(cardData, null);
  assert.strictEqual(cDirty, true);
  assert.strictEqual(reloads, 0);

  selectSeq = 0; contentRev = 0; curCard = 'A'; formData = {{name: 'A'}};
  cardData = null; cDirty = true; resolveFetch = null;
  const second = saveCard();
  while (!resolveFetch) await Promise.resolve();
  contentRev++;  // 模拟写盘在途时键盘继续编辑
  resolveFetch({{ok: true, json: async () => ({{stem: 'A', updated: [], id: '10510101'}})}});
  assert.strictEqual(await second, true);
  assert.deepStrictEqual(cardData, {{name: 'A', id: '10510101'}});
  assert.strictEqual(formData.id, '10510101');  // 仅在途改其他字段也须记录最终 ID
  assert.strictEqual(cDirty, true);
  assert.strictEqual(reloads, 0);
  assert.strictEqual(metadataRefreshes, 1);
  assert.ok(cStatusEl.textContent.includes('仍未保存'));

  selectSeq = 0; contentRev = 0; curCard = 'A'; formData = {{name: 'A'}};
  cardData = null; cDirty = true; resolveFetch = null;
  const third = saveCard();
  while (!resolveFetch) await Promise.resolve();
  formData.id = '手动02'; contentRev++;
  resolveFetch({{ok: true, json: async () => ({{stem: 'A', updated: [], id: '10510101'}})}});
  assert.strictEqual(await third, true);
  assert.strictEqual(formData.id, '手动02');  // 用户已改 ID 不被旧保存响应覆盖
  assert.deepStrictEqual(cardData, {{name: 'A', id: '10510101'}});
  assert.strictEqual(cDirty, true);
  assert.strictEqual(metadataRefreshes, 2);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_active_input_blocks_form_rebuild_and_write_tracking_excludes_preview(tmp_path):
    """键盘路径也不能销毁活动输入框；预览请求不计入写盘交互锁。"""
    script = _script()
    build_card = _extract_js(script, "function buildForm()")
    build_mech = _extract_js(script, "function buildMechForm()")
    tracks = _extract_js(script, "function tracksStorageWrite(args)")
    driver = f"""
const assert = require('node:assert');
let activeAsk = {{title: '新版本'}};
{build_card}
{build_mech}
{tracks}
buildForm();
buildMechForm();  // 活动输入时提前返回，无需访问/清空 DOM
assert.strictEqual(tracksStorageWrite(['/api/preview', {{method: 'POST'}}]), false);
assert.strictEqual(tracksStorageWrite(['/api/entity-preview', {{method: 'POST'}}]), false);
assert.strictEqual(tracksStorageWrite(['/api/client-log', {{method: 'POST'}}]), false);
assert.strictEqual(tracksStorageWrite(['/api/projects/P/cards/A', {{method: 'PUT'}}]), true);
assert.strictEqual(tracksStorageWrite(['/api/projects/P/cards/A/artwork?x=1', {{method: 'POST'}}]), true);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_session_confirm_suppression_is_per_kind_and_confirm_only(tmp_path):
    """勾选后确认才抑制同类提示；取消不抑制，命名与未保存两类互不影响。"""
    script = _script()
    suppressed = _extract_js(script, "const sessionPromptSuppressed =")
    confirm = _extract_js(script, "function sessionConfirm(message, kind)")
    finish = _extract_js(script, "function finishSessionConfirm(ok)")
    driver = f"""
const assert = require('node:assert');
const ids = ['session-confirm-modal', 'session-confirm-text', 'session-confirm-suppress'];
const elements = Object.fromEntries(ids.map(id => [id,
  {{style: {{display: 'none'}}, textContent: '', checked: false}}]));
const document = {{getElementById: id => elements[id]}};
{suppressed}
let sessionConfirmState = null;
{confirm}
{finish}
(async () => {{
  let pending = sessionConfirm('id 未填写', 'naming');
  assert.strictEqual(elements['session-confirm-modal'].style.display, 'block');
  assert.strictEqual(elements['session-confirm-text'].textContent, 'id 未填写');
  elements['session-confirm-suppress'].checked = true;
  finishSessionConfirm(false);
  assert.strictEqual(await pending, false);
  assert.strictEqual(sessionPromptSuppressed.naming, false);
  pending = sessionConfirm('id 未填写', 'naming');
  elements['session-confirm-suppress'].checked = true;
  finishSessionConfirm(true);
  assert.strictEqual(await pending, true);
  assert.strictEqual(sessionPromptSuppressed.naming, true);
  elements['session-confirm-modal'].style.display = 'none';
  assert.strictEqual(await sessionConfirm('id 未填写', 'naming'), true);
  assert.strictEqual(elements['session-confirm-modal'].style.display, 'none');
  pending = sessionConfirm('有未保存修改', 'unsaved');
  assert.strictEqual(elements['session-confirm-modal'].style.display, 'block');
  finishSessionConfirm(false);
  assert.strictEqual(await pending, false);
  assert.strictEqual(sessionPromptSuppressed.unsaved, false);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_unsaved_and_naming_guards_await_session_confirm(tmp_path):
    """异步自定义弹窗的取消结果必须阻止切换与保存，不能按 Promise 真值放行。"""
    script = _script()
    discard = _extract_js(script, "async function confirmDiscard()")
    naming = _extract_js(script, "async function confirmFallbackNaming()")
    driver = f"""
const assert = require('node:assert');
let cDirty = true, mDirty = false, curMech = null;
const formData = {{id: '', version_date: '20261027'}}, mechForm = null;
function confirm() {{ throw new Error('不应再调用原生 confirm'); }}
function askBusy() {{ return false; }}
function storageBusy() {{ return false; }}
async function sessionConfirm(message, kind) {{ return kind === 'naming'; }}
{discard}
{naming}
(async () => {{
  assert.strictEqual(await confirmDiscard(), false);
  assert.strictEqual(await confirmFallbackNaming(), true);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_shutdown_tool_checks_all_unsaved_state_and_closes(tmp_path):
    """退出按钮：任一编辑区有修改都先确认；取消不发请求，确认后关闭服务与标签页。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function hasUnsavedChanges()",
        "async function shutdownTool()",
    ))
    driver = f"""
const assert = require('node:assert');
let dirty = false, singleDirty = true, cDirty = false, mDirty = false;
let manualShutdown = false, allowExit = false, confirmCalls = 0, closeCalls = 0;
const requests = [], alerts = [];
const button = {{disabled: false}};
const document = {{getElementById: id => button}};
const window = {{close() {{ closeCalls++; }}}};
async function sessionConfirm(message, kind) {{
  confirmCalls++;
  assert.strictEqual(kind, 'unsaved');
  return allowExit;
}}
async function fetch(url, options) {{
  requests.push({{url, options}});
  return {{ok: true}};
}}
{functions}
(async () => {{
  await shutdownTool();
  assert.strictEqual(confirmCalls, 1);
  assert.strictEqual(requests.length, 0);
  assert.strictEqual(closeCalls, 0);
  assert.strictEqual(button.disabled, false);
  allowExit = true;
  await shutdownTool();
  assert.strictEqual(requests.length, 1);
  assert.strictEqual(requests[0].url, '/api/shutdown');
  assert.strictEqual(requests[0].options.method, 'POST');
  assert.strictEqual(closeCalls, 1);
  assert.strictEqual(manualShutdown, true);
  assert.strictEqual(button.disabled, true);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_mechanism_startup_retries_transient_failure(tmp_path):
    """启动时服务尚未就绪不得让已有机制永久空列表；有限重试成功后正常显示。"""
    script = _script()
    load = _extract_js(script, "async function loadMechs(selectName = null, reportError = true)")
    boot = _extract_js(script, "async function bootMechs(attempt = 0)")
    driver = f"""
const assert = require('node:assert');
let mechs = [], curMech = null, built = 0, errors = [], attempts = 0;
const timers = [];
function setTimeout(fn, delay) {{ timers.push(fn); return timers.length; }}
function listErr(msgs) {{ errors = msgs; }}
function buildMechList() {{ built = mechs.length; }}
function exitMech() {{ curMech = null; }}
function clearCard() {{}}
async function selectMech() {{}}
async function parseErrorDetail() {{ return ['bad']; }}
async function fetch(url) {{
  assert.strictEqual(url, '/api/mechanisms');
  attempts++;
  if (attempts === 1) throw new Error('服务尚未就绪');
  return {{ok: true, json: async () => [{{stem: '不屈', name: '不屈',
    versions: [{{stem: '不屈', date: '20191212'}}], count: 1}}]}};
}}
{load}
{boot}
(async () => {{
  await bootMechs();
  assert.strictEqual(mechs.length, 0);
  assert.strictEqual(timers.length, 1);
  await timers.shift()();
  assert.strictEqual(attempts, 2);
  assert.strictEqual(mechs[0].name, '不屈');
  assert.strictEqual(built, 1);
  assert.deepStrictEqual(errors, []);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_reserved_project_name_warns_before_request(tmp_path):
    """mechanisms 大小写变体均被前端拦截并弹窗说明，不发送项目请求。"""
    script = _script()
    is_reserved = _extract_js(script, "function isReservedProjectName(name)")
    reject = _extract_js(script, "function rejectReservedProjectName(name)")
    driver = f"""
const assert = require('node:assert');
const messages = [];
function alert(message) {{ messages.push(message); }}
{is_reserved}
{reject}
assert.strictEqual(isReservedProjectName('mechanisms'), true);
assert.strictEqual(isReservedProjectName(' Mechanisms '), true);
assert.strictEqual(isReservedProjectName('MECHANISMS'), true);
assert.strictEqual(isReservedProjectName('mechanisms-old'), false);
assert.strictEqual(isReservedProjectName('我的项目'), false);
assert.strictEqual(rejectReservedProjectName('Mechanisms'), true);
assert.strictEqual(rejectReservedProjectName('我的项目'), false);
assert.deepStrictEqual(messages, ['项目名「mechanisms」是跨项目通用机制的保留目录，请更换项目名。']);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_frame_variant_layout_independence_and_sparse_payload(tmp_path):
    script = _script()
    for removed in ("syncElemField", "syncRegionField", "propagateFromCurrentType", "STYLE_KEYS"):
        assert removed not in script
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function globalTypeLayout(t, variant = layoutFrameVariant)",
        "function layoutForRender(layout)",
        "function typeLayout()",
        "function diffLayout(eff, base)",
        "function layoutSavePayload()",
        "function singleGlobalLayout()",
    ))
    driver = f"""
const assert = require('node:assert');
const TYPES = ["式神", "战斗", "法术", "形态", "幻境", "协战"];
const base = () => ({{elements: {{power: {{kind: 'stat', field: 'power', pos: [1, 2],
  icon_size: 16, num_offset: [0, 1], font_size: 12}}}},
  text_regions: {{desc: {{center: [1, 2], width: 20, height: 10}}}}}});
const layouts = Object.fromEntries(TYPES.map(t => [t, base()]));
for (const t of TYPES)
  layouts[t].frame_variants = {{black: base(), blue: base(), red: base()}};
let layoutFrameVariant = 'black', curType = '战斗';
let entityLayoutMode = false, cardLayoutMode = null, singleLayout = null;
let formData = {{type: '战斗', frame_variant: 'black'}};
function deepCopy(value) {{ return JSON.parse(JSON.stringify(value)); }}
{functions}
assert.strictEqual(typeLayout(), layouts['战斗'].frame_variants.black);
typeLayout().elements.power.icon_size = 64;
typeLayout().text_regions.desc.width = 99;
assert.strictEqual(singleGlobalLayout().elements.power.icon_size, 64);
assert.strictEqual(singleGlobalLayout().frame_variants, undefined);
assert.strictEqual(layoutForRender(layouts['战斗']).frame_variants, undefined);
curType = '协战';
assert.strictEqual(typeLayout(), layouts['协战'].frame_variants.black);
typeLayout().elements.power.icon_size = 48;
for (const t of TYPES) {{
  assert.strictEqual(layouts[t].elements.power.icon_size, 16, `${{t}} norm`);
  const expected = t === '战斗' ? 64 : (t === '协战' ? 48 : 16);
  assert.strictEqual(layouts[t].frame_variants.black.elements.power.icon_size, expected, `${{t}} black`);
  assert.strictEqual(layouts[t].frame_variants.blue.elements.power.icon_size, 16, `${{t}} blue`);
  assert.strictEqual(layouts[t].frame_variants.black.text_regions.desc.width,
                     t === '战斗' ? 99 : 20, `${{t}} desc`);
}}
const payload = layoutSavePayload();
assert.strictEqual(payload['战斗'].frame_variants.black.elements.power.icon_size, 64);
assert.strictEqual(payload['战斗'].frame_variants.black.text_regions.desc.width, 99);
assert.strictEqual(payload['战斗'].frame_variants.blue, undefined);
assert.strictEqual(payload['战斗'].frame_variants.red, undefined);
assert.strictEqual(payload['法术'].frame_variants, undefined);
assert.strictEqual(payload['协战'].frame_variants.black.elements.power.icon_size, 48);
assert.strictEqual(payload['协战'].frame_variants.blue, undefined);
assert.strictEqual(layouts['战斗'].frame_variants.black.elements.power.icon_size, 64);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_card_frame_variant_buttons(tmp_path):
    html = (Path(__file__).resolve().parent.parent / "bwpdiy/web/static/editor.html").read_text(
        encoding="utf-8")
    assert 'id="c-frame-variants"' in html
    assert "selRowC(div, '框品'" not in html
    sync = _extract_js(_script(), "function syncCardFrameButtons()")
    driver = f"""
const assert = require('node:assert');
const FRAME_VARIANT_TYPES = new Set(["式神", "战斗", "法术", "形态", "幻境", "协战"]);
const buttons = ['norm', 'blue', 'black', 'red'].map(fv =>
  ({{dataset: {{fv}}, disabled: false, classList: {{active: false}}}}));
for (const b of buttons) b.classList.toggle = (name, on) => {{ b.classList.active = on; }};
const document = {{querySelectorAll: () => buttons}};
let formData = {{type: '战斗', frame_variant: 'black'}};
{sync}
syncCardFrameButtons();
assert(buttons.every(b => !b.disabled));
assert.deepStrictEqual(buttons.map(b => b.classList.active), [false, false, true, false]);
formData = {{type: '协战'}};
syncCardFrameButtons();
assert.deepStrictEqual(buttons.map(b => b.disabled), [false, false, false, false]);
assert.deepStrictEqual(buttons.map(b => b.classList.active), [true, false, false, false]);
formData = null;
syncCardFrameButtons();
assert(buttons.every(b => b.disabled));
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_gui_stat_inputs_derived(tmp_path):
    """stat 输入框从布局 stat 元素 field 派生 + 适用矩阵过滤（协战/非觉醒法术/表外无输入框）。"""
    script = _script()
    stat_matrix = _extract_js(script, "const STAT_MATRIX = {") + ";"
    stat_inputs = _extract_js(script, "function statInputs()")
    driver = f"""
const assert = require('node:assert');
{stat_matrix}
{stat_inputs}
let curType;
let cardOverrides = {{}};
let samples = {{"法术": {{evolve: true}}}};
function cardField(name) {{
  const ov = cardOverrides[curType] || {{}};
  return name in ov ? ov[name] : (samples[curType] || {{}})[name];
}}
const layouts = {{
  "式神": {{elements: {{power: {{kind: "stat", field: "power"}},
                       health: {{kind: "stat", field: "health"}}, name: {{kind: "text"}}}}}},
  "战斗": {{elements: {{power: {{kind: "stat", field: "power+"}},
                       shield: {{kind: "stat", field: "shield+"}}}}}},
  "法术": {{elements: {{power: {{kind: "stat", field: "power+"}},
                       health: {{kind: "stat", field: "health+"}}}}}},
  "幻境": {{elements: {{durability: {{kind: "stat", field: "durability"}}}}}},
  "协战": {{elements: {{}}}},
}};
function typeLayout() {{ return layouts[curType]; }}
curType = "式神";
assert.deepStrictEqual(statInputs(), [["power", "力量"], ["health", "生命"]]);
curType = "战斗";
assert.deepStrictEqual(statInputs(), [["power+", "力量+"], ["shield+", "护甲+"]]);
curType = "法术";
assert.deepStrictEqual(statInputs(), [["power+", "力量+"], ["health+", "生命+"]]);
cardOverrides["法术"] = {{evolve: false}};  // 非觉醒法术：无输入框
assert.deepStrictEqual(statInputs(), []);
delete cardOverrides["法术"];
curType = "幻境";
assert.deepStrictEqual(statInputs(), [["durability", "耐久"]]);
curType = "协战";
assert.deepStrictEqual(statInputs(), []);
// 布局 field 被改出矩阵（污染场景）：表外 field 不提供输入框
layouts["式神"].elements.power.field = "power+";
curType = "式神";
assert.deepStrictEqual(statInputs(), [["health", "生命"]]);
console.log("OK");
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_js_constants_parity_with_python(tmp_path):
    """editor.html 的共享常量与 Python 两侧（store/schema.py、render/badges.py）对账。

    JS 是第三份拷贝（Python 两侧已有 test_stat_matrix_parity_with_render 对账），
    漂移时本测试显式失败而非静默。
    """
    script = _script()
    start = script.index("const TYPES =")
    end = script.index(";", script.index("const EVOLVE_TYPES =")) + 1
    consts = script[start:end]
    driver = consts + """
console.log(JSON.stringify({
  TYPES, FACTIONS, RARITIES, LEVELS, STATS_BY_TYPE, SIGNED_STATS,
  STAT_MATRIX, NONNEG_TYPES: [...NONNEG_TYPES], EVOLVE_TYPES: [...EVOLVE_TYPES],
}));
"""
    import json
    import subprocess
    src = tmp_path / "driver.js"
    src.write_text(driver, encoding="utf-8")
    r = subprocess.run([NODE, str(src)], capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    js = json.loads(r.stdout)

    from bwpdiy.render.badges import _STAT_MATRIX
    from bwpdiy.store import schema

    assert js["TYPES"] == list(schema.CARD_TYPES)
    assert js["FACTIONS"] == list(schema.FACTIONS)
    assert js["RARITIES"] == list(schema.RARITIES)
    assert js["LEVELS"] == list(schema.LEVELS)
    assert js["STATS_BY_TYPE"] == {k: list(v) for k, v in schema._STATS_BY_TYPE.items()}
    assert js["SIGNED_STATS"] == list(schema._SIGNED_STATS)
    assert sorted(js["EVOLVE_TYPES"]) == sorted(schema._EVOLVE_TYPES)
    # STAT_MATRIX 的 (type, field) 键集与 render 矩阵一致；标签值非空
    js_keys = {(t, f) for t, fields in js["STAT_MATRIX"].items() for f in fields}
    assert js_keys == set(_STAT_MATRIX)
    assert all(label for fields in js["STAT_MATRIX"].values() for label in fields.values())
    # 非负类型 = 矩阵中 plain（无符号）类型
    plain_types = {t for (t, _f), mode in _STAT_MATRIX.items() if mode == "plain"}
    assert sorted(js["NONNEG_TYPES"]) == sorted(plain_types)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_js_validate_reinforce_whitelist(tmp_path):
    """validateCardJS 白名单对齐新 schema：协战允许 shikigami1/shikigami2、拒绝 shikigami。"""
    script = _script()
    end = script.index(";", script.index("const FRAME_VARIANT_TYPES =")) + 1
    consts = script[script.index("const TYPES ="):end]
    validate = _extract_js(script, "function validateCardJS(d)")
    driver = f"""
const assert = require('node:assert');
{consts}
{validate}
const ok = {{type: '协战', name: '共鸣', level: 1, rarity: 'R',
             shikigami1: '甲', shikigami2: '乙', description: ''}};
assert.deepStrictEqual(validateCardJS(ok), []);
const withOld = {{...ok, shikigami: '甲'}};
assert.ok(validateCardJS(withOld).some(e => e.includes('shikigami') && e.includes('白名单')));
assert.ok(validateCardJS({{...ok, shikigami1: 3}}).some(e => e.includes('shikigami1')));
assert.deepStrictEqual(validateCardJS({{...ok, duo_frame: true}}), []);  // 协战双式神框开关
assert.ok(validateCardJS({{...ok, duo_frame: '是'}}).some(e => e.includes('duo_frame')));
const battle = {{type: '战斗', name: '斩', level: 2, rarity: 'R', shikigami: '甲',
                'power+': 1, 'shield+': 1, description: ''}};
assert.deepStrictEqual(validateCardJS(battle), []);
assert.deepStrictEqual(validateCardJS({{...battle, token: true}}), []);
assert.deepStrictEqual(validateCardJS({{...battle, token: false}}), []);
assert.ok(validateCardJS({{...battle, token: 1}}).some(e => e.includes('token')));
assert.ok(validateCardJS({{...ok, token: true}}).some(e => e.includes('token') && e.includes('白名单')));
assert.ok(validateCardJS({{...battle, duo_frame: true}}).some(e => e.includes('白名单')));
assert.ok(validateCardJS({{...battle, shikigami1: '甲'}}).some(e => e.includes('白名单')));
assert.ok(validateCardJS({{...battle, name: ''}}).some(e => e.includes('name')));
// 单卡布局覆盖段：形状校验（合法稀疏覆盖通过；畸形 422 口径报错）
assert.deepStrictEqual(validateCardJS({{...battle, layout: {{elements: {{name: {{pos: [1, 2]}}}},
                                        text_regions: {{desc: {{width: 300}}}}}}}}), []);
assert.ok(validateCardJS({{...battle, layout: 'junk'}}).some(e => e.includes('layout')));
assert.ok(validateCardJS({{...battle, layout: {{junk: {{}}}}}}).some(e => e.includes('layout.junk')));
assert.ok(validateCardJS({{...battle, layout: {{elements: {{name: 'x'}}}}}}).some(e => e.includes('layout.elements')));
console.log("OK");
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_entity_layout_mode_isolated_from_card_types(tmp_path):
    """实体布局独立编辑、切换和还原，不向六种卡牌类型传播，也不显示觉醒星。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function typeLayout()",
        "function selectType(t)",
        "function selectMechLayout()",
        "function selectEntityLayout()",
        "function layoutDiffs(a, b)",
        "function formatDiffs(diffs)",
        "function restoreLayout(all)",
        "function buildTypes()",
        "function buildProps()",
    ))
    driver = f"""
const assert = require('node:assert');
const TYPES = ["式神", "战斗", "法术", "形态", "幻境", "协战"];
const FRAME_VARIANT_TYPES = new Set(TYPES.filter(t => t !== '协战'));
let curType = '式神', cardLayoutMode = null, singleLayout = {{elements: {{}}}};
let entityLayoutMode = false, mechLayoutMode = false, layoutFrameVariant = 'norm';
let sel = null, previewImg = null, dirty = false, singleDirty = false;
const base = () => ({{elements: {{power: {{kind: 'stat', field: 'power', pos: [1, 2],
  icon_size: 16, num_offset: [0, 1], font_size: 12}}}},
  text_regions: {{desc: {{center: [1, 2], width: 20, height: 10}}}}}});
const layouts = Object.fromEntries(TYPES.map(t => [t, base()]));
layouts['对局式神'] = {{elements: {{level: {{kind: 'level_badge', pos: [32, 88],
  base_size: 18, num_size: 14, num_offset: [0, 0]}}}}}};
layouts['机制'] = {{text_size: 24}};
const statusEl = {{textContent: ''}};
function deepCopy(value) {{ return JSON.parse(JSON.stringify(value)); }}
function markDirty() {{ dirty = true; }}
function showMechPanel(on) {{}}
function syncLayoutFrameButtons() {{}}
function buildLists() {{}}
function buildCardProps() {{}}
function buildMechProps() {{}}
function refreshPreview() {{}}
function restoreSingleLayout() {{}}
function draw() {{}}
function confirm() {{ return true; }}
function disp(key) {{ return key; }}
function title(text) {{ return {{text}}; }}
const propLabels = [];
function numRow(div, label) {{ propLabels.push(label); }}
function element(tag) {{ return {{tag, children: [], className: '', textContent: '', style: {{}},
  appendChild(child) {{ this.children.push(child); }} }}; }}
const typesDiv = element('div'), propsDiv = element('div');
const document = {{
  getElementById: id => id === 'l-types' ? typesDiv : propsDiv,
  querySelectorAll: () => [],
  createElement: element,
}};
let activeAsk = null;
function globalTypeLayout(t) {{ return layouts[t]; }}
{functions}
entityLayoutMode = true;
assert.strictEqual(typeLayout(), layouts['对局式神']);
selectType('战斗');
assert(!entityLayoutMode && !mechLayoutMode);
selectEntityLayout();
assert(entityLayoutMode && !mechLayoutMode);
selectMechLayout();
assert(!entityLayoutMode && mechLayoutMode);
buildTypes();
const tabs = typesDiv.children.filter(x => x.className === 'tab').map(x => x.textContent);
assert.deepStrictEqual(tabs, [...TYPES, '对局式神', '机制']);
assert(!TYPES.includes('对局式神'));
const snapshot = deepCopy(layouts);
layouts['战斗'].elements.power.pos = [9, 9];
layouts['对局式神'].elements.level.pos = [1, 1];
layouts['机制'].text_size = 30;
let layoutSnapshot = deepCopy(snapshot);
restoreLayout(true);
assert.deepStrictEqual(layouts, snapshot);
entityLayoutMode = true; mechLayoutMode = false;
sel = {{kind: 'element', name: 'level'}};
propLabels.length = 0;
buildProps();
assert(propLabels.includes('底座尺寸') && propLabels.includes('勾玉尺寸'));
assert(!propLabels.some(label => label.includes('星标')));
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_entity_layout_list_fixed_order(tmp_path):
    """对局式神元素按业务顺序排列，不受字典插入顺序和 x 坐标影响。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function buildLists()",
        "function layoutRegions()",
        "function disp(k)",
    ))
    disp_map = script[script.index("const DISP ="):script.index("function disp(k)")]
    driver = f"""
const assert = require('node:assert');
let entityLayoutMode = true, mechLayoutMode = false;
const stat = (x) => ({{kind: 'stat', pos: [x, 100]}});
const layouts = {{'对局式神': {{
  elements: {{
    shield: stat(0), health: stat(40), combat_power: stat(10),
    power: stat(30), level: {{kind: 'level_badge', pos: [50, 100]}},
  }},
  art_window: {{center: [48, 72], width: 84, height: 132}},
}}}};
function typeLayout() {{ return layouts['对局式神']; }}
{disp_map}
function element(tag) {{ return {{tag, children: [], style: {{}}, dataset: {{}}, textContent: '',
  appendChild(child) {{ this.children.push(child); }} }}; }}
const elems = element('div');
const document = {{getElementById: () => elems, createElement: element}};
let sel = null;
function refreshSel() {{}}
let activeAsk = null;
{functions}
buildLists();
const items = elems.children;
assert.deepStrictEqual(items.map(x => x.textContent),
  ['等级', '卡图内窗', '力量', '生命', '战力', '护甲']);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_entity_art_window_pick_drag_draw_and_props(tmp_path):
    """卡图内窗复用区域绿框/拖拽，并提供五项专用实时布局控件。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function layoutRegions()",
        "function draw()",
        "function handle([x, y], color, s = 6, square = false)",
        "function pick(mx, my)",
        "function buildProps()",
        "function title(t)",
        "function numRow(div, label, val, set)",
        "function checkRow(div, label, val, set)",
    ))
    driver = f"""
const assert = require('node:assert');
let entityLayoutMode = true, mechLayoutMode = false, cardLayoutMode = null;
let sel = null, previewImg = null, previewOffset = [0, 0], dirty = false, scheduled = 0;
const normal = {{elements: {{}}, text_regions: {{desc: {{center: [1, 2], width: 3, height: 4}}}}}};
const entity = {{version: 2, elements: {{}}, art_window: {{center: [48, 72], width: 84,
  height: 132, frame_center: true, offset_y: 0}}}};
const layouts = {{'式神': normal, '对局式神': entity}};
let curType = '式神';
function typeLayout() {{ return entityLayoutMode ? entity : normal; }}
const strokes = [];
const ctx = {{clearRect() {{}}, save() {{}}, restore() {{}}, translate() {{}},
  strokeRect(...args) {{ strokes.push({{color: this.strokeStyle, args}}); }},
  fillRect() {{}}, beginPath() {{}}, arc() {{}}, fill() {{}}}};
const canvas = {{width: 96, height: 144}};
function element(tag) {{ return {{tag, children: [], style: {{}}, textContent: '',
  appendChild(child) {{ this.children.push(child); }} }}; }}
const props = element('div');
const document = {{getElementById: () => props, createElement: element}};
function disp(key) {{ return key; }}
function markDirty() {{ dirty = true; }}
function schedulePreview() {{ scheduled++; }}
let activeAsk = null;
{functions}
assert.deepStrictEqual(layoutRegions(), {{art_window: entity.art_window}});
assert.deepStrictEqual(Object.keys(layoutRegions()), ['art_window']);
const target = pick(48, 72);
assert(target && target.sel.kind === 'region' && target.sel.name === 'art_window');
target.set(50, 75);
assert.deepStrictEqual(entity.art_window.center, [50, 75]);
assert.deepStrictEqual(normal.text_regions.desc.center, [1, 2]);
sel = null; draw();
assert(strokes.some(s => s.color === '#4f4' && JSON.stringify(s.args) === JSON.stringify([8, 9, 84, 132])));
sel = {{kind: 'region', name: 'art_window'}};
buildProps();
const controls = {{}};
function visit(node) {{
  if (node.tag === 'label' && node.children[0]) controls[node.textContent.trim()] = node.children[0];
  for (const child of node.children || []) visit(child);
}}
visit(props);
assert.deepStrictEqual(Object.keys(controls), ['中心 x', '中心 y', '宽度', '高度', '框体居中', '纵向偏移']);
controls['中心 x'].value = '55'; controls['中心 x'].onchange();
controls['框体居中'].checked = false; controls['框体居中'].onchange();
controls['纵向偏移'].value = '4'; controls['纵向偏移'].onchange();
assert.strictEqual(entity.art_window.center[0], 55);
assert.strictEqual(entity.art_window.frame_center, false);
assert.strictEqual(entity.art_window.offset_y, 4);
assert.strictEqual(normal.text_regions.desc.center[0], 1);
assert(dirty && scheduled === 3);
entityLayoutMode = false;
assert.strictEqual(layoutRegions(), normal.text_regions);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_entity_layout_preview_native_size_and_scaled_mouse(tmp_path):
    """实体布局固定样卡走无项目预览；CSS 放大不改变 PNG 尺寸，鼠标按比例反算。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "async function refreshPreview()",
        "async function refreshEntityLayoutPreview()",
        "async function handleLayoutPreviewResponse(r, seq)",
        "function mousePos(ev)",
    ))
    driver = f"""
const assert = require('node:assert');
let entityLayoutMode = true, mechLayoutMode = false, cardLayoutMode = null;
let previewSeq = 0, dirty = false, singleDirty = false;
let previewImg = null, previewOffset = [0, 0];
const entityLayoutSample = {{level: 2, level_color: 'yellow', power: 2, health: 5, combat_power: 1, shield: -1}};
const layouts = {{'对局式神': {{elements: {{}}}}}};
const canvas = {{width: 0, height: 0, style: {{}},
  getBoundingClientRect: () => ({{left: 10, top: 20, width: 288, height: 432}})}};
const statusEl = {{textContent: ''}};
const requests = [];
function typeLayout() {{ return layouts['对局式神']; }}
function draw() {{}}
const URL = {{createObjectURL: () => 'blob:entity', revokeObjectURL: () => {{}}}};
class Image {{
  constructor() {{ this.naturalWidth = 96; this.naturalHeight = 144; }}
  set src(value) {{ this._src = value; this.onload(); }}
  get src() {{ return this._src; }}
}}
async function fetch(url, options) {{
  requests.push({{url, options}});
  return {{ok: true, headers: {{get: () => '0,0'}}, blob: async () => ({{kind: 'png'}})}};
}}
let activeAsk = null;
{functions}
(async () => {{
  await refreshPreview();
  assert.strictEqual(requests.length, 1);
  assert.strictEqual(requests[0].url, '/api/entity-preview');
  assert.deepStrictEqual(JSON.parse(requests[0].options.body), {{
    card: {{type: '式神', name: '布局样卡'}},
    state: {{level: 2, level_color: 'yellow', power: 2, health: 5, combat_power: 1, shield: -1}},
    layout: layouts['对局式神'],
  }});
  assert.strictEqual(canvas.width, 96);
  assert.strictEqual(canvas.height, 144);
  assert.strictEqual(canvas.style.width, '288px');
  assert.strictEqual(canvas.style.height, '432px');
  assert.deepStrictEqual(mousePos({{clientX: 154, clientY: 236}}), [48, 72]);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_entity_layout_sample_stat_inputs(tmp_path):
    """对局布局样卡四项数值实时预览，力量/生命非负且不污染布局脏标记。"""
    script = _script()
    sample = _extract_js(script, "const entityLayoutSample = {") + ";"
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function buildCardProps()",
        "function numRowC(div, label, val, nonneg, set, extra = null, max = 9999999999, min = null)",
        "function selRowC(div, label, opts, val, set, map = null)",
        "function battleCheckbox(div, label, checked, set, disabled = false)",
    ))
    driver = f"""
const assert = require('node:assert');
let entityLayoutMode = true, cardLayoutMode = null, scheduled = 0;
function schedulePreview() {{ scheduled++; }}
function element(tag) {{ return {{tag, children: [], textContent: '', value: '', style: {{}},
  appendChild(child) {{ this.children.push(child); }} }}; }}
const div = element('div');
const document = {{getElementById: () => div, createElement: element}};
{sample}
let activeAsk = null;
{functions}
buildCardProps();
assert.deepStrictEqual(div.children.slice(0, 4).map(x => x.textContent),
  ['力量 ', '生命 ', '战力 ', '护甲 ']);
const inputs = div.children.slice(0, 4).map(x => x.children[0]);
assert.deepStrictEqual(inputs.map(x => x.min), [0, 0, undefined, undefined]);
inputs[0].value = '-8'; inputs[0].onchange();
inputs[1].value = '7'; inputs[1].onchange();
inputs[2].value = '-3'; inputs[2].onchange();
inputs[3].value = '-2'; inputs[3].onchange();
assert.deepStrictEqual([entityLayoutSample.power, entityLayoutSample.health,
  entityLayoutSample.combat_power, entityLayoutSample.shield], [0, 7, -3, -2]);
assert.strictEqual(scheduled, 4);
inputs[3].onwheel({{deltaY: -1, preventDefault() {{}}}});
assert.strictEqual(entityLayoutSample.shield, -1);
assert.strictEqual(scheduled, 5);
assert.deepStrictEqual(inputs.map(x => x.max), [9999999999, 9999999999, 9999999999, 9999999999]);
inputs[0].value = '10000000000'; inputs[0].onchange();
inputs[3].value = '-10000000000'; inputs[3].onchange();
assert.strictEqual(entityLayoutSample.power, 9999999999);
assert.strictEqual(entityLayoutSample.shield, -9999999999);
assert.strictEqual(scheduled, 7);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_layout_burst_status_and_entity_counter_props_drag_and_order(tmp_path):
    """爆能/特殊状态按等级锚点调参/拖拽；实体 counter 无符号参数并按固定顺序列出。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function buildLists()",
        "function layoutRegions()",
        "function disp(k)",
        "function buildProps()",
        "function title(t)",
        "function numRow(div, label, val, set)",
        "function pick(mx, my)",
    ))
    disp_map = script[script.index("const DISP ="):script.index("function disp(k)")]
    driver = f"""
const assert = require('node:assert');
let entityLayoutMode = false, mechLayoutMode = false, cardLayoutMode = null;
let curType = '战斗', sel = null, dirty = false, scheduled = 0;
const SIGNED_STATS = ['power+', 'health+', 'shield+'];
const layouts = {{
  '战斗': {{elements: {{
    level: {{kind: 'level_badge', pos: [10, 10]}},
    power: {{kind: 'stat', field: 'power+', pos: [0, 100], icon_size: 12,
      num_offset: [12, 0], font_size: 14, stroke_width: 2}},
    burst: {{kind: 'burst', offset: [30, 40], icon_size: 12, num_offset: [12, 0],
      font_size: 14, stroke_width: 2, sign_offset: [0, 0], group_offset: [0, 0],
      sign_size_plus: 7, sign_size_minus: 6}},
    status: {{kind: 'status', offset: [-20, 40], icon_size: 20}},
  }}, text_regions: {{}}}},
  '对局式神': {{version: 2, elements: {{
    defeated: {{kind: 'counter', pos: [48, 66], icon_size: 44, num_offset: [0, 0],
      font_size: 40, stroke_width: 2}},
    shield: {{kind: 'stat', pos: [0, 100]}},
    energy: {{kind: 'counter', pos: [82, 18], icon_size: 28, num_offset: [0, 0],
      font_size: 24, stroke_width: 2}},
    countdown: {{kind: 'counter', pos: [70, 30], icon_size: 24, num_offset: [2, -1],
      font_size: 22, stroke_width: 1}},
    health: {{kind: 'stat', pos: [40, 100]}}, combat_power: {{kind: 'stat', pos: [10, 100]}},
    power: {{kind: 'stat', pos: [30, 100]}}, level: {{kind: 'level_badge', pos: [48, 137]}},
  }}, art_window: {{center: [48, 72], width: 84, height: 132}}}},
}};
function typeLayout() {{ return entityLayoutMode ? layouts['对局式神'] : layouts[curType]; }}
function markDirty() {{ dirty = true; }}
function schedulePreview() {{ scheduled++; }}
function refreshSel() {{}}
function draw() {{}}
let activeAsk = null;
function element(tag) {{ return {{tag, children: [], style: {{}}, dataset: {{}}, textContent: '',
  set innerHTML(value) {{ if (value === '') this.children = []; }},
  appendChild(child) {{ this.children.push(child); return child; }} }}; }}
const elems = element('div'), props = element('div');
const document = {{getElementById: id => id === 'l-elems' ? elems : props,
  createElement: element}};
{disp_map}
{functions}
const EVOLVE_TYPES = new Set(['战斗', '法术', '形态', '幻境']);
buildLists();
assert.deepStrictEqual(elems.children.map(x => x.textContent), ['等级标', '爆能', '特殊状态', '力量']);
for (const t of ['式神', '协战']) {{
  layouts[t] = {{elements: {{level: {{kind: 'level_badge', pos: [10, 10]}},
    burst: {{kind: 'burst', offset: [30, 40]}}}}, text_regions: {{}}}};
  curType = t; buildLists();
  assert.deepStrictEqual(elems.children.map(x => x.textContent), ['等级标']);
}}
curType = '战斗'; buildLists();
sel = {{kind: 'element', name: 'burst'}};
buildProps();
const controls = {{}};
function collect(node, target = controls) {{
  if (node.tag === 'label' && node.children[0]) target[node.textContent.trim()] = node.children[0];
  for (const child of node.children || []) collect(child, target);
}}
collect(props);
for (const label of ['偏移 x', '偏移 y', '图标尺寸', '数字偏移 x', '数字偏移 y', '字号',
                     '符号偏移 x', '符号偏移 y', '符号数字整体偏移 x',
                     '符号数字整体偏移 y', '加号尺寸', '减号尺寸'])
  assert(controls[label], `缺少爆能参数：${{label}}`);
assert(!controls['位置 x']);
assert(!controls['描边宽度']);
const target = pick(40, 50);
assert(target && target.sel.name === 'burst');
target.set(70, 80);
assert.deepStrictEqual(layouts['战斗'].elements.burst.offset, [60, 70]);
assert.deepStrictEqual(layouts['战斗'].elements.level.pos, [10, 10]);
controls['偏移 x'].value = '9'; controls['偏移 x'].onchange();
assert.deepStrictEqual(layouts['战斗'].elements.burst.offset, [9, 70]);
sel = {{kind: 'element', name: 'status'}};
buildProps();
const statusControls = {{}};
collect(props, statusControls);
assert.deepStrictEqual(Object.keys(statusControls), ['偏移 x', '偏移 y', '图标尺寸']);
const statusTarget = pick(-10, 50);
assert(statusTarget && statusTarget.sel.name === 'status');
statusTarget.set(50, 70);
assert.deepStrictEqual(layouts['战斗'].elements.status.offset, [40, 60]);
assert.strictEqual(layouts['战斗'].elements.status.pos, undefined);
assert.deepStrictEqual(layouts['战斗'].elements.level.pos, [10, 10]);
statusControls['图标尺寸'].value = '26'; statusControls['图标尺寸'].onchange();
assert.strictEqual(layouts['战斗'].elements.status.icon_size, 26);
sel = {{kind: 'element', name: 'power'}};
buildProps();
const statControls = {{}};
collect(props, statControls);
assert(statControls['字号']);
assert(!statControls['描边宽度']);
entityLayoutMode = true;
sel = {{kind: 'element', name: 'energy'}};
buildProps();
const counterControls = {{}};
function collectCounter(node) {{
  if (node.tag === 'label' && node.children[0])
    counterControls[node.textContent.trim()] = node.children[0];
  for (const child of node.children || []) collectCounter(child);
}}
collectCounter(props);
assert.deepStrictEqual(Object.keys(counterControls),
  ['位置 x', '位置 y', '图标尺寸', '数字偏移 x', '数字偏移 y', '字号']);
assert(!Object.keys(counterControls).some(label => label.includes('符号') || label.includes('加号') ||
                                                   label.includes('减号')));
counterControls['数字偏移 x'].value = '7'; counterControls['数字偏移 x'].onchange();
assert.deepStrictEqual(layouts['对局式神'].elements.energy.num_offset, [7, 0]);
sel = {{kind: 'element', name: 'countdown'}};
buildProps(); collectCounter(props);
assert.strictEqual(counterControls['数字偏移 x'].value, 2);
assert.strictEqual(layouts['对局式神'].elements.energy.num_offset[0], 7);
buildLists();
assert.deepStrictEqual(elems.children.map(x => x.textContent),
  ['等级', '卡图内窗', '力量', '生命', '战力', '护甲', '能量', '倒计时', '气绝倒计时']);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_layout_burst_signed_sample_request_without_dirty(tmp_path):
    """六类型卡牌内容提供带符号爆能样例，只刷新预览且不修改布局脏状态。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function cardField(name)",
        "function setCardField(name, value)",
        "function buildCardProps()",
        "function textRow(div, label, val, set)",
        "function numRowC(div, label, val, nonneg, set, extra = null, max = 9999999999, min = null)",
        "function selRow(div, label, opts, val, set, map = null)",
        "function selRowC(div, label, opts, val, set, map = null)",
        "async function refreshPreview()",
    ))
    driver = f"""
const assert = require('node:assert');
let entityLayoutMode = false, mechLayoutMode = false, cardLayoutMode = null;
let curType = '战斗', cardOverrides = {{}}, cDirty = false, dirty = false, scheduled = 0;
let formData = null;
const samples = {{'战斗': {{name: '样卡', level: 1, shikigami: '所属', description: ''}}}};
const layout = {{elements: {{burst: {{kind: 'burst', offset: [0, 55]}}}}, text_regions: {{}}}};
const layouts = {{'战斗': layout}};
const EVOLVE_TYPES = new Set(['战斗', '法术', '形态', '幻境']);
const NONNEG_TYPES = new Set(), FRAME_VARIANT_TYPES = new Set();
let layoutFrameVariant = 'norm', previewSeq = 0;
function typeLayout() {{ return layout; }}
function globalTypeLayout() {{ return layout; }}
function layoutForRender(value) {{ return value; }}
function deepCopy(value) {{ return JSON.parse(JSON.stringify(value)); }}
const statusEl = {{textContent: ''}};
function statInputs() {{ return []; }}
function markDirty() {{ dirty = true; }}
function schedulePreview() {{ scheduled++; }}
async function refreshEntityLayoutPreview() {{}}
async function refreshMechPreview() {{}}
async function handleLayoutPreviewResponse() {{}}
const requests = [];
async function fetch(url, options) {{ requests.push({{url, options}}); return {{ok: true}}; }}
function element(tag) {{ return {{tag, children: [], textContent: '', value: '',
  set innerHTML(value) {{ if (value === '') this.children = []; }},
  appendChild(child) {{ this.children.push(child); return child; }} }}; }}
const div = element('div');
const document = {{getElementById: () => div, createElement: element}};
let activeAsk = null;
{functions}
(async () => {{
  buildCardProps();
  const controls = {{}};
  function visit(node) {{
    if (node.tag === 'label' && node.children[0]) controls[node.textContent.trim()] = node.children[0];
    for (const child of node.children || []) visit(child);
  }}
  visit(div);
  assert(controls['爆能']);
  assert.strictEqual(controls['爆能'].max, 0);
  controls['爆能'].value = '2'; controls['爆能'].onchange();
  assert.strictEqual(cardOverrides['战斗'].burst, 0);
  controls['爆能'].value = '-10'; controls['爆能'].onchange();
  assert.strictEqual(cardOverrides['战斗'].burst, -10);
  assert.strictEqual(dirty, false);
  assert.strictEqual(scheduled, 2);
  await refreshPreview();
  assert.strictEqual(requests.length, 1);
  const body = JSON.parse(requests[0].options.body);
  assert.deepStrictEqual(body.card, {{burst: -10}});
  assert.deepStrictEqual(body.layout, layout);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_layout_entity_counter_samples_and_requests_without_dirty(tmp_path):
    """实体样例覆盖 none/energy/countdown、气绝与永久，切换样例不碰布局工作副本。"""
    script = _script()
    sample = _extract_js(script, "const entityLayoutSample = {") + ";"
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function buildCardProps()",
        "function numRowC(div, label, val, nonneg, set, extra = null, max = 9999999999, min = null)",
        "function selRowC(div, label, opts, val, set, map = null)",
        "function battleCheckbox(div, label, checked, set, disabled = false)",
        "async function refreshEntityLayoutPreview()",
    ))
    driver = f"""
const assert = require('node:assert');
let entityLayoutMode = true, cardLayoutMode = null, dirty = false, scheduled = 0, previewSeq = 0;
const layout = {{version: 2, elements: {{energy: {{kind: 'counter', pos: [82, 18]}},
  defeated: {{kind: 'counter', pos: [48, 66]}}}}, art_window: {{center: [48, 72]}}}};
const before = JSON.stringify(layout);
function typeLayout() {{ return layout; }}
function markDirty() {{ dirty = true; }}
function schedulePreview() {{ scheduled++; }}
async function handleLayoutPreviewResponse() {{}}
const requests = [];
async function fetch(url, options) {{ requests.push({{url, options}}); return {{ok: true}}; }}
function element(tag) {{ return {{tag, children: [], textContent: '', value: '', checked: false,
  disabled: false, className: '', style: {{}},
  set innerHTML(value) {{ if (value === '') this.children = []; }},
  appendChild(child) {{ this.children.push(child); return child; }} }}; }}
const div = element('div');
const document = {{getElementById: () => div, createElement: element}};
let activeAsk = null;
{sample}
{functions}
function control(label) {{
  let found = null;
  function visit(node) {{
    if (node.tag === 'label' && node.textContent.trim() === label) found = node.children[0];
    for (const child of node.children || []) visit(child);
  }}
  visit(div);
  return found;
}}
(async () => {{
  buildCardProps();
  assert(control('能量') && control('倒计时') && control('气绝') && control('永久'));
  assert.strictEqual(control('右上组件'), null);
  assert.strictEqual(control('永久').disabled, true);
  control('倒计时').checked = true; control('倒计时').onchange();
  assert.strictEqual(entityLayoutSample.countdown, 0);
  assert.strictEqual(entityLayoutSample.energy, null);
  assert.strictEqual(control('倒计时数值').disabled, false);
  assert.strictEqual(control('能量数值').disabled, true);
  control('倒计时数值').value = '2'; control('倒计时数值').onchange();
  assert.strictEqual(entityLayoutSample.countdown, 2);
  control('能量').checked = true; control('能量').onchange();
  assert.strictEqual(entityLayoutSample.energy, 0);
  assert.strictEqual(entityLayoutSample.countdown, null);
  assert.strictEqual(control('倒计时').checked, false);
  control('能量数值').value = '3'; control('能量数值').onchange();
  await refreshEntityLayoutPreview();
  let state = JSON.parse(requests[0].options.body).state;
  assert.strictEqual(state.energy, 3);
  assert.strictEqual(state.countdown, null);
  assert.strictEqual(state.defeated_countdown, null);
  const defeated = control('气绝');
  defeated.checked = true; defeated.onchange();
  assert.strictEqual(entityLayoutSample.defeated_countdown, 3);
  assert.strictEqual(control('永久').disabled, false);
  const permanent = control('永久');
  permanent.checked = true; permanent.onchange();
  await refreshEntityLayoutPreview();
  state = JSON.parse(requests[1].options.body).state;
  assert.strictEqual(state.energy, 3);
  assert.strictEqual(state.defeated_countdown, 'infinity');
  assert.strictEqual(JSON.stringify(layout), before);
  assert.strictEqual(dirty, false);
  control('能量').checked = false; control('能量').onchange();
  assert.strictEqual(entityLayoutSample.energy, null);
  assert.strictEqual(entityLayoutSample.countdown, null);
  assert.strictEqual(scheduled, 7);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_layout_preview_rechecks_seq_after_error_detail(tmp_path):
    """慢错误响应过期后不得覆盖布局状态文字。"""
    handler = _extract_js(_script(), "async function handleLayoutPreviewResponse(r, seq)")
    driver = f"""
const assert = require('node:assert');
let previewSeq = 1, cardLayoutMode = false, singleDirty = false, dirty = false;
const statusEl = {{textContent: '当前状态'}};
let releaseDetail;
const response = {{ok: false,
  json: () => new Promise(resolve => {{ releaseDetail = resolve; }})}};
{handler}
(async () => {{
  const pending = handleLayoutPreviewResponse(response, 1);
  previewSeq++;
  releaseDetail({{detail: '旧错误'}});
  await pending;
  assert.strictEqual(statusEl.textContent, '当前状态');
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_layout_preview_slow_success_rechecks_seq_and_defers_status(tmp_path):
    """慢成功响应在 blob/onload 过期时均丢弃；有效图片加载后才更新状态文字。"""
    handler = _extract_js(_script(), "async function handleLayoutPreviewResponse(r, seq)")
    driver = f"""
const assert = require('node:assert');
let previewSeq = 1, cardLayoutMode = false, singleDirty = false, dirty = false;
let entityLayoutMode = false;
const statusEl = {{textContent: '当前状态'}};
const currentImage = {{id: 'current'}};
let previewImg = currentImage, previewOffset = [7, 8], draws = 0;
const canvas = {{width: 20, height: 30, style: {{width: '20px', height: '30px'}}}};
const images = [], created = [], revoked = [];
class Image {{
  constructor() {{ this.naturalWidth = 64; this.naturalHeight = 96; images.push(this); }}
  set src(value) {{ this._src = value; }}
  get src() {{ return this._src; }}
}}
const URL = {{createObjectURL: blob => {{ created.push(blob); return 'blob:' + created.length; }},
             revokeObjectURL: url => revoked.push(url)}};
function draw() {{ draws++; }}
function successResponse(blob) {{
  return {{ok: true, headers: {{get: () => '1,2'}}, blob: async () => blob}};
}}
{handler}
(async () => {{
  let releaseBlob;
  const slow = {{ok: true, headers: {{get: () => '1,2'}},
    blob: () => new Promise(resolve => {{ releaseBlob = resolve; }})}};
  const pending = handleLayoutPreviewResponse(slow, 1);
  previewSeq++;
  releaseBlob({{id: 'stale-blob'}});
  await pending;
  assert.deepStrictEqual(created, []);
  assert.strictEqual(statusEl.textContent, '当前状态');
  assert.strictEqual(previewImg, currentImage);
  assert.deepStrictEqual(previewOffset, [7, 8]);
  assert.strictEqual(canvas.width, 20);

  previewSeq = 2;
  statusEl.textContent = '等待旧图片';
  await handleLayoutPreviewResponse(successResponse({{id: 'stale-onload'}}), 2);
  assert.strictEqual(statusEl.textContent, '等待旧图片');
  assert.deepStrictEqual(created, [{{id: 'stale-onload'}}]);
  previewSeq++;
  statusEl.textContent = '新请求状态';
  images[0].onload();
  assert.strictEqual(statusEl.textContent, '新请求状态');
  assert.strictEqual(previewImg, currentImage);
  assert.deepStrictEqual(previewOffset, [7, 8]);
  assert.strictEqual(canvas.width, 20);
  assert.deepStrictEqual(revoked, ['blob:1']);
  assert.strictEqual(draws, 0);

  previewSeq = 3;
  statusEl.textContent = '等待有效图片';
  await handleLayoutPreviewResponse(successResponse({{id: 'current'}}), 3);
  assert.strictEqual(statusEl.textContent, '等待有效图片');
  images[1].onload();
  assert.strictEqual(statusEl.textContent, '');
  assert.strictEqual(previewImg, images[1]);
  assert.deepStrictEqual(previewOffset, [1, 2]);
  assert.strictEqual(canvas.width, 64);
  assert.strictEqual(canvas.height, 96);
  assert.strictEqual(draws, 1);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_entity_state_is_temporary(tmp_path):
    """小卡默认取基础值，法术觉醒叠加永久数值；临时修改不写卡牌、不置脏。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function battleStyles(card)",
        "function makeEntityState(card)",
        "function setBattleEntityField(key, value)",
    ))
    driver = f"""
const assert = require('node:assert');
const ENTITY_LEVELS = [0, 1, 2, 3];
const LEVEL_COLOR_VALUES = new Set(['yellow', 'cyan', 'purple', 'red', 'blue', 'brown']);
const STAT_VALUE_COLOR_VALUES = new Set(['red', 'green', 'purple']);
const cards = {{shikigami: [{{name: '基础式神', power: 3, health: 4}},
  {{name: '极值式神', power: 9999999999, health: 9999999999}}], cards: []}};
let battleEntityState = null;
let cDirty = false;
let scheduled = 0;
function scheduleBattlePreview() {{ scheduled++; }}
{functions}
assert(battleStyles({{type: '式神'}}).includes('entity'));
assert(battleStyles({{type: '形态'}}).includes('entity'));
assert(battleStyles({{type: '法术', evolve: true}}).includes('entity'));
assert(!battleStyles({{type: '战斗'}}).includes('entity'));
const source = {{type: '法术', evolve: true, shikigami: '基础式神', 'power+': 2, 'health+': -1,
                level: 2, level_color: 'cyan', power: -2, health: 5.5,
                combat_power: 8, shield: 9, art_scale: 7, power_color: 'green'}};
const state = makeEntityState(source);
battleEntityState = state;
assert.deepStrictEqual([state.level, state.level_color, state.power, state.health,
                        state.combat_power, state.shield, state.art_scale],
                       [2, 'cyan', 5, 3, 0, 0, 1]);
assert.strictEqual(state.power_color, 'green');
assert.strictEqual(state.energy, null);
assert.strictEqual(state.countdown, null);
assert.strictEqual(state.defeated_countdown, null);
const fallback = makeEntityState({{type: '式神', level: 4, level_color: 'bad', power: 3, health: 4}});
assert.deepStrictEqual([fallback.level, fallback.level_color, fallback.power, fallback.health],
                       [1, 'yellow', 3, 4]);
assert.deepStrictEqual(makeEntityState({{type: '形态', shikigami: '基础式神', power: 2, health: 5}}).power, 2);
const awakenedForm = makeEntityState({{type: '形态', evolve: true, shikigami: '基础式神',
                                       power: 9, health: 9}});
assert.deepStrictEqual([awakenedForm.power, awakenedForm.health], [3, 4]);
const awakenedCombat = makeEntityState({{type: '战斗', evolve: true, shikigami: '基础式神',
                                         'power+': 9, 'shield+': 9}});
assert.deepStrictEqual([awakenedCombat.power, awakenedCombat.health], [3, 4]);
const negative = makeEntityState({{type: '法术', evolve: true, shikigami: '基础式神',
                                   'power+': -9, 'health+': -9}});
assert.deepStrictEqual([negative.power, negative.health], [0, 0]);
const capped = makeEntityState({{type: '法术', evolve: true, shikigami: '极值式神',
                                 'power+': 1, 'health+': 1}});
assert.deepStrictEqual([capped.power, capped.health], [9999999999, 9999999999]);
assert.strictEqual(makeEntityState({{type: '式神', level: 0}}).level, 0);
setBattleEntityField('power', 4);
assert(state.power === 4 && cDirty === false && scheduled === 1);
assert(source.power === -2 && source['power+'] === 2);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_portrait_subpreview_visibility_without_entity(tmp_path):
    """头像预览需扩展功能与头像框同时开启；衍生物和其他卡始终隐藏。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function isMainShikigami(card)",
        "function syncSubpreviews()",
        "async function cPreviewPortrait(withForm)",
    ))
    driver = f"""
const assert = require('node:assert');
const cSubpreviews = {{style: {{display: 'none'}}}};
const cPortraitImg = {{style: {{display: 'none'}}, removeAttribute() {{}}}};
const extOptions = {{marker: false}};
let formData = {{type: '式神'}};
let curProject = '项目', curCard = 'stem', requests = 0;
let cPortraitSeq = 0, cPortraitAppliedSeq = 0, cPortraitUrl = null;
const URL = {{createObjectURL: () => 'blob:new', revokeObjectURL() {{}}}};
function enc(value) {{ return value; }}
async function fetch() {{ requests++; return {{ok: true, blob: async () => ({{kind: 'png'}})}}; }}
{functions}
(async () => {{
  await cPreviewPortrait(false);
  assert.strictEqual(cPortraitImg.style.display, 'none');
  assert.strictEqual(cSubpreviews.style.display, 'none');
  assert.strictEqual(requests, 0);
  extOptions.marker = true;
  await cPreviewPortrait(false);
  assert.strictEqual(cPortraitImg.style.display, 'block');
  assert.strictEqual(cSubpreviews.style.display, 'flex');
  assert.strictEqual(requests, 1);
  formData.portrait = {{frame: false}};
  await cPreviewPortrait(true);
  assert.strictEqual(cPortraitImg.style.display, 'none');
  assert.strictEqual(cSubpreviews.style.display, 'none');
  assert.strictEqual(requests, 1);
  delete formData.portrait.frame;
  formData = {{type: '式神', shikigami: '基础'}};
  await cPreviewPortrait(true);
  assert.strictEqual(cPortraitImg.style.display, 'none');
  assert.strictEqual(cSubpreviews.style.display, 'none');
  formData = {{type: '形态'}};
  await cPreviewPortrait(true);
  assert.strictEqual(cSubpreviews.style.display, 'none');
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_preview_applies_latest_completed_response_during_continuous_edits(tmp_path):
    """连续编辑时显示最新已完成画面，仅逆序旧响应不得覆盖更新画面。"""
    script = _script()
    handler = _extract_js(script, "async function cHandlePreviewResponse(r, seq)")
    driver = f"""
const assert = require('node:assert');
let cPreviewSeq = 2, cPreviewAppliedSeq = 0, cPreviewUrl = 'blob:old';
const cPreviewImg = {{src: 'blob:old'}};
function setPreviewError() {{}}
const URL = {{createObjectURL: blob => blob, revokeObjectURL() {{}}}};
function success(url) {{ return {{ok: true, blob: async () => url}}; }}
{handler}
(async () => {{
  await cHandlePreviewResponse(success('blob:first'), 1);
  assert.strictEqual(cPreviewImg.src, 'blob:first');
  await cHandlePreviewResponse(success('blob:second'), 2);
  assert.strictEqual(cPreviewImg.src, 'blob:second');
  await cHandlePreviewResponse(success('blob:out-of-order'), 1);
  assert.strictEqual(cPreviewImg.src, 'blob:second');
  assert.strictEqual(cPreviewUrl, 'blob:second');
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_preview_success_clears_older_error_after_blob(tmp_path):
    """旧错误解析先完成时，新成功图落盘后仍须清除该错误。"""
    script = _script()
    handler = _extract_js(script, "async function cHandlePreviewResponse(r, seq)")
    driver = f"""
const assert = require('node:assert');
let cPreviewSeq = 2, cPreviewAppliedSeq = 0, cPreviewUrl = null;
const cPreviewImg = {{src: ''}}, cErrorEl = {{textContent: ''}};
function setPreviewError(channel, text) {{ cErrorEl.textContent = text; }}
const URL = {{createObjectURL: blob => blob, revokeObjectURL() {{}}}};
let releaseError, releaseBlob;
function parseErrorDetail() {{ return new Promise(resolve => {{ releaseError = resolve; }}); }}
{handler}
(async () => {{
  const oldError = cHandlePreviewResponse({{ok: false}}, 1);
  const newSuccess = cHandlePreviewResponse({{ok: true,
    blob: () => new Promise(resolve => {{ releaseBlob = resolve; }})}}, 2);
  releaseError(['旧错误']);
  await oldError;
  assert(cErrorEl.textContent.includes('旧错误'));
  releaseBlob('blob:new');
  await newSuccess;
  assert.strictEqual(cPreviewImg.src, 'blob:new');
  assert.strictEqual(cErrorEl.textContent, '');
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_ineligible_subpreview_invalidates_pending_blob(tmp_path):
    """主要式神变为衍生物时，等待中的旧头像 blob 不得重新回写。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function isMainShikigami(card)",
        "async function cPreviewPortrait(withForm)",
    ))
    driver = f"""
const assert = require('node:assert');
let cPortraitSeq = 0, cPortraitAppliedSeq = 0, cPortraitUrl = null;
const extOptions = {{marker: true}};
let formData = {{type: '式神'}}, curProject = '项目', curCard = 'stem';
const cPortraitImg = {{src: '', style: {{}}, removeAttribute() {{ this.src = ''; }}}};
const created = [];
const URL = {{createObjectURL: blob => {{ created.push(blob); return blob; }},
             revokeObjectURL() {{}}}};
function syncSubpreviews() {{}}
function enc(value) {{ return value; }}
let releasePortrait;
async function fetch() {{ return {{ok: true,
  blob: () => new Promise(resolve => {{ releasePortrait = resolve; }})}}; }}
{functions}
(async () => {{
  const oldPortrait = cPreviewPortrait(true);
  while (!releasePortrait) await Promise.resolve();
  formData = {{type: '式神', shikigami: '基础'}};
  await cPreviewPortrait(true);
  releasePortrait('blob:old-portrait');
  await oldPortrait;
  assert.strictEqual(cPortraitImg.src, '');
  assert.strictEqual(cPortraitUrl, null);
  assert.deepStrictEqual(created, []);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_preview_response_rechecks_seq_after_blob(tmp_path):
    """Blob 等待期间退出/清空后，旧成功响应不得回写图片、URL 或错误区。"""
    script = _script()
    handler = _extract_js(script, "async function cHandlePreviewResponse(r, seq)")
    driver = f"""
const assert = require('node:assert');
let cPreviewSeq = 1, cPreviewAppliedSeq = 0, cPreviewUrl = 'blob:current';
const cPreviewImg = {{src: 'blob:current', onload: null}};
const cErrorEl = {{textContent: '初始'}};
function setPreviewError() {{}}
const created = [];
const URL = {{createObjectURL: blob => {{ created.push(blob); return 'blob:stale'; }},
             revokeObjectURL() {{}}}};
let releaseBlob;
const response = {{ok: true, blob: () => new Promise(resolve => {{ releaseBlob = resolve; }})}};
{handler}
(async () => {{
  const pending = cHandlePreviewResponse(response, 1);
  cPreviewSeq++; cPreviewAppliedSeq = cPreviewSeq;  // 首次检查通过后退出/切卡/清空
  cErrorEl.textContent = '当前界面';
  releaseBlob({{png: 'stale'}});
  await pending;
  assert.strictEqual(cPreviewImg.src, 'blob:current');
  assert.strictEqual(cPreviewImg.onload, null);
  assert.strictEqual(cPreviewUrl, 'blob:current');
  assert.strictEqual(cErrorEl.textContent, '当前界面');
  assert.deepStrictEqual(created, []);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_preview_response_rechecks_seq_after_error_detail(tmp_path):
    """错误解析等待期间退出/清空后，旧错误响应不得回写共用预览界面。"""
    script = _script()
    handler = _extract_js(script, "async function cHandlePreviewResponse(r, seq)")
    driver = f"""
const assert = require('node:assert');
let cPreviewSeq = 2, cPreviewAppliedSeq = 0, cPreviewUrl = 'blob:current';
const cPreviewImg = {{src: 'blob:current', onload: null}};
const cErrorEl = {{textContent: '当前界面'}};
const created = [];
const URL = {{createObjectURL: blob => {{ created.push(blob); return 'blob:stale'; }},
             revokeObjectURL() {{}}}};
let releaseDetail;
async function parseErrorDetail() {{
  return new Promise(resolve => {{ releaseDetail = resolve; }});
}}
{handler}
(async () => {{
  const pending = cHandlePreviewResponse({{ok: false}}, 2);
  cPreviewSeq++; cPreviewAppliedSeq = cPreviewSeq;  // 首次检查通过后退出/切卡/清空
  releaseDetail(['旧错误']);
  await pending;
  assert.strictEqual(cPreviewImg.src, 'blob:current');
  assert.strictEqual(cPreviewImg.onload, null);
  assert.strictEqual(cPreviewUrl, 'blob:current');
  assert.strictEqual(cErrorEl.textContent, '当前界面');
  assert.deepStrictEqual(created, []);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_mouse_preview_frames_coalesce_latest_and_stay_independent(tmp_path):
    """鼠标编辑按通道合并到动画帧，执行时读取最新值且不取消其他通道。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "const mousePreviewFrames = {art: 0, portrait: 0}",
        "const mousePreviewBusy = {art: false, portrait: false}",
        "const mousePreviewQueued = {art: false, portrait: false}",
        "function scheduleMousePreview(channel)",
        "function flushMousePreview(channel)",
        "function afterMouseEdit(channel)",
    ))
    driver = f"""
const assert = require('node:assert');
let formData = {{type: '式神', artwork: {{images: [{{offset_x: 0}}]}}}};
let cDirty = false, notes = 0;
let cPreviewTimer = null;
const previews = [];
const document = {{getElementById: () => null}};
function noteEdit() {{ notes++; }}
function showFormErrors() {{}}
function validateCardJS() {{ return []; }}
function cPreviewForm(withPortrait) {{
  previews.push({{channel: 'art', x: formData.artwork.images[0].offset_x, withPortrait}});
}}
function cPreviewPortrait(withForm) {{ previews.push({{channel: 'portrait', withForm}}); }}
let nextFrame = 0;
const frames = new Map();
function requestAnimationFrame(fn) {{ const id = ++nextFrame; frames.set(id, fn); return id; }}
function cancelAnimationFrame(id) {{ frames.delete(id); }}
function runFrame(id) {{ const fn = frames.get(id); frames.delete(id); fn(); }}
let activeAsk = null;
{functions}
for (let i = 1; i <= 20; i++) {{
  formData.artwork.images[0].offset_x = i;
  afterMouseEdit('art');
}}
assert.strictEqual(frames.size, 1);
assert.strictEqual(previews.length, 0);
assert(cDirty && notes === 20);
runFrame(mousePreviewFrames.art);
assert.deepStrictEqual(previews, [{{channel: 'art', x: 20, withPortrait: false}}]);
assert.strictEqual(frames.size, 0);
afterMouseEdit('portrait');
scheduleMousePreview('art');
assert.strictEqual(frames.size, 2);
const artFrame = mousePreviewFrames.art;
flushMousePreview('portrait');
assert.strictEqual(frames.size, 1);
assert(frames.has(artFrame));
assert.deepStrictEqual(previews[1], {{channel: 'portrait', withForm: true}});
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_mouse_preview_drops_backlog_and_finishes_at_latest_position(tmp_path):
    """在途渲染期间合并连续操作，不排队回放轨迹，完成后补发最新状态。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "const mousePreviewFrames = {art: 0, portrait: 0}",
        "const mousePreviewBusy = {art: false, portrait: false}",
        "const mousePreviewQueued = {art: false, portrait: false}",
        "function scheduleMousePreview(channel)",
        "function flushMousePreview(channel)",
    ))
    driver = f"""
const assert = require('node:assert');
let x = 0;
const positions = [], pending = [];
function cPreviewForm() {{
  positions.push(x);
  return new Promise(resolve => pending.push(resolve));
}}
function cPreviewPortrait() {{}}
function requestAnimationFrame() {{ throw new Error('本测试直接刷新'); }}
function cancelAnimationFrame() {{}}
let activeAsk = null;
{functions}
async function settle() {{
  pending.shift()();
  await new Promise(resolve => setImmediate(resolve));
}}
(async () => {{
  x = 1; flushMousePreview('art');
  assert.deepStrictEqual(positions, [1]);
  for (x = 2; x <= 100; x++) flushMousePreview('art');
  assert.deepStrictEqual(positions, [1]);
  assert.strictEqual(pending.length, 1);
  await settle();
  assert.deepStrictEqual(positions, [1, 101]);
  x = 101; flushMousePreview('art');
  x = 102; flushMousePreview('art');
  await settle();
  assert.deepStrictEqual(positions, [1, 101, 102]);
  await settle();
  assert.deepStrictEqual(positions, [1, 101, 102]);
  assert.strictEqual(mousePreviewBusy.art, false);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_mouseup_flushes_only_the_active_drag_channels(tmp_path):
    """实际拖拽结束时取消待执行帧并立即最终预览，无拖拽的 mouseup 不刷新。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "const mousePreviewFrames = {art: 0, portrait: 0}",
        "const mousePreviewBusy = {art: false, portrait: false}",
        "const mousePreviewQueued = {art: false, portrait: false}",
        "function scheduleMousePreview(channel)",
        "function flushMousePreview(channel)",
        "function afterMouseEdit(channel)",
        "function bindArtMouse(img)",
    ))
    driver = f"""
const assert = require('node:assert');
let formData = {{type: '式神'}}, cDirty = false;
let cPreviewTimer = null;
const previews = [];
const document = {{getElementById: () => null}};
function noteEdit() {{}}
function showFormErrors() {{}}
function validateCardJS() {{ return []; }}
function cPreviewForm(withPortrait) {{ previews.push(['art', withPortrait]); }}
function cPreviewPortrait(withForm) {{ previews.push(['portrait', withForm]); }}
let nextFrame = 0;
const frames = new Map();
function requestAnimationFrame(fn) {{ const id = ++nextFrame; frames.set(id, fn); return id; }}
function cancelAnimationFrame(id) {{ frames.delete(id); }}
const windowListeners = {{}};
const window = {{addEventListener: (name, fn) => {{
  (windowListeners[name] ||= []).push(fn);
}}}};
function dispatchWindow(name, event) {{ for (const fn of windowListeners[name]) fn(event); }}
function artMouseChannel(img) {{
  return {{get: () => 0, set: () => afterMouseEdit(img.channel)}};
}}
function makeImage(channel) {{
  const listeners = {{}};
  return {{channel, listeners, naturalWidth: 100,
    addEventListener: (name, fn) => {{ listeners[name] = fn; }},
    getBoundingClientRect: () => ({{width: 100}})}};
}}
const artImg = makeImage('art'), cPortraitImg = makeImage('portrait');
let activeAsk = null;
{functions}
bindArtMouse(artImg);
bindArtMouse(cPortraitImg);
dispatchWindow('mouseup');
assert.deepStrictEqual(previews, []);
artImg.listeners.mousedown({{button: 0, clientX: 0, clientY: 0, preventDefault() {{}}}});
dispatchWindow('mouseup');
assert.deepStrictEqual(previews, []);
assert.strictEqual(frames.size, 0);
artImg.listeners.mousedown({{button: 0, clientX: 0, clientY: 0, preventDefault() {{}}}});
dispatchWindow('mousemove', {{clientX: 5, clientY: 5}});
assert.strictEqual(frames.size, 1);
dispatchWindow('mouseup');
assert.strictEqual(frames.size, 0);
assert.deepStrictEqual(previews, [['art', false]]);
previews.length = 0;
cPortraitImg.listeners.mousedown({{button: 0, clientX: 0, clientY: 0, preventDefault() {{}}}});
dispatchWindow('mousemove', {{clientX: 5, clientY: 5}});
assert.strictEqual(frames.size, 1);
dispatchWindow('mouseup');
assert.strictEqual(frames.size, 0);
assert.deepStrictEqual(previews, [['portrait', true]]);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_mouse_edit_coalesces_pending_normal_preview_without_losing_channels(tmp_path):
    """普通防抖未到期时鼠标编辑接管主卡与头像通道，每通道最终只请求一次。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function scheduleCardPreview()",
        "const mousePreviewFrames = {art: 0, portrait: 0}",
        "const mousePreviewBusy = {art: false, portrait: false}",
        "const mousePreviewQueued = {art: false, portrait: false}",
        "function scheduleMousePreview(channel)",
        "function flushMousePreview(channel)",
        "function afterMouseEdit(channel)",
    ))
    driver = f"""
const assert = require('node:assert');
let cPreviewTimer = null;
let formData = {{type: '式神', artwork: {{images: [{{offset_x: 7}}]}}}}, cDirty = false;
const previews = [];
const document = {{getElementById: () => null}};
function noteEdit() {{}}
function showFormErrors() {{}}
function validateCardJS() {{ return []; }}
function cPreviewForm() {{ previews.push('art'); }}
function cPreviewPortrait() {{ previews.push('portrait'); }}
let nextTimer = 0, nextFrame = 0;
const timers = new Map(), frames = new Map();
function setTimeout(fn) {{ const id = ++nextTimer; timers.set(id, fn); return id; }}
function clearTimeout(id) {{ timers.delete(id); }}
function requestAnimationFrame(fn) {{ const id = ++nextFrame; frames.set(id, fn); return id; }}
function cancelAnimationFrame(id) {{ frames.delete(id); }}
let activeAsk = null;
{functions}
scheduleCardPreview();
assert.strictEqual(timers.size, 1);
afterMouseEdit('art');
assert.strictEqual(timers.size, 0);
assert.strictEqual(frames.size, 2);
assert.deepStrictEqual(previews, []);
for (const id of [...frames.keys()]) {{
  const fn = frames.get(id); frames.delete(id); fn();
}}
assert.deepStrictEqual(previews.sort(), ['art', 'portrait']);
assert.strictEqual(timers.size, 0);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_normal_preview_debounce_refreshes_one_round(tmp_path):
    """纯普通输入在 300ms 后只刷新一轮主卡与头像。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function scheduleCardPreview()",
        "async function cPreviewProject()",
        "async function cPreviewForm(withPortrait = true)",
    ))
    driver = f"""
const assert = require('node:assert');
let cPreviewTimer = null;
let cPreviewSeq = 0, formData = {{type: '式神'}}, curProject = '项目', curCard = 'stem';
let portraits = 0, handled = 0;
let nextTimer = 0;
const timers = new Map(), delays = [];
function setTimeout(fn, delay) {{
  const id = ++nextTimer; timers.set(id, fn); delays.push(delay); return id;
}}
function clearTimeout(id) {{ timers.delete(id); }}
async function runTimer(id) {{
  const fn = timers.get(id); timers.delete(id); await fn();
}}
function enc(value) {{ return value; }}
function validateCardJS() {{ return []; }}
function cPreviewPortrait() {{ portraits++; }}
async function cHandlePreviewResponse() {{ handled++; }}
async function fetch() {{ return {{ok: true}}; }}
let activeAsk = null;
{functions}
(async () => {{
  scheduleCardPreview();
  scheduleCardPreview();
  assert.strictEqual(timers.size, 1);
  assert.strictEqual(handled + portraits, 0);
  await runTimer(cPreviewTimer);
  assert.deepStrictEqual([handled, portraits], [1, 1]);
  await cPreviewProject();
  assert.deepStrictEqual([handled, portraits], [2, 2]);
  assert.deepStrictEqual(delays, [300, 300]);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_select_card_rechecks_seq_after_json(tmp_path):
    """选卡只作废旧响应，不像清空选择那样主动清图；旧 A 不得覆盖已提交的 B 表单。"""
    select = _extract_js(_script(), "async function selectCard(stem, force = false)")
    driver = f"""
const assert = require('node:assert');
let curCard = null, curProject = '项目', curMech = null, formData = null, cardData = null;
let cDirty = false, mainShiki = null, neutralMode = false, selectSeq = 0;
let cPreviewSeq = 0, cPortraitSeq = 0;
let cPreviewAppliedSeq = 0, cPortraitAppliedSeq = 0;
let cards = {{shikigami: [], cards: []}}, builds = 0, previews = 0;
const cStatusEl = {{textContent: ''}};
const cPortraitImg = {{src: 'blob:old', style: {{display: 'block'}},
  removeAttribute() {{ this.src = ''; }}}};
let cPortraitUrl = 'blob:old', subpreviewSyncs = 0;
function syncSubpreviews() {{ subpreviewSyncs++; }}
const URL = {{revokeObjectURL() {{}}}};
function confirmDiscard() {{ return true; }}
function buildCardList() {{}}
function listErr() {{}}
function enc(value) {{ return value; }}
function deepCopy(value) {{ return JSON.parse(JSON.stringify(value)); }}
function resetUndo() {{}}
function syncCardFrameButtons() {{}}
function buildForm() {{ builds++; }}
function cPreviewProject() {{ previews++; }}
const pending = {{}};
async function fetch(url) {{
  const stem = url.endsWith('/A') ? 'A' : 'B';
  return {{ok: true, json: () => new Promise(resolve => {{ pending[stem] = resolve; }})}};
}}
let activeAsk = null;
{select}
(async () => {{
  const a = selectCard('A');
  await Promise.resolve();
  assert.strictEqual(cPortraitImg.style.display, 'block');
  assert.strictEqual(cPortraitImg.src, 'blob:old');
  assert.strictEqual(cPortraitUrl, 'blob:old');
  assert.strictEqual(subpreviewSyncs, 0);
  while (!pending.A) await Promise.resolve();
  const b = selectCard('B');
  while (!pending.B) await Promise.resolve();
  pending.B({{type: '形态', name: 'B', power: 2, health: 3}});
  await b;
  pending.A({{type: '形态', name: 'A', power: 9, health: 9}});
  await a;
  assert.strictEqual(curCard, 'B');
  assert.strictEqual(cardData.name, 'B');
  assert.strictEqual(formData.name, 'B');
  assert.strictEqual(formData.power, 2);
  assert.strictEqual(builds, 1);
  assert.strictEqual(previews, 1);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_clear_card_invalidates_pending_select_json(tmp_path):
    """慢 A 的 JSON 在清卡后完成时不得复活表单。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "async function selectCard(stem, force = false)",
        "const mousePreviewFrames = {art: 0, portrait: 0}",
        "function clearCard()",
    ))
    driver = f"""
const assert = require('node:assert');
let curCard = null, curProject = '项目', curMech = null, formData = null, cardData = null;
let cDirty = false, mainShiki = null, neutralMode = false, selectSeq = 0;
let cards = {{shikigami: [], cards: []}}, builds = 0, previews = 0;
const cStatusEl = {{textContent: ''}}, cErrorEl = {{textContent: ''}};
let cPreviewTimer = null, cPortraitTimer = null;
let cPreviewSeq = 0, cPortraitSeq = 0;
let cPreviewAppliedSeq = 0, cPortraitAppliedSeq = 0;
let cPreviewUrl = null, cPortraitUrl = null;
const cPreviewImg = {{removeAttribute() {{}}}};
const cPortraitImg = {{style: {{}}, removeAttribute() {{}}}};
const cSubpreviews = {{style: {{}}}};
const document = {{getElementById: () => ({{textContent: ''}})}};
const URL = {{revokeObjectURL() {{}}}};
function confirmDiscard() {{ return true; }}
function buildCardList() {{}}
function listErr() {{}}
function enc(value) {{ return value; }}
function deepCopy(value) {{ return JSON.parse(JSON.stringify(value)); }}
function clearTimeout() {{}}
function cancelAnimationFrame() {{}}
function resetUndo() {{}}
function syncCardFrameButtons() {{}}
function buildForm() {{ builds++; }}
function cPreviewProject() {{ previews++; }}
function syncSubpreviews() {{}}
let resolveA;
async function fetch() {{
  return {{ok: true, json: () => new Promise(resolve => {{ resolveA = resolve; }})}};
}}
let activeAsk = null;
{functions}
(async () => {{
  const a = selectCard('A');
  while (!resolveA) await Promise.resolve();
  clearCard();
  resolveA({{type: '形态', name: 'A', power: 9, health: 9}});
  await a;
  assert.strictEqual(curCard, null);
  assert.strictEqual(cardData, null);
  assert.strictEqual(formData, null);
  assert.strictEqual(builds, 0);
  assert.strictEqual(previews, 0);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_clear_card_cancels_mouse_preview_frames(tmp_path):
    """清卡取消主卡/头像旧帧并归零，随后两通道仍能独立合并和调度。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "const mousePreviewFrames = {art: 0, portrait: 0}",
        "const mousePreviewBusy = {art: false, portrait: false}",
        "const mousePreviewQueued = {art: false, portrait: false}",
        "function scheduleMousePreview(channel)",
        "function flushMousePreview(channel)",
        "function clearCard()",
    ))
    driver = f"""
const assert = require('node:assert');
let selectSeq = 0, curCard = 'old', cardData = {{}}, formData = {{}};
let cDirty = true;
let cPreviewTimer = null, cPortraitTimer = null;
let cPreviewSeq = 0, cPortraitSeq = 0;
let cPreviewAppliedSeq = 0, cPortraitAppliedSeq = 0;
let cPreviewUrl = null, cPortraitUrl = null;
const cPreviewImg = {{removeAttribute() {{}}}};
const cPortraitImg = {{style: {{}}, removeAttribute() {{}}}};
const cSubpreviews = {{style: {{}}}};
const cErrorEl = {{textContent: ''}};
const document = {{getElementById: () => ({{textContent: ''}})}};
const URL = {{revokeObjectURL() {{}}}};
function clearTimeout() {{}}
function resetUndo() {{}}
function syncCardFrameButtons() {{}}
const previews = [];
function cPreviewForm() {{ previews.push('art'); }}
function cPreviewPortrait() {{ previews.push('portrait'); }}
let nextFrame = 0;
const frames = new Map(), cancelled = [];
function requestAnimationFrame(fn) {{ const id = ++nextFrame; frames.set(id, fn); return id; }}
function cancelAnimationFrame(id) {{ cancelled.push(id); frames.delete(id); }}
let activeAsk = null;
{functions}
scheduleMousePreview('art');
scheduleMousePreview('art');
scheduleMousePreview('portrait');
assert.strictEqual(frames.size, 2);
clearCard();
assert.deepStrictEqual(cancelled, [1, 2]);
assert.strictEqual(frames.size, 0);
assert.deepStrictEqual(mousePreviewFrames, {{art: 0, portrait: 0}});
assert.deepStrictEqual(previews, []);
scheduleMousePreview('art');
scheduleMousePreview('art');
scheduleMousePreview('portrait');
assert.strictEqual(frames.size, 2);
for (const id of [...frames.keys()]) {{
  const fn = frames.get(id); frames.delete(id); fn();
}}
assert.deepStrictEqual(previews.sort(), ['art', 'portrait']);
assert.deepStrictEqual(mousePreviewFrames, {{art: 0, portrait: 0}});
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_preview_urls_released_on_replace_and_clear_without_onload(tmp_path):
    """主卡/头像连续两次换图均立即释放旧 URL，清卡释放最后一张，不依赖 onload。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function isMainShikigami(card)",
        "async function cHandlePreviewResponse(r, seq)",
        "async function cPreviewPortrait(withForm)",
        "function clearCard()",
    ))
    driver = f"""
const assert = require('node:assert');
let cPreviewSeq = 1, cPortraitSeq = 0, selectSeq = 0;
let cPreviewAppliedSeq = 0, cPortraitAppliedSeq = 0;
const mousePreviewFrames = {{art: 0, portrait: 0}};
function cancelAnimationFrame() {{}}
let cPreviewTimer = null, cPortraitTimer = null;
let cPreviewUrl = 'main-old', cPortraitUrl = 'portrait-old';
let curCard = 'stem', curProject = '项目', curMech = null, cardData = {{}}, formData = {{type: '式神'}};
const extOptions = {{marker: true}};
let cDirty = false;
const cPreviewImg = {{src: 'main-old', removeAttribute() {{}}}};
const cPortraitImg = {{src: 'portrait-old', style: {{}}, removeAttribute() {{}}}};
const cSubpreviews = {{style: {{}}}};
const cErrorEl = {{textContent: ''}};
function setPreviewError() {{}}
const revoked = [];
const URL = {{createObjectURL: blob => blob, revokeObjectURL: url => revoked.push(url)}};
function clearTimeout() {{}}
function syncSubpreviews() {{}}
function enc(value) {{ return value; }}
function resetUndo() {{}}
function syncCardFrameButtons() {{}}
const document = {{getElementById: () => ({{textContent: ''}})}};
let portraitRequests = 0;
async function fetch() {{ return {{ok: true, blob: async () => 'portrait-' + (++portraitRequests)}}; }}
function success(url) {{ return {{ok: true, blob: async () => url}}; }}
let activeAsk = null;
{functions}
const mainResponse = r => cHandlePreviewResponse(r, ++cPreviewSeq);
(async () => {{
  await mainResponse(success('main-1'));
  await mainResponse(success('main-2'));
  await cPreviewPortrait(true);
  await cPreviewPortrait(true);
  assert.deepStrictEqual(revoked, ['main-old', 'main-1', 'portrait-old', 'portrait-1']);
  clearCard();
  assert.deepStrictEqual(revoked,
    ['main-old', 'main-1', 'portrait-old', 'portrait-1', 'portrait-2', 'main-2']);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_select_card_and_clear_cancel_main_and_portrait_channels(tmp_path):
    """切卡保留正常表单；清卡取消主卡/头像通道并释放全部 objectURL。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "async function selectCard(stem, force = false)",
        "function clearCard()",
    ))
    driver = f"""
const assert = require('node:assert');
let curCard = 'old', curProject = '项目', curMech = null, formData = {{name: '旧'}};
let cardData = null, cDirty = true, mainShiki = null, neutralMode = false, selectSeq = 0;
let cards = {{shikigami: [], cards: []}};
const cStatusEl = {{textContent: ''}}, cErrorEl = {{textContent: ''}};
const removed = [];
const cPreviewImg = {{removeAttribute() {{ removed.push('main'); }}}};
const cPortraitImg = {{style: {{}}, removeAttribute() {{ removed.push('portrait'); }}}};
const cSubpreviews = {{style: {{display: 'flex'}}}};
let cPreviewUrl = 'blob:main', cPortraitUrl = 'blob:portrait';
let cPreviewSeq = 1, cPortraitSeq = 2;
let cPreviewAppliedSeq = 0, cPortraitAppliedSeq = 0;
const mousePreviewFrames = {{art: 0, portrait: 0}};
function cancelAnimationFrame() {{}}
let cPreviewTimer = 11, cPortraitTimer = 12;
const cancelled = [], revoked = [];
function clearTimeout(id) {{ cancelled.push(id); }}
const URL = {{revokeObjectURL(url) {{ revoked.push(url); }}}};
const elements = {{}};
const document = {{getElementById: id => elements[id] || (elements[id] = {{textContent: ''}})}};
function confirmDiscard() {{ return true; }}
function enc(value) {{ return value; }}
function buildCardList() {{}}
function listErr() {{}}
function deepCopy(value) {{ return JSON.parse(JSON.stringify(value)); }}
function resetUndo() {{}}
function syncCardFrameButtons() {{}}
function buildForm() {{}}
function cPreviewProject() {{}}
function syncSubpreviews() {{}}
async function fetch() {{ return {{ok: true, json: async () => ({{type: '形态', name: '新', power: 3, health: 4}})}}; }}
let activeAsk = null;
{functions}
(async () => {{
  await selectCard('new');
  assert.strictEqual(formData.power, 3);
  assert.strictEqual(formData.health, 4);
  assert.strictEqual(cDirty, false);
  clearCard();
  assert.strictEqual(formData, null);
  assert.deepStrictEqual(cancelled, [11, 12]);
  assert.strictEqual(cPreviewTimer, null);
  assert.strictEqual(cPortraitTimer, null);
  assert.deepStrictEqual(revoked, ['blob:portrait', 'blob:main']);
  assert.strictEqual(cPreviewSeq, 3);
  assert.strictEqual(cPortraitSeq, 4);
  assert.strictEqual(cPreviewUrl, null);
  assert.strictEqual(cPortraitUrl, null);
  assert.deepStrictEqual(removed, ['main', 'portrait']);
  assert.strictEqual(cSubpreviews.style.display, 'none');
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_entity_mode_entry_exit_branches_are_removed(tmp_path):
    """常驻子预览不再保留实体模式及进入/返回分支。"""
    import json
    script = _script()
    driver = f"""
const assert = require('node:assert');
const source = {json.dumps(script)};
for (const obsolete of ['entityMode', 'enterEntityMode', 'exitEntityMode', 'buildEntityForm'])
  assert(!source.includes(obsolete), obsolete);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_battle_entity_controls_cover_counters_without_dirtying(tmp_path):
    """对局页提供右上状态、气绝与永久控件，所有修改只调度临时预览。"""
    script = _script()
    declarations = (
        "function setBattleEntityField(key, value)",
        "function battleSelectRow(div, label, options, value, set)",
        "function battleNumberRow(div, label, value, set, min = null, id = null, disabled = false,\n                         max = 9999999999)",
        "function battleScaleRow(div)",
        "function battleColorOptions()",
        "function battleColorField(style, field, value)",
        "function battleCheckbox(div, label, checked, set, disabled = false)",
        "function battleCounterMode()",
        "function setBattleCounterMode(mode)",
        "function setBattleDefeated(enabled)",
        "function setBattlePermanent(permanent)",
        "function buildBattleForm()",
    )
    functions = "\n".join(_extract_js(script, decl) for decl in declarations)
    driver = f"""
const assert = require('node:assert');
const ENTITY_LEVELS = [0, 1, 2, 3], LEVEL_COLORS = [['yellow', '黄']];
const EVOLVE_TYPES = new Set(['战斗', '法术', '形态', '幻境']);
const STATS_BY_TYPE = {{'形态': ['power', 'health']}};
const STAT_MATRIX = {{'形态': {{power: '力量', health: '生命'}}}};
const STAT_VALUE_COLORS = [['white', '白'], ['red', '红']];
let battleStyle = 'entity', battleCardState = {{type: '形态'}};
let battleEntityState = {{level: 2, level_color: 'yellow', power: 3, health: 4,
  combat_power: 0, shield: 0, art_scale: 1, energy: null, countdown: null,
  defeated_countdown: null, power_color: null, health_color: null,
  combat_power_color: null, shield_color: null}};
let cDirty = true, mDirty = true, scheduled = 0;
function scheduleBattlePreview() {{ scheduled++; }}
function setBattleCardField() {{ throw new Error('小卡控件不得写大卡'); }}
function element(tag) {{
  return {{tag, children: [], style: {{}}, textContent: '', value: '', checked: false,
    disabled: false, className: '',
    set innerHTML(value) {{ if (value === '') this.children = []; this._innerHTML = value; }},
    get innerHTML() {{ return this._innerHTML || ''; }},
    appendChild(child) {{ this.children.push(child); return child; }} }};
}}
const form = element('div');
const document = {{createElement: element, getElementById: () => form}};
{functions}
buildBattleForm();
function control(label, id = null) {{
  let found = null;
  function visit(node) {{
    if (node.tag === 'label' && node.textContent.trim() === label) found = node.children[0];
    for (const child of node.children || []) visit(child);
  }}
  visit(form);
  if (id) {{
    function byId(node) {{ if (node.id === id) found = node; for (const c of node.children || []) byId(c); }}
    byId(form);
  }}
  return found;
}}
const mode = control('右上状态');
mode.value = 'energy'; mode.onchange();
assert.strictEqual(battleEntityState.energy, 0);
assert.strictEqual(battleEntityState.countdown, null);
const energy = control('右上数值', 'b-counter-value');
energy.value = '4'; energy.onchange();
assert.strictEqual(battleEntityState.energy, 4);
energy.value = '10000000000'; energy.onchange();
assert.strictEqual(battleEntityState.energy, 9999999999);
assert.strictEqual(energy.max, 9999999999);
mode.value = 'countdown'; mode.onchange();
const countdown = control('右上数值', 'b-counter-value');
countdown.value = '0'; countdown.onchange();
assert.strictEqual(battleEntityState.countdown, 0);
const defeated = control('气绝');
defeated.checked = true; defeated.onchange();
assert.strictEqual(battleEntityState.defeated_countdown, 3);
const permanent = control('永久');
permanent.checked = true; permanent.onchange();
assert.strictEqual(battleEntityState.defeated_countdown, 'infinity');
assert.strictEqual(control('气绝倒计时', 'b-defeated-value').disabled, true);
permanent.checked = false; permanent.onchange();
const defeatedValue = control('气绝倒计时', 'b-defeated-value');
assert.strictEqual(defeatedValue.min, 0);
defeatedValue.value = '0'; defeatedValue.onchange();
assert.strictEqual(battleEntityState.defeated_countdown, 0);
assert.strictEqual(cDirty, true && mDirty, true);
assert(scheduled >= 4);
console.log('OK');
"""
    _run_node(tmp_path, driver)


def test_preview_duo_frame_override_empty_slots(client):
    """布局 tab 样卡开 duo_frame：无项目上下文不注入 _duo，渲染空槽位框（与关闭不同图）。"""
    from bwpdiy.render.layout import load_layouts, get_type_layout
    tl = get_type_layout(load_layouts(client.app.state.assets_dir), "协战")
    on = client.post("/api/preview", json={"type": "协战", "layout": tl,
                                           "card": {"duo_frame": True}})
    assert on.status_code == 200 and on.headers["content-type"] == "image/png"
    off = client.post("/api/preview", json={"type": "协战", "layout": tl})
    assert off.status_code == 200 and on.content != off.content


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_battle_styles_follow_card_type(tmp_path):
    styles = _extract_js(_script(), "function battleStyles(card)")
    driver = f"""
const assert = require('node:assert');
{styles}
assert.deepStrictEqual(battleStyles({{type: '式神'}}), ['entity']);
assert.deepStrictEqual(battleStyles({{type: '式神', shikigami: '白狼'}}), ['entity']);
assert.deepStrictEqual(battleStyles({{type: '战斗'}}), ['card']);
assert.deepStrictEqual(battleStyles({{type: '形态'}}), ['card', 'entity']);
assert.deepStrictEqual(battleStyles({{type: '法术', evolve: true}}), ['card', 'entity']);
assert.deepStrictEqual(battleStyles(null), []);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_battle_entry_rebuilds_temporary_state_without_dirtying(tmp_path):
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function battleStyles(card)",
        "function makeEntityState(card)",
        "function setBattleCardField(key, value)",
        "function setBattleEntityField(key, value)",
        "function enterBattlePreview()",
        "function leaveBattlePreview()",
    ))
    driver = f"""
const assert = require('node:assert');
const ENTITY_LEVELS = [0, 1, 2, 3];
const LEVEL_COLOR_VALUES = new Set(['yellow', 'cyan']);
const STAT_VALUE_COLOR_VALUES = new Set(['red', 'green', 'purple']);
let cards = {{shikigami: [], cards: []}};
let curProject = '项目', curCard = '形态-stem', curMech = null;
let formData = {{type: '形态', name: '烈', level: 2, level_color: 'cyan',
                power: 3, health: 4, power_color: 'green'}};
let cDirty = true, mDirty = true;
let battleStyle = null, battleCardState = null, battleEntityState = null;
let battleActive = false, battleSession = 0, battlePreviewTimer = null;
let battlePreviewSeq = 0, battlePreviewAppliedSeq = 0, battlePreviewUrl = null;
let scheduled = 0;
const elements = {{
  'b-status': {{textContent: ''}}, 'b-error': {{textContent: ''}},
  'b-preview': {{src: 'blob:old', removeAttribute() {{ this.src = ''; }}}},
  'b-btn-export': {{disabled: false}},
}};
const document = {{getElementById: id => elements[id]}};
const URL = {{revokeObjectURL() {{}}}};
function deepCopy(value) {{ return JSON.parse(JSON.stringify(value)); }}
function buildBattleStyles() {{}}
function buildBattleForm() {{}}
function clearTimeout() {{}}
function scheduleBattlePreview() {{ scheduled++; }}
{functions}
enterBattlePreview();
assert.strictEqual(battleStyle, 'card');
assert.strictEqual(battleCardState.burst, 0);
assert.strictEqual(battleCardState.status, null);
assert.strictEqual(battleCardState.power_color, 'green');
assert.deepStrictEqual(battleEntityState.power_color, 'green');
assert.strictEqual(battleEntityState.energy, null);
assert.strictEqual(battleEntityState.countdown, null);
assert.strictEqual(battleEntityState.defeated_countdown, null);
assert.notStrictEqual(battleCardState, formData);
setBattleCardField('burst', 3);
setBattleCardField('status', 'shown');
setBattleEntityField('power', 9);
assert.strictEqual(formData.burst, undefined);
assert.strictEqual(formData.status, undefined);
assert.strictEqual(formData.power, 3);
assert.strictEqual(cDirty, true);
assert.strictEqual(mDirty, true);
assert.strictEqual(scheduled, 4);
leaveBattlePreview();
assert.strictEqual(battleActive, false);
assert.strictEqual(elements['b-preview'].src, '');
formData.name = '未保存的新名字';
enterBattlePreview();
assert.strictEqual(battleCardState.name, '未保存的新名字');
assert.strictEqual(battleCardState.burst, 0);
assert.strictEqual(battleEntityState.power, 3);
assert.strictEqual(curCard, '形态-stem');
assert.strictEqual(cDirty, true && mDirty, true);
curMech = '机制'; formData = null;
enterBattlePreview();
assert(elements['b-status'].textContent.includes('请先'));
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_battle_card_status_control_and_preview_request(tmp_path):
    """大卡特殊状态只修改临时状态，预览请求携带所选状态。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function setBattleCardField(key, value)",
        "function battleSelectRow(div, label, options, value, set)",
        "function battleNumberRow(div, label, value, set, min = null, id = null, disabled = false,\n                         max = 9999999999)",
        "function buildBattleForm()",
        "function battleRequest(style, project, stem, card, state)",
    ))
    driver = f"""
const assert = require('node:assert');
const ENTITY_LEVELS = [0, 1, 2, 3], LEVEL_COLORS = [['yellow', '黄']];
const EVOLVE_TYPES = new Set(['战斗', '法术', '形态', '幻境']);
const STATS_BY_TYPE = {{'战斗': []}}, STAT_MATRIX = {{'战斗': {{}}}};
let battleStyle = 'card', battleEntityState = null, scheduled = 0;
let battleCardState = {{type: '战斗', name: '测试', level: 1, level_color: 'yellow',
  burst: 0, status: null}};
function scheduleBattlePreview() {{ scheduled++; }}
function setBattleEntityField() {{ throw new Error('大卡控件不得写小卡'); }}
function element(tag) {{
  return {{tag, children: [], style: {{}}, textContent: '', value: '', selected: false,
    set innerHTML(value) {{ if (value === '') this.children = []; }},
    appendChild(child) {{ this.children.push(child); return child; }} }};
}}
const form = element('div');
const document = {{createElement: element, getElementById: () => form}};
const enc = encodeURIComponent;
{functions}
buildBattleForm();
let statusControl = null, burstControl = null;
function visit(node) {{
  const label = node.tag === 'label' ? node.textContent.trim() : '';
  if (label === '特殊状态') statusControl = node.children[0];
  if (label === '爆能') burstControl = node.children[0];
  for (const child of node.children || []) visit(child);
}}
visit(form);
assert(statusControl, '大卡缺少特殊状态控件');
assert(burstControl, '大卡缺少爆能控件');
assert.strictEqual(burstControl.max, 0);
burstControl.value = '3'; burstControl.onchange();
assert.strictEqual(battleCardState.burst, 0);
burstControl.value = '-3'; burstControl.onchange();
assert.strictEqual(battleCardState.burst, -3);
assert.deepStrictEqual(statusControl.children.map(o => [o.value, o.textContent]),
  [['', '无'], ['bless', '加护'], ['eclipse', '蚀印'], ['bond', '缘结'],
   ['curse', '诅咒'], ['radiance', '天晖'], ['nightmare', '梦魇'],
   ['eternal', '无始无终'], ['endless', '无穷无尽'], ['unused', '未使用'],
   ['multi_status', '多状态'], ['shown', '已展示']]);
assert.strictEqual(statusControl.children[0].selected, true);
statusControl.value = 'shown'; statusControl.onchange();
assert.strictEqual(battleCardState.status, 'shown');
assert.strictEqual(scheduled, 3);
let request = null;
function fetch(url, options) {{ request = {{url, options}}; return {{ok: true}}; }}
battleRequest('card', '项目', '战斗-stem', battleCardState, null);
assert.strictEqual(request.url, '/api/projects/%E9%A1%B9%E7%9B%AE/cards/%E6%88%98%E6%96%97-stem/preview');
assert.strictEqual(JSON.parse(request.options.body).card.status, 'shown');
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_battle_slow_response_export_and_leave_are_safe(tmp_path):
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function battleRequest(style, project, stem, card, state)",
        "async function handleBattlePreviewResponse(r, seq, session)",
        "async function exportBattlePreview()",
        "function leaveBattlePreview()",
    ))
    driver = f"""
const assert = require('node:assert');
let battleActive = true, battleSession = 4, battleStyle = 'entity';
let battlePreviewTimer = null, battlePreviewSeq = 2, battlePreviewAppliedSeq = 0;
let battlePreviewUrl = 'blob:old';
let battleCardState = {{type: '形态', name: '烈:/山?'}};
let battleEntityState = {{power: 3}};
let curProject = '项目', curCard = 'stem';
const image = {{src: 'blob:old', removeAttribute() {{ this.src = ''; }}}};
const status = {{textContent: ''}}, error = {{textContent: ''}}, button = {{disabled: false}};
const document = {{getElementById: id => ({{
  'b-preview': image, 'b-status': status, 'b-error': error, 'b-btn-export': button,
}})[id], createElement: () => ({{click() {{ downloads.push({{href: this.href,
  download: this.download}}); }}}})}};
const downloads = [], created = [];
const URL = {{createObjectURL: blob => {{ created.push(blob); return 'blob:new'; }},
             revokeObjectURL() {{}}}};
function clearTimeout() {{}}
function deepCopy(value) {{ return JSON.parse(JSON.stringify(value)); }}
function enc(value) {{ return value; }}
async function parseErrorDetail() {{ return ['失败']; }}
const requests = [];
async function fetch(url, options) {{
  requests.push({{url, options}});
  return {{ok: true, blob: async () => ({{png: 'new'}})}};
}}
{functions}
(async () => {{
  let release;
  const slow = {{ok: true, blob: () => new Promise(resolve => {{ release = resolve; }})}};
  const pending = handleBattlePreviewResponse(slow, 2, 4);
  leaveBattlePreview();
  release({{png: 'stale'}});
  await pending;
  assert.strictEqual(image.src, '');
  assert.deepStrictEqual(created, []);

  battleActive = true; battleSession = 5; battleStyle = 'entity';
  battleCardState = {{type: '形态', name: '烈:/山?'}};
  battleEntityState = {{power: 3}};
  battlePreviewAppliedSeq = 0;
  image.src = 'blob:valid';
  await handleBattlePreviewResponse({{ok: false}}, 3, 5);
  assert.strictEqual(image.src, 'blob:valid');
  assert(error.textContent.includes('失败'));

  const exporting = exportBattlePreview();
  await Promise.resolve();
  leaveBattlePreview();
  await exporting;
  assert.deepStrictEqual(downloads, []);
  assert.strictEqual(requests[0].url, '/api/entity-preview');
  const body = JSON.parse(requests[0].options.body);
  assert.deepStrictEqual(body, {{project: '项目', card: {{type: '形态', name: '烈:/山?'}},
                                state: {{power: 3}}}});
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_battle_same_session_out_of_order_success_keeps_newest(tmp_path):
    script = _script()
    handler = _extract_js(script, "async function handleBattlePreviewResponse(r, seq, session)")
    driver = f"""
const assert = require('node:assert');
let battleActive = true, battleSession = 7;
let battlePreviewAppliedSeq = 0, battlePreviewUrl = 'blob:old';
const image = {{src: 'blob:old'}}, error = {{textContent: ''}};
const document = {{getElementById: id => id === 'b-preview' ? image : error}};
const created = [], revoked = [];
const URL = {{createObjectURL: blob => {{ created.push(blob.png); return 'blob:' + blob.png; }},
             revokeObjectURL: url => revoked.push(url)}};
{handler}
function slowSuccess(png) {{
  let release;
  const response = {{ok: true, blob: () => new Promise(resolve => {{ release = resolve; }})}};
  return {{response, release: () => release({{png}})}};
}}
(async () => {{
  const older = slowSuccess('older'), newer = slowSuccess('newer');
  const oldPending = handleBattlePreviewResponse(older.response, 1, 7);
  const newPending = handleBattlePreviewResponse(newer.response, 2, 7);
  newer.release();
  await newPending;
  assert.strictEqual(image.src, 'blob:newer');
  older.release();
  await oldPending;
  assert.strictEqual(image.src, 'blob:newer');
  assert.strictEqual(battlePreviewUrl, 'blob:newer');
  assert.deepStrictEqual(created, ['newer']);
  assert.deepStrictEqual(revoked, ['blob:old']);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_battle_navigation_integrates_hash_entry_guards_and_return(tmp_path):
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function battleStyles(card)",
        "function makeEntityState(card)",
        "function enterBattlePreview()",
        "function leaveBattlePreview()",
        "function showTab(name)",
        "async function tryShowTab(name)",
    ))
    main = (EDITOR_HTML.parent / "editor-main.js").read_text(encoding="utf-8")
    startup = "\n".join(line for line in main.splitlines()
                        if line.startswith("if (location.hash"))
    assert startup.count("showTab") == 2
    driver = f"""
const assert = require('node:assert');
const ENTITY_LEVELS = [0, 1, 2, 3];
const LEVEL_COLOR_VALUES = new Set(['yellow', 'cyan']);
const STAT_VALUE_COLOR_VALUES = new Set(['red', 'green', 'purple']);
function classList(active = false) {{
  const values = new Set(active ? ['active'] : []);
  return {{contains: name => values.has(name),
    toggle: (name, on) => {{ if (on) values.add(name); else values.delete(name); }}}};
}}
const navtabs = ['cards', 'battle', 'layout'].map(tab =>
  ({{dataset: {{tab}}, classList: classList(tab === 'cards')}}));
const pages = Object.fromEntries(['cards', 'battle', 'layout'].map(tab =>
  ['tab-' + tab, {{id: 'tab-' + tab, classList: classList(tab === 'cards')}}]));
const elements = {{...pages,
  'b-status': {{textContent: ''}}, 'b-error': {{textContent: ''}},
  'b-preview': {{src: '', removeAttribute() {{ this.src = ''; }}}},
  'b-btn-export': {{disabled: true}},
}};
const document = {{
  getElementById: id => elements[id],
  querySelectorAll: selector => selector === '.navtab' ? navtabs
    : (selector === '.tabpage' ? Object.values(pages) : []),
}};
const location = {{hash: '#battle'}};
const history = {{replaceState: (a, b, hash) => {{ location.hash = hash; }}}};
const extOptions = {{layout: false, marker: true}};
const URL = {{revokeObjectURL() {{}}}};
let cards = {{shikigami: [], cards: []}};
let curProject = '项目', curCard = '形态-stem', curMech = null;
let formData = {{type: '形态', name: '未保存形态', level: 2, level_color: 'cyan',
                power: 3, health: 4}};
let cDirty = true, mDirty = false, dirty = false, singleDirty = false;
let cardLayoutMode = null;
let battleStyle = null, battleCardState = null, battleEntityState = null;
let battleActive = false, battleSession = 0, battlePreviewTimer = null;
let battlePreviewSeq = 0, battlePreviewAppliedSeq = 0, battlePreviewUrl = null;
let battleExporting = false, scheduled = 0, allowLeave = false;
const prompts = [];
function deepCopy(value) {{ return JSON.parse(JSON.stringify(value)); }}
function clearTimeout() {{}}
function buildBattleStyles() {{}}
function buildBattleForm() {{}}
function scheduleBattlePreview() {{ scheduled++; }}
function captureLayoutSnapshot() {{}}
function layoutBoot() {{}}
function buildForm() {{}}
function scheduleCardPreview() {{}}
function exitCardLayout() {{ throw new Error('本用例不进入单卡布局分支'); }}
async function sessionConfirm(message) {{ prompts.push(message); return allowLeave; }}
{functions}
{startup}
(async () => {{
  assert.strictEqual(battleActive, true);
  assert.strictEqual(battleCardState.name, '未保存形态');
  assert.notStrictEqual(battleCardState, formData);
  const originalForm = formData;
  await tryShowTab('cards');
  assert.strictEqual(battleActive, false);
  assert.strictEqual(formData, originalForm);
  assert.strictEqual(formData.name, '未保存形态');
  assert.strictEqual(curCard, '形态-stem');
  assert.strictEqual(cDirty, true);

  curMech = '共享机制'; formData = null; mDirty = true;
  await tryShowTab('battle');
  assert.strictEqual(battleActive, false);
  assert.strictEqual(prompts.length, 1);
  assert(prompts[0].includes('卡牌/机制'));
  allowLeave = true;
  await tryShowTab('battle');
  assert.strictEqual(battleActive, true);
  assert(elements['b-status'].textContent.includes('请先'));
  await tryShowTab('cards');

  showTab('layout');
  dirty = true; allowLeave = false;
  await tryShowTab('battle');
  assert.strictEqual(battleActive, false);
  assert.strictEqual(pages['tab-layout'].classList.contains('active'), true);
  assert.strictEqual(prompts.length, 3);
  assert(prompts[2].includes('布局'));
  allowLeave = true;
  await tryShowTab('battle');
  assert.strictEqual(battleActive, true);
  assert.strictEqual(pages['tab-battle'].classList.contains('active'), true);
  assert.strictEqual(curCard, '形态-stem');
  assert.strictEqual(cDirty, true && mDirty, true);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_battle_card_level_zero_is_omitted_for_preview_and_export(tmp_path):
    """大卡等级 0 在渲染副本中删 level；小卡 state.level=0 仍原样提交。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function battleRequest(style, project, stem, card, state)",
        "async function handleBattlePreviewResponse(r, seq, session)",
        "async function battlePreview()",
        "async function exportBattlePreview()",
    ))
    driver = f"""
const assert = require('node:assert');
let battleActive = true, battleSession = 1, battleStyle = 'card';
let battleCardState = {{type: '战斗', name: '斩', level: 0, burst: 2}};
let battleEntityState = {{level: 0}};
let curProject = '项目', curCard = 'stem';
let battlePreviewSeq = 0, battlePreviewAppliedSeq = 0, battlePreviewUrl = null;
let battleExporting = false;
const image = {{src: ''}}, error = {{textContent: ''}}, button = {{disabled: false}};
const document = {{getElementById: id => ({{
  'b-preview': image, 'b-error': error, 'b-btn-export': button,
}})[id], createElement: () => ({{click() {{}}}})}};
const URL = {{createObjectURL: () => 'blob:new', revokeObjectURL() {{}}}};
function deepCopy(value) {{ return JSON.parse(JSON.stringify(value)); }}
function enc(value) {{ return value; }}
function setTimeout() {{}}
const requests = [];
async function fetch(url, options) {{
  requests.push({{url, options}});
  return {{ok: true, blob: async () => ({{png: 'ok'}})}};
}}
{functions}
(async () => {{
  await battlePreview();
  await exportBattlePreview();
  assert.strictEqual(requests.length, 2);
  for (const request of requests) {{
    const card = JSON.parse(request.options.body).card;
    assert.strictEqual('level' in card, false);
    assert.strictEqual(card.burst, 2);
  }}
  assert.strictEqual(battleCardState.level, 0);
  battleStyle = 'entity';
  await battlePreview();
  const entityBody = JSON.parse(requests[2].options.body);
  assert.strictEqual(entityBody.state.level, 0);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_battle_export_style_switch_cancels_download_and_unlocks(tmp_path):
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function battleRequest(style, project, stem, card, state)",
        "async function exportBattlePreview()",
    ))
    driver = f"""
const assert = require('node:assert');
let battleActive = true, battleSession = 1, battleStyle = 'card';
let battleCardState = {{type: '形态', name: '烈'}}, battleEntityState = {{}};
let curProject = '项目', curCard = 'stem', battleExporting = false;
const error = {{textContent: ''}}, button = {{disabled: false}};
const downloads = [];
const document = {{getElementById: id => id === 'b-error' ? error : button,
  createElement: () => ({{click() {{ downloads.push(this.download); }}}})}};
const URL = {{createObjectURL: () => 'blob:new', revokeObjectURL() {{}}}};
function deepCopy(value) {{ return JSON.parse(JSON.stringify(value)); }}
function enc(value) {{ return value; }}
function setTimeout() {{}}
let resolveFirst, requests = 0;
function fetch() {{
  requests++;
  if (requests === 1) return new Promise(resolve => {{ resolveFirst = resolve; }});
  return Promise.resolve({{ok: true, blob: async () => ({{png: 'second'}})}});
}}
{functions}
(async () => {{
  const first = exportBattlePreview();
  while (!resolveFirst) await Promise.resolve();
  battleStyle = 'entity';
  resolveFirst({{ok: true, blob: async () => ({{png: 'first'}})}});
  assert.strictEqual(await first, false);
  assert.deepStrictEqual(downloads, []);
  assert.strictEqual(battleExporting, false);
  assert.strictEqual(await exportBattlePreview(), true);
  assert.deepStrictEqual(downloads, ['烈_对局.png']);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


def test_battle_page_structure_and_card_library_migration():
    html = EDITOR_HTML.read_text(encoding="utf-8")
    assert 'data-tab="battle"' in html and 'id="tab-battle"' in html
    assert '<input type="checkbox" id="ext-marker"> 扩展功能' in html
    main = (EDITOR_HTML.parent / "editor-main.js").read_text(encoding="utf-8")
    assert "location.hash === '#battle' && extOptions.marker" in main
    assert 'id="c-entity"' not in html
    scripts = [chunk.split('"', 1)[0] for chunk in html.split('<script src="')[1:]]
    assert scripts == ["editor-core.js", "editor-cards.js", "editor-battle.js",
                       "editor-mech.js", "editor-layout.js", "editor-main.js"]
    cards = (EDITOR_HTML.parent / "editor-cards.js").read_text(encoding="utf-8")
    for obsolete in ("appendEntityForm", "exportEntity", "statColorSelect",
                     "scheduleEntityPreview", "c-entity"):
        assert obsolete not in cards
    assert "levelColorRow" not in cards


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_battle_migration_keeps_marker_level_zero_without_color_control(tmp_path):
    level_row = _extract_js(_script(), "function levelRow(div)")
    driver = f"""
const assert = require('node:assert');
let formData = {{level: 1, level_color: 'cyan'}}, edits = 0;
function afterEdit() {{ edits++; }}
function element(tag) {{ return {{tag, children: [], textContent: '', value: '',
  appendChild(child) {{ this.children.push(child); return child; }} }}; }}
const div = element('div');
const document = {{createElement: element}};
{level_row}
levelRow(div);
assert.strictEqual(div.children.length, 1);
assert.strictEqual(div.children[0].children.length, 1);
const select = div.children[0].children[0];
assert.deepStrictEqual(select.children.map(option => option.value), ['0', '1', '2', '3']);
select.value = '0'; select.onchange();
assert.strictEqual(formData.level, undefined);
assert.strictEqual(formData.level_color, 'cyan');
select.value = '2'; select.onchange();
assert.strictEqual(formData.level, 2);
assert.strictEqual(edits, 2);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_extension_controls_battle_tab_and_returns_to_cards(tmp_path):
    apply = _extract_js(_script(), "function applyExtOptions()")
    driver = f"""
const assert = require('node:assert');
const extOptions = {{layout: true, marker: false}};
let cardLayoutMode = false, formData = null, mechForm = null;
const shown = [];
const styles = {{}};
const elements = {{
  'ext-layout': {{checked: false}}, 'ext-marker': {{checked: false}},
  'tab-layout': {{classList: {{contains: () => false}}}},
  'tab-battle': {{classList: {{contains: () => true}}}},
}};
const document = {{
  getElementById: id => elements[id],
  querySelector: selector => {{
    const el = {{style: {{}}}};
    styles[selector] = el.style;
    return el;
  }},
}};
function saveExtOptions() {{}}
function showTab(name) {{ shown.push(name); }}
function exitCardLayout() {{}}
function buildForm() {{}}
function buildMechForm() {{}}
function cPreviewPortrait() {{}}
{apply}
applyExtOptions();
assert.strictEqual(styles['.navtab[data-tab="battle"]'].display, 'none');
assert.deepStrictEqual(shown, ['cards']);
extOptions.marker = true;
applyExtOptions();
assert.strictEqual(styles['.navtab[data-tab="battle"]'].display, '');
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_portrait_inputs_follow_marker_and_frame(tmp_path):
    build = _extract_js(_script(), "function buildForm()")
    driver = f"""
const assert = require('node:assert');
let activeAsk = null, cDirty = false;
let formData = {{type: '式神', name: '测试', level: 1, artwork: {{images: [{{}}]}}}};
const extOptions = {{marker: false, layout: false}};
const artRows = [], checks = [];
function element(tag) {{ return {{tag, children: [], style: {{}}, textContent: '', value: '',
  set innerHTML(value) {{ if (value === '') this.children = []; }},
  appendChild(child) {{ this.children.push(child); return child; }} }}; }}
const div = element('div');
const document = {{getElementById: () => div, createElement: element}};
function syncCardFrameButtons() {{}}
function infoRow() {{}}
function textRow() {{}}
function versionRows() {{}}
function levelRow() {{}}
function factionRow() {{}}
function shikigamiRow() {{}}
function numRowC() {{}}
function artRow(div, label, val, set, pval, pset) {{ if (pset) artRows.push({{label, pset}}); }}
function isMainShikigami() {{ return true; }}
function rarityOptions() {{ return ['R']; }}
function selRowC() {{}}
function checkRowC(div, label, checked, set) {{ checks.push({{label, set}}); }}
function showFormErrors() {{}}
function validateCardJS() {{ return []; }}
function afterEdit(rebuild) {{ if (rebuild) buildForm(); }}
function undoAll() {{}}
function undoLast() {{}}
function saveCard() {{}}
function openExport() {{}}
function exportPortrait() {{}}
const EVOLVE_TYPES = new Set(['战斗', '法术', '形态', '幻境']);
const NONNEG_TYPES = new Set(['式神', '形态', '幻境']);
const FACTIONS = ['红莲'];
const STATS_BY_TYPE = {{式神: ['power', 'health']}};
const STAT_MATRIX = {{式神: {{power: '力量', health: '生命'}}}};
{build}
buildForm();
assert.strictEqual(artRows.length, 0);
extOptions.marker = true;
buildForm();
assert.strictEqual(artRows.length, 4);
formData.portrait = {{frame: false}};
artRows.length = 0;
buildForm();
assert.strictEqual(artRows.length, 0);
const frame = checks.find(row => row.label === '头像框');
assert(frame);
delete formData.portrait.frame;
frame.set(false);
assert.strictEqual(formData.portrait.frame, false);
assert.strictEqual(artRows.length, 0);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_layout_status_sample_select_only_changes_preview(tmp_path):
    build = _extract_js(_script(), "function buildCardProps()")
    driver = f"""
const assert = require('node:assert');
let entityLayoutMode = false, mechLayoutMode = false, cardLayoutMode = null;
let curType = '战斗', scheduled = 0, dirty = false;
const samples = {{战斗: {{name: '样卡', level: 1}}}};
const cardOverrides = {{}};
const controls = [];
function element(tag) {{ return {{tag, children: [], style: {{}}, textContent: '', value: '',
  set innerHTML(value) {{ if (value === '') this.children = []; }},
  appendChild(child) {{ this.children.push(child); return child; }} }}; }}
const div = element('div');
const document = {{getElementById: () => div, createElement: element}};
function cardField(name) {{
  const ov = cardOverrides[curType] || {{}};
  return name in ov ? ov[name] : (samples[curType] || {{}})[name];
}}
function setCardField(name, value) {{
  (cardOverrides[curType] = cardOverrides[curType] || {{}})[name] = value;
  scheduled++;
}}
function schedulePreview() {{ scheduled++; }}
function textRow() {{}}
function selRow() {{}}
function numRowC() {{}}
function selRowC(div, label, opts, val, set) {{ controls.push({{label, opts, val, set}}); }}
function statInputs() {{ return []; }}
const EVOLVE_TYPES = new Set(['战斗', '法术', '形态', '幻境']);
const NONNEG_TYPES = new Set(['式神', '形态', '幻境']);
let activeAsk = null;
{build}
buildCardProps();
const status = controls.find(row => row.label === '特殊状态');
assert(status);
assert.deepStrictEqual(status.opts, ['', 'bless', 'eclipse', 'bond', 'curse', 'radiance',
  'nightmare', 'eternal', 'endless', 'unused', 'multi_status', 'shown']);
assert.strictEqual(status.val, '');
status.set('shown');
assert.strictEqual(cardOverrides['战斗'].status, 'shown');
status.set('');
assert.strictEqual(cardOverrides['战斗'].status, null);
assert.strictEqual(dirty, false);
console.log('OK');
"""
    _run_node(tmp_path, driver)


def test_auto_id_editor_static_contract():
    cards = (EDITOR_HTML.parent / "editor-cards.js").read_text(encoding="utf-8")
    main = (EDITOR_HTML.parent / "editor-main.js").read_text(encoding="utf-8")
    assert "checkRowC(div, '衍生牌'" not in cards
    assert "payload.id = res.id" in cards
    assert "formData.id = res.id" in cards and "cardData.id = res.id" in cards
    assert "params.set('token'" in cards
    for field in ("shikigami", "shikigami1", "shikigami2"):
        assert f"params.set('{field}'" in cards
    assert "/meta" in cards and "loadCards(null, false)" in cards
    assert "c-new-proj').onclick = async () => {\n  if (!await confirmDiscard()) return;" in cards
    assert "pDirty" in main
    naming = _extract_js(cards, "async function confirmFallbackNaming()")
    assert "id 未填写" not in naming


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_project_id_dirty_included_in_unified_unsaved_check(tmp_path):
    has_unsaved = _extract_js(_script(), "function hasUnsavedChanges()")
    driver = f"""
const assert = require('node:assert');
let dirty = false, singleDirty = false, cDirty = false, mDirty = false, pDirty = true;
{has_unsaved}
assert.strictEqual(hasUnsavedChanges(), true);
pDirty = false;
assert.strictEqual(hasUnsavedChanges(), false);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
@pytest.mark.parametrize("change_id", [False, True])
def test_upload_response_merges_id_by_field_and_preserves_other_edits(tmp_path, change_id):
    script = _script()
    build = _extract_js(script, "function buildForm()")
    ensure_art = _extract_js(script, "function ensureArtFirst(data = formData)")
    save = _extract_js(script, "async function saveCard()")
    driver = f"""
const assert = require('node:assert');
const changeId = {str(change_id).lower()};
const uploadId = changeId ? '01' : '';
let activeAsk = null, curProject = 'P', curCard = 'A', curMech = null;
let selectSeq = 0, contentRev = 0, cDirty = false;
let formData = {{type: '战斗', name: '斩', id: uploadId, shikigami: '甲', token: true,
  level: 1, rarity: 'R', description: '', artwork: {{images: [{{offset_x: 7}}]}}}};
let cardData = {{id: '', shikigami: '旧所属', artwork: {{images: [{{offset_x: 3}}]}}}};
const cStatusEl = {{textContent: ''}};
const extOptions = {{marker: false, layout: false}};
function element(tag) {{ return {{tag, children: [], style: {{}}, textContent: '', value: '',
  set innerHTML(value) {{ if (value === '') this.children = []; }},
  appendChild(child) {{ this.children.push(child); return child; }} }}; }}
const div = element('div');
const document = {{getElementById: () => div, createElement: element}};
function syncCardFrameButtons() {{}}
function infoRow() {{}}
function textRow() {{}}
function versionRows() {{}}
function levelRow() {{}}
function shikigamiRow() {{}}
function numRowC() {{}}
function artRow() {{}}
function isMainShikigami() {{ return false; }}
function rarityOptions() {{ return ['R']; }}
function selRowC() {{}}
function checkRowC() {{}}
function showFormErrors() {{}}
function validateCardJS() {{ return []; }}
function undoAll() {{}}
function undoLast() {{}}
function openExport() {{}}
function askBusy() {{ return false; }}
function storageBusy() {{ return false; }}
function guiDebug() {{}}
async function confirmFallbackNaming() {{ return true; }}
function enc(value) {{ return value; }}
function deepCopy(value) {{ return JSON.parse(JSON.stringify(value)); }}
function resetUndo() {{}}
async function loadCards() {{}}
let metadataRefreshes = 0;
async function loadProjectIds() {{ metadataRefreshes++; }}
let resolveFetch;
const requests = [];
function fetch(url, options) {{
  requests.push({{url, options}});
  return new Promise(resolve => {{ resolveFetch = resolve; }});
}}
function scheduleCardPreview() {{}}
function cPreviewProject() {{}}
const EVOLVE_TYPES = new Set(['战斗']);
const NONNEG_TYPES = new Set();
const STATS_BY_TYPE = {{战斗: []}};
const STAT_MATRIX = {{战斗: {{}}}};
{ensure_art}
{build}
{save}
function findFileInput(node) {{
  if (node.type === 'file') return node;
  for (const child of node.children) {{ const found = findFileInput(child); if (found) return found; }}
  return null;
}}
(async () => {{
  buildForm();
  const input = findFileInput(div);
  input.files = [{{name: 'a.png', size: 1, type: 'image/png'}}];
  const pending = input.onchange();
  while (!resolveFetch) await Promise.resolve();
  if (changeId) formData.id = '02';
  formData.description = '上传期间仅编辑其他字段';
  formData.token = false;
  formData.shikigami = '在途所属';
  contentRev++;
  cDirty = true;
  resolveFetch({{ok: true, json: async () => ({{path: '10510101.png', id: '10510101'}})}});
  await pending;
  assert.strictEqual(metadataRefreshes, 1);
  const expectedId = changeId ? '02' : '10510101';
  assert.strictEqual(formData.id, expectedId);
  assert.strictEqual(formData.description, '上传期间仅编辑其他字段');
  assert.strictEqual(formData.token, false);
  assert.strictEqual(formData.shikigami, '在途所属');
  assert.strictEqual(cDirty, true);
  assert.deepStrictEqual(formData.artwork.images[0],
    {{offset_x: 7, path: '10510101.png'}});
  assert.deepStrictEqual(cardData, {{id: '10510101', token: true, shikigami: '甲',
    artwork: {{images: [{{offset_x: 3, path: '10510101.png'}}]}}}});
  assert.ok(requests[0].url.includes(changeId ? 'id=01' : 'id='));

  fetch = async (url, options) => {{
    requests.push({{url, options}});
    return {{ok: true, json: async () => ({{stem: 'A', updated: [], id: '10510101'}})}};
  }};
  assert.strictEqual(await saveCard(), true);
  const nextSave = JSON.parse(requests[1].options.body);
  assert.strictEqual(nextSave.id, expectedId);
  assert.strictEqual(nextSave.token, false);
  assert.strictEqual(nextSave.shikigami, '在途所属');
  assert.strictEqual(nextSave.artwork.images[0].path, '10510101.png');
  assert.strictEqual(metadataRefreshes, 2);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_project_save_response_preserves_later_edits(tmp_path):
    script = _script()
    save = _extract_js(script, "async function saveProjectId()")
    discard = _extract_js(script, "async function confirmDiscard()")
    driver = f"""
const assert = require('node:assert');
let curProject = 'P';
let projectData = {{id: '052', release_date: '20261231'}};
let savedProjectData = {{id: '051', release_date: '20261230'}};
let pDirty = true, projectContentRev = 0, cDirty = false, mDirty = false, metadataRefreshes = 0;
const cStatusEl = {{textContent: ''}};
function askBusy() {{ return false; }}
function storageBusy() {{ return false; }}
function enc(value) {{ return value; }}
function deepCopy(value) {{ return JSON.parse(JSON.stringify(value)); }}
function showFormErrors() {{}}
function validDateStr() {{ return true; }}
async function sessionConfirm() {{ return true; }}
async function loadProjectIds() {{ metadataRefreshes++; }}
let resolveFetch;
const requests = [];
function fetch(url, options) {{
  requests.push({{url, options}});
  return new Promise(resolve => {{ resolveFetch = resolve; }});
}}
{save}
{discard}
(async () => {{
  const pending = saveProjectId();
  while (!resolveFetch) await Promise.resolve();
  assert.deepStrictEqual(JSON.parse(requests[0].options.body),
    {{id: '052', release_date: '20261231'}});
  projectData.id = '053';
  projectData.release_date = '20270102';
  projectContentRev++;
  pDirty = true;
  resolveFetch({{ok: true, json: async () => ({{id: '052', release_date: '20261231'}})}});
  await pending;
  assert.strictEqual(metadataRefreshes, 1);
  assert.deepStrictEqual(projectData, {{id: '053', release_date: '20270102'}});
  assert.deepStrictEqual(savedProjectData, {{id: '052', release_date: '20261231'}});
  assert.strictEqual(pDirty, true);
  assert.ok(cStatusEl.textContent.includes('仍未保存'));
  assert.strictEqual(await confirmDiscard(), true);
  assert.deepStrictEqual(projectData, {{id: '052', release_date: '20261231'}});
  assert.strictEqual(pDirty, false);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_project_rename_uses_unified_dirty_guard(tmp_path):
    handler = _extract_js(_script(), "document.getElementById('c-ren-proj').onclick = async () =>")
    driver = f"""
const assert = require('node:assert');
const button = {{}};
const document = {{getElementById: () => button}};
let curProject = 'P', curCard = null, cDirty = false, pDirty = true;
let guards = 0;
const requests = [];
async function ask() {{ return {{text: 'Q'}}; }}
function rejectReservedProjectName() {{ return false; }}
async function confirmDiscard() {{ guards++; return false; }}
async function sessionConfirm() {{ throw new Error('应使用统一检查'); }}
function enc(value) {{ return value; }}
async function fetch(url) {{ requests.push(url); return {{ok: true}}; }}
function listErr() {{}}
async function loadProjects() {{}}
{handler}
(async () => {{
  await button.onclick();
  assert.strictEqual(guards, 1);
  assert.deepStrictEqual(requests, []);
  assert.strictEqual(curProject, 'P');
  assert.strictEqual(pDirty, true);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_reselect_current_project_enters_project_editor(tmp_path):
    select = _extract_js(_script(), "async function selectProject(p)")
    driver = f"""
const assert = require('node:assert');
let curProject = 'P', curCard = 'A', curMech = null, formData = {{id: '1'}}, cardData = {{}};
let projectData = {{id: '051'}}, savedProjectData = {{id: '051'}}, pDirty = false;
let mainShiki = '甲', neutralMode = true;
let guards = 0, cleared = 0, built = 0;
const metaLoads = [], cardLoads = [];
async function confirmDiscard() {{ guards++; return true; }}
function exitMech() {{ curMech = null; }}
function clearCard() {{ cleared++; curCard = null; formData = null; cardData = null; }}
function listErr() {{}}
function buildProjectList() {{ built++; }}
async function loadProjectMeta(project) {{ metaLoads.push(project); }}
async function loadCards(stem, selectFirst) {{ cardLoads.push([stem, selectFirst]); }}
{select}
(async () => {{
  await selectProject('P');
  assert.strictEqual(guards, 1);
  assert.strictEqual(cleared, 1);
  assert.strictEqual(curCard, null);
  assert.strictEqual(formData, null);
  assert.deepStrictEqual(metaLoads, ['P']);
  assert.deepStrictEqual(cardLoads, [[null, false]]);
  assert.strictEqual(mainShiki, null);
  assert.strictEqual(neutralMode, false);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_project_list_sorts_and_shows_ids(tmp_path):
    build = _extract_js(_script(), "function buildProjectList()")
    driver = f"""
const assert = require('node:assert');
let projects = ['无编号', '乙', '甲'], projectIds = {{甲: '051', 乙: '052', 无编号: ''}};
let curProject = '甲';
function element(tag) {{ return {{tag, children: [], style: {{}}, textContent: '', className: '',
  set innerHTML(value) {{ if (value === '') this.children = []; }},
  appendChild(child) {{ this.children.push(child); return child; }} }}; }}
const list = element('div'), sections = element('div');
const document = {{getElementById: id => id === 'c-projects' ? list : sections, createElement: element}};
function fitListHeight() {{}}
{build}
buildProjectList();
assert.deepStrictEqual(list.children.map(item => item.children[0].textContent), ['甲', '乙', '无编号']);
const withId = list.children[0].children[0];
assert.strictEqual(withId.children.length, 1);
assert.strictEqual(withId.children[0].textContent, '(051)');
assert.strictEqual(withId.children[0].className, 'meta');
assert.strictEqual(list.children[1].children[0].children[0].textContent, '(052)');
assert.strictEqual(list.children[2].children[0].children.length, 0);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_project_id_refresh_does_not_reset_card_selection(tmp_path):
    script = _script()
    build = _extract_js(script, "function buildProjectList()")
    load = _extract_js(script, "async function loadProjectIds()")
    driver = f"""
const assert = require('node:assert');
let projects = ['甲'], projectIds = {{甲: '051'}}, curProject = '甲', projectIdsSeq = 0;
let curCard = 'A', formData = {{id: '未重置'}}, cardData = {{id: '基准'}};
function element(tag) {{ return {{tag, children: [], style: {{}}, textContent: '', className: '',
  set innerHTML(value) {{ if (value === '') this.children = []; }},
  appendChild(child) {{ this.children.push(child); return child; }} }}; }}
const list = element('div'), sections = element('div');
const document = {{getElementById: id => id === 'c-projects' ? list : sections, createElement: element}};
function fitListHeight() {{}}
function listErr() {{}}
async function fetch(url) {{
  assert.strictEqual(url, '/api/projects/meta');
  return {{ok: true, json: async () => ({{甲: '052'}})}};
}}
{build}
{load}
(async () => {{
  await loadProjectIds();
  assert.deepStrictEqual(projectIds, {{甲: '052'}});
  assert.strictEqual(curCard, 'A');
  assert.strictEqual(formData.id, '未重置');
  assert.strictEqual(cardData.id, '基准');
  assert.strictEqual(list.children[0].children[0].children[0].textContent, '(052)');
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_project_form_release_date_shares_dirty_revision(tmp_path):
    build = _extract_js(_script(), "function buildForm()")
    driver = f"""
const assert = require('node:assert');
let activeAsk = null, curProject = 'P', curMech = null, formData = null;
let projectData = {{id: '051', release_date: '20261231'}}, pDirty = false, projectContentRev = 0;
const cStatusEl = {{textContent: ''}};
const rows = [];
function element(tag) {{ return {{tag, children: [], style: {{}}, textContent: '',
  set innerHTML(value) {{ if (value === '') this.children = []; }},
  appendChild(child) {{ this.children.push(child); return child; }} }}; }}
const div = element('div');
const document = {{getElementById: () => div, createElement: element}};
function syncCardFrameButtons() {{}}
function saveProjectId() {{}}
function textRow(div, label, value, set) {{ rows.push({{label, value, set}}); }}
{build}
buildForm();
const date = rows.find(row => row.label.includes('发布日期'));
assert(date);
assert.strictEqual(date.value, '20261231');
date.set('20270101');
rows.find(row => row.label.includes('项目 ID')).set('052');
assert.strictEqual(projectData.release_date, '20270101');
assert.strictEqual(projectData.id, '052');
assert.strictEqual(pDirty, true);
assert.strictEqual(projectContentRev, 2);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_new_project_submit_includes_release_date(tmp_path):
    handler = _extract_js(_script(), "document.getElementById('c-new-proj').onclick = async () =>")
    driver = f"""
const assert = require('node:assert');
const button = {{}};
const document = {{getElementById: () => button}};
let curProject = null, cDirty = false, pDirty = false;
async function confirmDiscard() {{ return true; }}
async function ask() {{ return {{text: 'P', id: '051', release_date: '20261231'}}; }}
function rejectReservedProjectName() {{ return false; }}
function listErr() {{}}
async function loadProjects() {{}}
const requests = [];
async function fetch(url, options) {{
  requests.push({{url, options}});
  return {{ok: true}};
}}
{handler}
(async () => {{
  await button.onclick();
  assert.strictEqual(requests.length, 1);
  assert.deepStrictEqual(JSON.parse(requests[0].options.body),
    {{name: 'P', id: '051', release_date: '20261231'}});
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_new_project_ask_has_release_date_input(tmp_path):
    ask = _extract_js(_script(), "function ask(")
    driver = f"""
const assert = require('node:assert');
function element(tag) {{ return {{tag, children: [], style: {{}}, textContent: '', value: '',
  set innerHTML(value) {{ if (value === '') this.children = []; }},
  appendChild(child) {{ this.children.push(child); child.parent = this; return child; }},
  focus() {{}}, select() {{}}}};
}}
const box = element('div'), slot = element('div'), home = element('div');
const document = {{createElement: element,
  getElementById: id => id === 'c-ask' ? box : id === 'c-ask-home' ? home : slot}};
function beginAsk() {{ return true; }}
function endAsk() {{}}
{ask}
(async () => {{
  const pending = ask({{title: '新项目', target: 'slot', withId: true}});
  assert.strictEqual(box.children.length, 5);
  const name = box.children[1], id = box.children[2], release = box.children[3];
  assert.ok(release.placeholder.includes('YYYYMMDD'));
  name.value = 'P'; id.value = '051'; release.value = '20261231';
  box.children[4].children[0].onclick();
  assert.deepStrictEqual(await pending,
    {{text: 'P', sel: null, id: '051', release_date: '20261231'}});
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_project_save_allows_blank_id_with_release_date(tmp_path):
    save = _extract_js(_script(), "async function saveProjectId()")
    driver = f"""
const assert = require('node:assert');
let curProject = 'P', projectData = {{id: '', release_date: '20260102'}};
let savedProjectData = {{id: '', release_date: ''}}, pDirty = true, projectContentRev = 0;
const cStatusEl = {{textContent: ''}};
function askBusy() {{ return false; }}
function storageBusy() {{ return false; }}
function validDateStr() {{ return true; }}
function enc(value) {{ return value; }}
function showFormErrors() {{}}
async function loadProjectIds() {{}}
const requests = [];
async function fetch(url, options) {{
  requests.push({{url, options}});
  return {{ok: true, json: async () => ({{id: '', release_date: '20260102'}})}};
}}
{save}
(async () => {{
  await saveProjectId();
  assert.deepStrictEqual(JSON.parse(requests[0].options.body),
    {{id: '', release_date: '20260102'}});
  assert.deepStrictEqual(savedProjectData, {{id: '', release_date: '20260102'}});
  assert.strictEqual(pDirty, false);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_save_stops_when_selection_changes_during_project_id_refresh(tmp_path):
    save = _extract_js(_script(), "async function saveCard()")
    driver = f"""
const assert = require('node:assert');
let selectSeq = 0, contentRev = 0, curProject = 'P', curCard = 'A';
let formData = {{name: 'A'}}, cardData = null, cDirty = true;
const cStatusEl = {{textContent: ''}};
let resolveSave, resolveRefresh, reloads = 0, undoResets = 0;
function askBusy() {{ return false; }}
function storageBusy() {{ return false; }}
function guiDebug() {{}}
function validateCardJS() {{ return []; }}
async function confirmFallbackNaming() {{ return true; }}
function deepCopy(value) {{ return JSON.parse(JSON.stringify(value)); }}
function enc(value) {{ return value; }}
function fetch() {{ return new Promise(resolve => {{ resolveSave = resolve; }}); }}
function loadProjectIds() {{ return new Promise(resolve => {{ resolveRefresh = resolve; }}); }}
function showFormErrors() {{}}
function resetUndo() {{ undoResets++; }}
async function loadCards() {{ reloads++; }}
const document = {{getElementById: () => null}};
{save}
(async () => {{
  const pending = saveCard();
  while (!resolveSave) await Promise.resolve();
  resolveSave({{ok: true, json: async () => ({{stem: 'A', updated: [], id: '10510101'}})}});
  while (!resolveRefresh) await Promise.resolve();
  selectSeq++; curCard = null; cDirty = true;
  resolveRefresh();
  assert.strictEqual(await pending, true);
  assert.strictEqual(reloads, 0);
  assert.strictEqual(undoResets, 0);
  assert.strictEqual(cDirty, true);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_new_card_handlers_stop_after_refresh_selection_change(tmp_path):
    script = _script()
    handlers = "\n".join(_extract_js(script, decl) for decl in (
        "document.getElementById('c-new-card').onclick = async () =>",
        "document.getElementById('c-new-shiki').onclick = async () =>",
    ))
    driver = f"""
const assert = require('node:assert');
const buttons = {{}};
const document = {{getElementById: id => buttons[id] = {{}}}};
let curProject = 'P', curCard = 'A', mainShiki = null, selectSeq = 0;
let resolveRefresh;
const loads = [];
async function confirmDiscard() {{ return true; }}
async function askNewCard() {{ return {{name: '卡', type: '战斗', shiki: {{}}}}; }}
async function ask() {{ return {{text: '式神'}}; }}
function sanitizeStem(value) {{ return value; }}
function uniqueStem(value) {{ return value; }}
function skeleton(type, name) {{ return {{type, name}}; }}
function rejectReservedProjectName() {{ return false; }}
function enc(value) {{ return value; }}
function listErr() {{}}
async function fetch() {{ return {{ok: true}}; }}
function loadProjectIds() {{ return new Promise(resolve => {{ resolveRefresh = resolve; }}); }}
async function loadCards(stem) {{ loads.push(stem); }}
{handlers}
(async () => {{
  for (const id of ['c-new-card', 'c-new-shiki']) {{
    resolveRefresh = null; selectSeq = 0; curCard = 'A';
    const pending = buttons[id].onclick();
    while (!resolveRefresh) await Promise.resolve();
    selectSeq++; curCard = null;
    resolveRefresh();
    await pending;
    assert.deepStrictEqual(loads, []);
  }}
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_new_version_refreshes_project_ids_without_stale_continuation(tmp_path):
    create = _extract_js(_script(), "async function createNewVersion()")
    driver = f"""
const assert = require('node:assert');
let curMech = null, curProject = 'P', curCard = 'A', selectSeq = 0, cDirty = true;
let resolveRefresh, refreshStarted = false;
const loads = [];
async function confirmDiscard() {{ return true; }}
async function ask() {{ return {{text: '20270101'}}; }}
function localToday() {{ return '20270101'; }}
function validDateStr() {{ return true; }}
function enc(value) {{ return value; }}
function showFormErrors() {{}}
async function fetch() {{ return {{ok: true, json: async () => ({{stem: 'A@20270101'}})}}; }}
function loadProjectIds() {{
  refreshStarted = true;
  return new Promise(resolve => {{ resolveRefresh = resolve; }});
}}
async function loadCards(stem) {{ loads.push(stem); }}
{create}
(async () => {{
  const pending = createNewVersion();
  while (!refreshStarted && !loads.length) await Promise.resolve();
  assert.strictEqual(refreshStarted, true);
  selectSeq++; curCard = null;
  resolveRefresh();
  await pending;
  assert.deepStrictEqual(loads, []);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)
