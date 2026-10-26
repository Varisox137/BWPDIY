"""web 层（FastAPI 编辑器后端）测试：布局读写 API 与样卡预览。"""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from bwpdiy.web.app import create_app

ASSETS = Path(__file__).resolve().parent.parent / "assets"


@pytest.fixture()
def assets_dir(tmp_path) -> Path:
    """真实 assets/ 的临时拷贝：PUT 用例会写 layout.json，不能污染仓库。"""
    dst = tmp_path / "assets"
    shutil.copytree(ASSETS, dst)
    return dst


@pytest.fixture()
def client(assets_dir):
    return TestClient(create_app(assets_dir))


def test_get_layout(client):
    r = client.get("/api/layout")
    assert r.status_code == 200
    assert "战斗" in r.json()


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


def test_host_guard(client):
    """Host 校验（防 DNS rebinding）：非回环 Host 一律 400；回环/testserver 放行。"""
    assert client.get("/api/layout", headers={"host": "evil.example.com"}).status_code == 400
    assert client.get("/api/layout", headers={"host": "attacker.com:8630"}).status_code == 400
    for ok in ("127.0.0.1:8630", "localhost:8630", "[::1]:8630", "testserver"):
        assert client.get("/api/version", headers={"host": ok}).status_code == 200


def test_version_carries_changelog(client):
    """/api/version 附带当前版本更新说明（「最近更新」弹窗数据源）与本次启动 boot_id。"""
    from bwpdiy import __version__
    from bwpdiy.changelog import CHANGELOG
    data = client.get("/api/version").json()
    assert data["version"] == __version__
    assert isinstance(data["boot_id"], int)
    assert data["notes"] == CHANGELOG.get(__version__, [])
    assert CHANGELOG.get(__version__), "当前版本必须在 changelog.py 登记更新说明"


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
    raw = (assets_dir / "layout.json").read_text(encoding="utf-8")
    assert '"战斗"' in raw and "\\u" not in raw
    assert '\n  "战斗"' in raw


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
    before = (assets_dir / "layout.json").read_bytes()
    assert client.put("/api/layout", json={"对局式神": {"elements": []}}).status_code == 422
    assert (assets_dir / "layout.json").read_bytes() == before


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
    before = (assets_dir / "layout.json").read_bytes()
    response = client.put("/api/layout", json={"对局式神": entity})
    assert response.status_code == 422
    assert (assets_dir / "layout.json").read_bytes() == before


def test_put_layout_mech_section(client, assets_dir):
    """「机制」段为扁平参数映射（无 elements/text_regions），可保存并回读。"""
    layouts = client.get("/api/layout").json()
    assert "机制" in layouts  # 缺段时 load_layouts 已补齐包内默认
    layouts["机制"]["text_size"] = 28
    assert client.put("/api/layout", json=layouts).status_code == 200
    assert client.get("/api/layout").json()["机制"]["text_size"] == 28
    # 机制段形状非法（非对象）拒绝且不动文件
    before = (assets_dir / "layout.json").read_bytes()
    r = client.put("/api/layout", json={"机制": "不是对象"})
    assert r.status_code == 422
    assert (assets_dir / "layout.json").read_bytes() == before


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
    bak = assets_dir / "layout.json.bak"
    assert bak.is_file()
    assert not (assets_dir / "layout.json.tmp").exists()


@pytest.mark.parametrize("bad", [
    {},  # 空布局视同误操作
    {"战斗": "不是对象"},
    {"战斗": {"elements": {}}},  # 缺 text_regions
    {"战斗": {"text_regions": {}}},  # 缺 elements
])
def test_put_layout_invalid_shape(client, assets_dir, bad):
    before = (assets_dir / "layout.json").read_bytes()
    r = client.put("/api/layout", json=bad)
    assert r.status_code == 422
    assert (assets_dir / "layout.json").read_bytes() == before  # 校验失败不得动文件


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
    for needle in ("[[关键字]]", "#ll", "四分之一宽空格", "扩展选项", "自适应"):
        assert needle in modal


# --- editor.html 内嵌 JS 纯函数测试（node 驱动：抽取函数源码 + 桩驱动运行） ---
# 布局设置 tab 自 layout.html 迁入 editor.html，被测函数名保持不变

NODE = shutil.which("node")
EDITOR_HTML = Path(__file__).resolve().parent.parent / "bwpdiy" / "web" / "static" / "editor.html"


def _script() -> str:
    html = EDITOR_HTML.read_text(encoding="utf-8")
    return html.split("<script>", 1)[1].split("</script>", 1)[0]


def _extract_js(script: str, decl: str) -> str:
    """按花括号配对从内嵌脚本中抽取一个声明（函数/const 对象字面量）。"""
    start = script.index(decl)
    brace = script.index("{", start)
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
def test_propagate_style_keys_only(tmp_path):
    """保存传播只镜像样式键白名单；kind/field/icon/icon_neg/pos/enabled 不跨类型覆盖。"""
    script = _script()
    import re
    style_keys = re.search(r"const STYLE_KEYS = .*?;", script, re.S).group(0)
    propagate = _extract_js(script, "function propagateFromCurrentType()")
    driver = f"""
const assert = require('node:assert');
const TYPES = ["式神", "战斗", "法术", "形态", "幻境", "协战"];
let curType = "战斗", entityLayoutMode = false;
{style_keys}
{propagate}
const layouts = {{
  "战斗": {{elements: {{
    power: {{kind: "stat", field: "power+", icon: "ll", pos: [138, 484],
            icon_size: 64, num_offset: [8, -2], font_size: 52}},
    shield: {{kind: "stat", field: "shield+", icon: "hj", icon_neg: "pj", pos: [377, 482],
             icon_size: 56, num_offset: [13, -2], font_size: 52}},
    level: {{kind: "level_badge", pos: [120, 60], base_size: 52, star_size: 68, num_size: 40,
            enabled: false}},
  }}}},
  "法术": {{elements: {{
    power: {{kind: "stat", field: "power+", icon: "ll", pos: [160, 485],
            icon_size: 32, num_offset: [22, 0], font_size: 30}},
    health: {{kind: "stat", field: "health+", icon: "sm", pos: [360, 485],
             icon_size: 32, num_offset: [22, 0], font_size: 30}},
    shield: {{kind: "stat", field: "shield+", icon: "hj", pos: [360, 485],
             icon_size: 32, num_offset: [22, 0], font_size: 30}},
    level: {{kind: "level_badge", pos: [120, 65], base_size: 50, star_size: 68, num_size: 40,
            enabled: true}},
  }}}},
  "形态": {{elements: {{
    power: {{kind: "stat", field: "power", icon: "zl", pos: [160, 485],
            icon_size: 32, num_offset: [22, 0], font_size: 30}},
  }}}},
}};
function typeLayout() {{ return layouts[curType]; }}
propagateFromCurrentType();
// 样式键镜像
assert.strictEqual(layouts["法术"].elements.power.icon_size, 64);
assert.deepStrictEqual(layouts["法术"].elements.power.num_offset, [8, -2]);
assert.strictEqual(layouts["形态"].elements.power.font_size, 52);
assert.strictEqual(layouts["法术"].elements.level.base_size, 52);
// 内容/结构键不镜像（field 跨类型污染回归）
assert.strictEqual(layouts["形态"].elements.power.field, "power");
assert.strictEqual(layouts["法术"].elements.health.field, "health+");
assert.strictEqual(layouts["形态"].elements.power.icon, "zl");
assert.strictEqual(layouts["法术"].elements.shield.icon, "hj");
assert.ok(!("icon_neg" in layouts["法术"].elements.shield));
assert.deepStrictEqual(layouts["法术"].elements.power.pos, [160, 485]);
assert.strictEqual(layouts["法术"].elements.level.enabled, true);
console.log("OK");
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
        "function syncElemField(name, key, val)",
        "function syncRegionField(name, key, val)",
        "function selectType(t)",
        "function selectMechLayout()",
        "function selectEntityLayout()",
        "function layoutDiffs(a, b)",
        "function formatDiffs(diffs)",
        "function restoreLayout(all)",
        "function buildTypes()",
        "function buildProps()",
    ))
    import re
    style_keys = re.search(r"const STYLE_KEYS = .*?;", script, re.S).group(0)
    propagate = _extract_js(script, "function propagateFromCurrentType()")
    driver = f"""
const assert = require('node:assert');
const TYPES = ["式神", "战斗", "法术", "形态", "幻境", "协战"];
const FRAME_VARIANT_TYPES = new Set(TYPES.filter(t => t !== '协战'));
let curType = '式神', cardLayoutMode = null, singleLayout = {{elements: {{}}}};
let entityLayoutMode = false, mechLayoutMode = false;
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
{style_keys}
{propagate}
{functions}
entityLayoutMode = true;
assert.strictEqual(typeLayout(), layouts['对局式神']);
const before = deepCopy(layouts);
syncElemField('power', 'icon_size', 99);
syncRegionField('desc', 'width', 99);
propagateFromCurrentType();
assert.deepStrictEqual(layouts, before);
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
const layouts = {{'对局式神': {{elements: {{}}}}}};
const canvas = {{width: 0, height: 0, style: {{}},
  getBoundingClientRect: () => ({{left: 10, top: 20, width: 384, height: 576}})}};
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
{functions}
(async () => {{
  await refreshPreview();
  assert.strictEqual(requests.length, 1);
  assert.strictEqual(requests[0].url, '/api/entity-preview');
  assert.deepStrictEqual(JSON.parse(requests[0].options.body), {{
    card: {{type: '式神', name: '布局样卡'}},
    state: {{level: 2, power: 2, health: 5, combat_power: 1, shield: -1}},
    layout: layouts['对局式神'],
  }});
  assert.strictEqual(canvas.width, 96);
  assert.strictEqual(canvas.height, 144);
  assert.strictEqual(canvas.style.width, '384px');
  assert.strictEqual(canvas.style.height, '576px');
  assert.deepStrictEqual(mousePos({{clientX: 202, clientY: 308}}), [48, 72]);
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
    """对局状态只继承合法基础值，修改不写卡牌数据、不置脏。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function entityEligible(card)",
        "function makeEntityState(card)",
        "function setEntityField(key, value)",
    ))
    driver = f"""
const assert = require('node:assert');
const LEVELS = [1, 2, 3];
const LEVEL_COLOR_VALUES = new Set(['yellow', 'cyan', 'purple', 'red', 'blue', 'brown']);
let entityState = null;
let cDirty = false;
let scheduled = 0;
function scheduleEntityPreview() {{ scheduled++; }}
{functions}
assert(entityEligible({{type: '式神'}}));
assert(entityEligible({{type: '形态'}}));
assert(entityEligible({{type: '法术', evolve: true}}));
assert(!entityEligible({{type: '战斗'}}));
assert(!entityEligible(null));
const source = {{type: '法术', evolve: true, 'power+': 3, 'health+': 4,
                level: 2, level_color: 'cyan', power: -2, health: 5.5,
                combat_power: 8, shield: 9, art_scale: 7}};
const state = makeEntityState(source);
entityState = state;
assert.deepStrictEqual(state, {{level: 2, level_color: 'cyan', power: 0, health: 0,
                                combat_power: 0, shield: 0, art_scale: 1}});
assert.deepStrictEqual(makeEntityState({{type: '式神', level: 4, level_color: 'bad',
                                         power: 3, health: 4}}),
                       {{level: 1, level_color: 'yellow', power: 3, health: 4,
                        combat_power: 0, shield: 0, art_scale: 1}});
setEntityField('power', 4);
assert(state.power === 4 && cDirty === false && scheduled === 1);
assert(source.power === -2 && source['power+'] === 3);
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_entity_subpreviews_dom_order_and_visibility(tmp_path):
    """式神子预览为头像→实体，形态仅实体，普通战斗隐藏子预览容器。"""
    import json
    script = _script()
    html = EDITOR_HTML.read_text(encoding="utf-8")
    mid = html.split('<div id="c-mid">', 1)[1].split('<div id="c-right">', 1)[0]
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function entityEligible(card)",
        "function syncSubpreviews()",
        "async function cPreviewPortrait(withForm)",
        "async function entityPreview()",
    ))
    driver = f"""
const assert = require('node:assert');
const mid = {json.dumps(mid)};
const container = mid.indexOf('id="c-subpreviews"');
const portrait = mid.indexOf('id="c-portrait"');
const entity = mid.indexOf('id="c-entity"');
assert(container >= 0 && container < portrait && portrait < entity);
const cSubpreviews = {{style: {{display: 'none'}}}};
const cPortraitImg = {{style: {{display: 'none'}}, removeAttribute() {{}}}};
const cEntityImg = {{style: {{display: 'none'}}, removeAttribute() {{}}}};
let formData = {{type: '式神'}}, entityState = {{power: 2}};
let curProject = '项目', curCard = 'stem', curMech = null;
let cPortraitSeq = 0, cPortraitUrl = null, cEntitySeq = 0, cEntityUrl = null;
const cErrorEl = {{textContent: ''}};
const URL = {{createObjectURL: () => 'blob:new', revokeObjectURL() {{}}}};
async function fetch() {{ return {{ok: true, blob: async () => ({{kind: 'png'}})}}; }}
async function cHandleEntityPreviewResponse(r, seq) {{ cEntityImg.src = 'blob:entity'; }}
{functions}
(async () => {{
  await cPreviewPortrait(false);
  await entityPreview();
  assert.strictEqual(cPortraitImg.style.display, 'block');
  assert.strictEqual(cEntityImg.style.display, 'block');
  assert.strictEqual(cSubpreviews.style.display, 'flex');
  formData = {{type: '形态'}};
  await cPreviewPortrait(true);
  await entityPreview();
  assert.strictEqual(cPortraitImg.style.display, 'none');
  assert.strictEqual(cEntityImg.style.display, 'block');
  assert.strictEqual(cSubpreviews.style.display, 'flex');
  formData = {{type: '战斗'}};
  await cPreviewPortrait(true);
  await entityPreview();
  assert.strictEqual(cPortraitImg.style.display, 'none');
  assert.strictEqual(cEntityImg.style.display, 'none');
  assert.strictEqual(cSubpreviews.style.display, 'none');
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_entity_preview_has_independent_response_channel_and_export(tmp_path):
    """实体使用独立 seq/URL/图片，慢响应不写主卡；导出沿用当前临时状态。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function entityEligible(card)",
        "function syncSubpreviews()",
        "async function cHandleEntityPreviewResponse(r, seq)",
        "async function entityPreview()",
        "async function exportEntity()",
    ))
    driver = f"""
const assert = require('node:assert');
let entityState = {{level: 2, level_color: 'cyan', power: 4, health: 5,
                    combat_power: -1, shield: 2, art_scale: 1.2}};
let formData = {{type: '形态', name: '  烈:/山?  '}};
let curProject = '项目', curCard = 'card-stem', curMech = null;
let cPreviewSeq = 7, cEntitySeq = 3, cEntityUrl = 'blob:old-entity';
const cPreviewImg = {{src: 'blob:main', onload: null}};
const cEntityImg = {{src: 'blob:old-entity', style: {{display: 'block'}}, onload: null,
                    removeAttribute() {{}}}};
const cPortraitImg = {{style: {{display: 'none'}}}};
const cSubpreviews = {{style: {{display: 'flex'}}}};
const requests = [], downloads = [], created = [];
const cErrorEl = {{textContent: ''}};
function setPreviewError() {{}}
const cFormErrors = {{textContent: ''}};
const document = {{getElementById: id => id === 'c-form-errors' ? cFormErrors : null,
                   createElement: tag => ({{click() {{ downloads.push({{href: this.href,
                                                                      download: this.download}}); }}}})}};
const URL = {{createObjectURL: blob => {{ created.push(blob); return 'blob:new-entity'; }},
             revokeObjectURL: url => {{}}}};
async function fetch(url, options) {{
  requests.push({{url, options}});
  return {{ok: true, blob: async () => ({{kind: 'png'}})}};
}}
async function parseErrorDetail(response) {{ return ['bad']; }}
{functions}
(async () => {{
  await entityPreview();
  assert.strictEqual(cEntitySeq, 4);
  assert.strictEqual(cPreviewSeq, 7);
  assert.strictEqual(cPreviewImg.src, 'blob:main');
  assert.strictEqual(cEntityImg.src, 'blob:new-entity');
  assert.strictEqual(cEntityUrl, 'blob:new-entity');
  assert.strictEqual(requests[0].url, '/api/entity-preview');
  assert.deepStrictEqual(JSON.parse(requests[0].options.body),
                         {{project: curProject, card: formData, state: entityState}});
  const stale = cHandleEntityPreviewResponse({{ok: true,
    blob: () => new Promise(resolve => {{ globalThis.releaseBlob = resolve; }})}}, 4);
  cEntitySeq++;
  globalThis.releaseBlob({{kind: 'stale'}});
  await stale;
  assert.strictEqual(cEntityImg.src, 'blob:new-entity');
  assert.strictEqual(created.length, 1);
  await exportEntity();
  assert.strictEqual(requests[1].url, '/api/entity-preview');
  assert.deepStrictEqual(JSON.parse(requests[1].options.body),
                         {{project: curProject, card: formData, state: entityState}});
  assert.deepStrictEqual(downloads, [{{href: 'blob:new-entity', download: '烈山_对局.png'}}]);
  assert.strictEqual(cFormErrors.textContent, '');
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
let cPreviewSeq = 1, cPreviewUrl = 'blob:current';
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
  cPreviewSeq++;  // 首次检查通过后退出/切卡/清空
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
let cPreviewSeq = 2, cPreviewUrl = 'blob:current';
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
  cPreviewSeq++;  // 首次检查通过后退出/切卡/清空
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
        "const mousePreviewFrames = {art: 0, entity: 0, portrait: 0}",
        "function scheduleMousePreview(channel)",
        "function flushMousePreview(channel)",
        "function afterMouseEdit(channel)",
    ))
    driver = f"""
const assert = require('node:assert');
let formData = {{type: '式神', artwork: {{images: [{{offset_x: 0}}]}}}};
let cDirty = false, notes = 0;
const previews = [];
const document = {{getElementById: () => null}};
function noteEdit() {{ notes++; }}
function showFormErrors() {{}}
function validateCardJS() {{ return []; }}
function cPreviewForm(withPortrait, withEntity) {{
  previews.push({{channel: 'art', x: formData.artwork.images[0].offset_x, withPortrait, withEntity}});
}}
function entityPreview() {{ previews.push({{channel: 'entity', x: formData.artwork.images[0].offset_x}}); }}
function cPreviewPortrait(withForm) {{ previews.push({{channel: 'portrait', withForm}}); }}
let nextFrame = 0;
const frames = new Map();
function requestAnimationFrame(fn) {{ const id = ++nextFrame; frames.set(id, fn); return id; }}
function cancelAnimationFrame(id) {{ frames.delete(id); }}
function runFrame(id) {{ const fn = frames.get(id); frames.delete(id); fn(); }}
{functions}
for (let i = 1; i <= 20; i++) {{
  formData.artwork.images[0].offset_x = i;
  afterMouseEdit('art');
}}
assert.strictEqual(frames.size, 2);
assert.strictEqual(previews.length, 0);
assert(cDirty && notes === 20);
runFrame(mousePreviewFrames.art);
assert.deepStrictEqual(previews, [{{channel: 'art', x: 20, withPortrait: false, withEntity: false}}]);
assert.strictEqual(frames.size, 1);
runFrame(mousePreviewFrames.entity);
assert.deepStrictEqual(previews[1], {{channel: 'entity', x: 20}});
afterMouseEdit('portrait');
scheduleMousePreview('art');
scheduleMousePreview('entity');
assert.strictEqual(frames.size, 3);
const artFrame = mousePreviewFrames.art, entityFrame = mousePreviewFrames.entity;
flushMousePreview('portrait');
assert.strictEqual(frames.size, 2);
assert(frames.has(artFrame) && frames.has(entityFrame));
assert.deepStrictEqual(previews[2], {{channel: 'portrait', withForm: true}});
console.log('OK');
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_mouseup_flushes_only_the_active_drag_channels(tmp_path):
    """实际拖拽结束时取消待执行帧并立即最终预览，无拖拽的 mouseup 不刷新。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "const mousePreviewFrames = {art: 0, entity: 0, portrait: 0}",
        "function scheduleMousePreview(channel)",
        "function flushMousePreview(channel)",
        "function afterMouseEdit(channel)",
        "function bindArtMouse(img)",
    ))
    driver = f"""
const assert = require('node:assert');
let formData = {{type: '式神'}}, cDirty = false;
const previews = [];
const document = {{getElementById: () => null}};
function noteEdit() {{}}
function showFormErrors() {{}}
function validateCardJS() {{ return []; }}
function cPreviewForm(withPortrait, withEntity) {{ previews.push(['art', withPortrait, withEntity]); }}
function entityPreview() {{ previews.push(['entity']); }}
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
{functions}
bindArtMouse(artImg);
bindArtMouse(cPortraitImg);
dispatchWindow('mouseup');
assert.deepStrictEqual(previews, []);
artImg.listeners.mousedown({{button: 0, clientX: 0, clientY: 0, preventDefault() {{}}}});
dispatchWindow('mousemove', {{clientX: 5, clientY: 5}});
assert.strictEqual(frames.size, 2);
dispatchWindow('mouseup');
assert.strictEqual(frames.size, 0);
assert.deepStrictEqual(previews, [['art', false, false], ['entity']]);
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
def test_card_portrait_entity_preview_scheduling_is_independent(tmp_path):
    """普通输入仍使用独立的 300ms 防抖，主卡刷新联动实体与头像。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function scheduleCardPreview()",
        "function scheduleEntityPreview()",
        "async function cPreviewProject()",
        "async function cPreviewForm(withPortrait = true, withEntity = true)",
    ))
    driver = f"""
const assert = require('node:assert');
let cPreviewTimer = null, cPortraitTimer = null, cEntityTimer = null;
let cPreviewSeq = 0, formData = {{type: '式神'}}, curProject = '项目', curCard = 'stem';
let portraits = 0, entities = 0, handled = 0;
let nextTimer = 0;
const timers = new Map(), delays = [];
function setTimeout(fn, delay) {{
  const id = ++nextTimer; timers.set(id, fn); delays.push(delay); return id;
}}
function clearTimeout(id) {{ timers.delete(id); }}
function enc(value) {{ return value; }}
function validateCardJS() {{ return []; }}
function entityPreview() {{ entities++; }}
function cPreviewPortrait() {{ portraits++; }}
async function cHandlePreviewResponse() {{ handled++; }}
async function fetch() {{ return {{ok: true}}; }}
{functions}
scheduleEntityPreview();
scheduleEntityPreview();
scheduleCardPreview();
scheduleCardPreview();
assert.strictEqual(timers.size, 2);
assert.deepStrictEqual(delays, [300, 300, 300, 300]);
(async () => {{
  await cPreviewForm(false);
  assert.strictEqual(entities, 1);
  assert.strictEqual(portraits, 0);
  assert.strictEqual(handled, 1);
  await cPreviewForm(true);
  assert.strictEqual(entities, 2);
  assert.strictEqual(portraits, 1);
  await cPreviewProject();
  assert.strictEqual(entities, 3);
  assert.strictEqual(portraits, 2);
  assert.strictEqual(handled, 3);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_select_card_rechecks_seq_after_json(tmp_path):
    """A/B 选卡 JSON 逆序完成时，旧 A 不得覆盖已提交的 B 表单。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function entityEligible(card)",
        "function makeEntityState(card)",
        "async function selectCard(stem, force = false)",
    ))
    driver = f"""
const assert = require('node:assert');
const LEVELS = [1, 2, 3];
const LEVEL_COLOR_VALUES = new Set(['yellow']);
let curCard = null, curProject = '项目', curMech = null, formData = null, cardData = null;
let entityState = null, cDirty = false, mainShiki = null, neutralMode = false, selectSeq = 0;
let cards = {{shikigami: [], cards: []}}, builds = 0, previews = 0;
const cStatusEl = {{textContent: ''}};
function confirmDiscard() {{ return true; }}
function buildCardList() {{}}
function listErr() {{}}
function enc(value) {{ return value; }}
function deepCopy(value) {{ return JSON.parse(JSON.stringify(value)); }}
function resetUndo() {{}}
function buildForm() {{ builds++; }}
function cPreviewProject() {{ previews++; }}
const pending = {{}};
async function fetch(url) {{
  const stem = url.endsWith('/A') ? 'A' : 'B';
  return {{ok: true, json: () => new Promise(resolve => {{ pending[stem] = resolve; }})}};
}}
{functions}
(async () => {{
  const a = selectCard('A');
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
  assert.strictEqual(entityState.power, 2);
  assert.strictEqual(builds, 1);
  assert.strictEqual(previews, 1);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_preview_urls_released_on_replace_and_clear_without_onload(tmp_path):
    """三通道连续两次换图均立即释放旧 URL，清卡释放最后一张，不依赖 onload。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "async function cHandlePreviewResponse(r, seq)",
        "async function cHandleEntityPreviewResponse(r, seq)",
        "async function cPreviewPortrait(withForm)",
        "function clearCard()",
    ))
    driver = f"""
const assert = require('node:assert');
let cPreviewSeq = 1, cEntitySeq = 1, cPortraitSeq = 0;
let cPreviewTimer = null, cEntityTimer = null, cPortraitTimer = null;
let cPreviewUrl = 'main-old', cEntityUrl = 'entity-old', cPortraitUrl = 'portrait-old';
let curCard = 'stem', curProject = '项目', curMech = null, cardData = {{}}, formData = {{type: '式神'}};
let entityState = {{}}, cDirty = false;
const cPreviewImg = {{src: 'main-old', removeAttribute() {{}}}};
const cEntityImg = {{src: 'entity-old', style: {{}}, removeAttribute() {{}}}};
const cPortraitImg = {{src: 'portrait-old', style: {{}}, removeAttribute() {{}}}};
const cSubpreviews = {{style: {{}}}};
const cErrorEl = {{textContent: ''}};
const cPreviewErrors = {{main: '', entity: ''}};
let cPreviewErrorChannel = null;
function setPreviewError() {{}}
const revoked = [];
const URL = {{createObjectURL: blob => blob, revokeObjectURL: url => revoked.push(url)}};
function clearTimeout() {{}}
function syncSubpreviews() {{}}
function enc(value) {{ return value; }}
function resetUndo() {{}}
const document = {{getElementById: () => ({{textContent: ''}})}};
let portraitRequests = 0;
async function fetch() {{ return {{ok: true, blob: async () => 'portrait-' + (++portraitRequests)}}; }}
function success(url) {{ return {{ok: true, blob: async () => url}}; }}
{functions}
const mainResponse = r => cHandlePreviewResponse(r, ++cPreviewSeq);
const entityResponse = r => cHandleEntityPreviewResponse(r, ++cEntitySeq);
(async () => {{
  await mainResponse(success('main-1'));
  await mainResponse(success('main-2'));
  await entityResponse(success('entity-1'));
  await entityResponse(success('entity-2'));
  await cPreviewPortrait(true);
  await cPreviewPortrait(true);
  assert.deepStrictEqual(revoked,
    ['main-old', 'main-1', 'entity-old', 'entity-1', 'portrait-old', 'portrait-1']);
  clearCard();
  assert.deepStrictEqual(revoked,
    ['main-old', 'main-1', 'entity-old', 'entity-1', 'portrait-old', 'portrait-1',
     'portrait-2', 'entity-2', 'main-2']);
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_preview_errors_are_cleared_per_channel(tmp_path):
    """实体成功只清实体错误；主卡/实体交错失败时保留另一通道错误。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "async function cHandlePreviewResponse(r, seq)",
        "async function cHandleEntityPreviewResponse(r, seq)",
    ))
    error_helper = (_extract_js(script, "function setPreviewError(channel, text)")
                    if "function setPreviewError(channel, text)" in script else """
function setPreviewError(channel, text) {
  cPreviewErrors[channel] = text;
  if (text) cPreviewErrorChannel = channel;
  else if (cPreviewErrorChannel === channel)
    cPreviewErrorChannel = cPreviewErrors[channel === 'main' ? 'entity' : 'main']
      ? (channel === 'main' ? 'entity' : 'main') : null;
  cErrorEl.textContent = cPreviewErrorChannel ? cPreviewErrors[cPreviewErrorChannel] : '';
}
""")
    driver = f"""
const assert = require('node:assert');
let cPreviewSeq = 0, cEntitySeq = 0, cPreviewUrl = null, cEntityUrl = null;
const cPreviewImg = {{src: '', onload: null}}, cEntityImg = {{src: '', onload: null}};
const cErrorEl = {{textContent: ''}};
const cPreviewErrors = {{main: '', entity: ''}};
let cPreviewErrorChannel = null;
const URL = {{createObjectURL: blob => blob, revokeObjectURL() {{}}}};
async function parseErrorDetail(response) {{ return [response.detail]; }}
function success(url) {{ return {{ok: true, blob: async () => url}}; }}
function failure(detail) {{ return {{ok: false, detail}}; }}
{error_helper}
{functions}
const mainResponse = r => cHandlePreviewResponse(r, ++cPreviewSeq);
const entityResponse = r => cHandleEntityPreviewResponse(r, ++cEntitySeq);
(async () => {{
  await entityResponse(failure('实体一'));
  assert(cErrorEl.textContent.includes('实体一'));
  await entityResponse(success('entity-ok'));
  assert.strictEqual(cErrorEl.textContent, '');
  await mainResponse(failure('主卡一'));
  await entityResponse(failure('实体二'));
  assert(cErrorEl.textContent.includes('实体二'));
  await mainResponse(success('main-ok'));
  assert(cErrorEl.textContent.includes('实体二'));
  await entityResponse(success('entity-ok-2'));
  assert.strictEqual(cErrorEl.textContent, '');
  await mainResponse(failure('主卡二'));
  await entityResponse(failure('实体三'));
  await entityResponse(success('entity-ok-3'));
  assert(cErrorEl.textContent.includes('主卡二'));
  console.log('OK');
}})().catch(e => {{ console.error(e); process.exit(1); }});
"""
    _run_node(tmp_path, driver)


@pytest.mark.skipif(NODE is None, reason="node 不可用")
def test_select_card_initializes_entity_and_clear_cancels_all_channels(tmp_path):
    """切卡重建临时实体状态；清卡取消三通道并释放全部 objectURL。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function entityEligible(card)",
        "function makeEntityState(card)",
        "async function selectCard(stem, force = false)",
        "function clearCard()",
    ))
    driver = f"""
const assert = require('node:assert');
const LEVELS = [1, 2, 3];
const LEVEL_COLOR_VALUES = new Set(['yellow', 'cyan']);
let entityState = {{power: 99}};
let curCard = 'old', curProject = '项目', curMech = null, formData = {{name: '旧'}};
let cardData = null, cDirty = true, mainShiki = null, neutralMode = false, selectSeq = 0;
let cards = {{shikigami: [], cards: []}};
const cStatusEl = {{textContent: ''}}, cErrorEl = {{textContent: ''}};
const cPreviewErrors = {{main: '', entity: ''}};
let cPreviewErrorChannel = null;
const removed = [];
const cPreviewImg = {{removeAttribute() {{ removed.push('main'); }}}};
const cPortraitImg = {{style: {{}}, removeAttribute() {{ removed.push('portrait'); }}}};
const cEntityImg = {{style: {{}}, removeAttribute() {{ removed.push('entity'); }}}};
const cSubpreviews = {{style: {{display: 'flex'}}}};
let cPreviewUrl = 'blob:main', cPortraitUrl = 'blob:portrait', cEntityUrl = 'blob:entity';
let cPreviewSeq = 1, cPortraitSeq = 2, cEntitySeq = 3;
let cPreviewTimer = 11, cPortraitTimer = 12, cEntityTimer = 13;
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
function buildForm() {{}}
function cPreviewProject() {{}}
async function fetch() {{ return {{ok: true, json: async () => ({{type: '形态', name: '新', power: 3, health: 4}})}}; }}
{functions}
(async () => {{
  await selectCard('new');
  assert.strictEqual(entityState.power, 3);
  assert.strictEqual(entityState.health, 4);
  assert.strictEqual(cDirty, false);
  clearCard();
  assert.strictEqual(entityState, null);
  assert.deepStrictEqual(cancelled, [11, 12, 13]);
  assert.deepStrictEqual(revoked, ['blob:portrait', 'blob:entity', 'blob:main']);
  assert.strictEqual(cPreviewSeq, 2);
  assert.strictEqual(cPortraitSeq, 3);
  assert.strictEqual(cEntitySeq, 4);
  assert.strictEqual(cPreviewUrl, null);
  assert.strictEqual(cPortraitUrl, null);
  assert.strictEqual(cEntityUrl, null);
  assert.deepStrictEqual(removed, ['main', 'portrait', 'entity']);
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
def test_entity_controls_append_to_normal_form_without_dirtying(tmp_path):
    """实体控件追加在普通表单后，保留原字段与按钮，修改只调度实体预览。"""
    script = _script()
    functions = "\n".join(_extract_js(script, decl) for decl in (
        "function appendEntityForm(div)",
        "function setEntityField(key, value)",
        "function selRowC(div, label, opts, val, set, map = null)",
        "function numRowC(div, label, val, nonneg, set, extra = null)",
        "function artRow(div, label, val, set, pval, pset, step = 1, min = null, ids = null)",
    ))
    build_form = _extract_js(script, "function buildForm()")
    driver = f"""
const assert = require('node:assert');
const LEVELS = [1, 2, 3];
const LEVEL_COLORS = [['yellow', '黄'], ['cyan', '青']];
let entityState = {{level: 2, level_color: 'cyan', power: 3, health: 4,
                    combat_power: 0, shield: 0, art_scale: 1}};
let cDirty = false, scheduled = 0, exported = false;
const formData = {{type: '形态', name: '烈'}};
function scheduleEntityPreview() {{ scheduled++; }}
function exportEntity() {{ exported = true; }}
function element(tag) {{ return {{tag, children: [], style: {{}}, textContent: '',
  appendChild(child) {{ this.children.push(child); }} }}; }}
const form = element('div');
const normalLabel = element('label'); normalLabel.textContent = '卡名 ';
const normalButton = element('button'); normalButton.textContent = '保存';
form.appendChild(normalLabel); form.appendChild(normalButton);
const document = {{createElement: element}};
const buildFormSource = {build_form!r};
{functions}
appendEntityForm(form);
assert.strictEqual(form.children[0], normalLabel);
assert.strictEqual(form.children[1], normalButton);
assert(buildFormSource.includes('appendEntityForm(div)'));
const labels = [], buttons = [], labelElements = [];
function visit(node) {{
  if (node.tag === 'label') {{ labels.push(node.textContent.trim()); labelElements.push(node); }}
  if (node.tag === 'button') buttons.push(node);
  for (const child of node.children || []) visit(child);
}}
visit(form);
assert.deepStrictEqual(labels, ['卡名', '等级', '勾玉颜色', '对局缩放', '力量', '生命',
                                '战力/乏力', '护甲/破甲']);
assert.deepStrictEqual(buttons.map(b => b.textContent), ['保存', '导出对局式神']);
const level = labelElements.find(l => l.textContent.trim() === '等级').children[0];
level.value = '3'; level.onchange();
assert.strictEqual(entityState.level, 3);
assert.strictEqual(scheduled, 1);
assert.strictEqual(cDirty, false);
buttons[1].onclick();
assert(exported);
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
