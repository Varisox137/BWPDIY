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


def test_host_guard(client):
    """Host 校验（防 DNS rebinding）：非回环 Host 一律 400；回环/testserver 放行。"""
    assert client.get("/api/layout", headers={"host": "evil.example.com"}).status_code == 400
    assert client.get("/api/layout", headers={"host": "attacker.com:8630"}).status_code == 400
    for ok in ("127.0.0.1:8630", "localhost:8630", "[::1]:8630", "testserver"):
        assert client.get("/api/version", headers={"host": ok}).status_code == 200


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
    """允许只保存部分类型（缺省类型回退默认布局是特性）。"""
    r = client.put("/api/layout", json={"战斗": client.get("/api/layout").json()["战斗"]})
    assert r.status_code == 200 and r.json()["ok"]
    assert list(client.get("/api/layout").json()) == ["战斗"]


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
    # 预览不裁剪：返回完整 512×512（布局配置页覆盖层坐标 1:1 对齐的前提）
    from io import BytesIO
    from PIL import Image
    assert Image.open(BytesIO(r.content)).size == (512, 512)


@pytest.mark.parametrize("card_type", ["式神", "战斗", "法术", "形态", "幻境", "协战"])
def test_preview_all_types(client, card_type):
    from bwpdiy.render.layout import load_layouts, get_type_layout
    tl = get_type_layout(load_layouts(client.app.state.assets_dir), card_type)
    r = client.post("/api/preview", json={"type": card_type, "layout": tl})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    from io import BytesIO
    from PIL import Image
    assert Image.open(BytesIO(r.content)).size == (512, 512)


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
let curType = "战斗";
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
const battle = {{type: '战斗', name: '斩', level: 2, rarity: 'R', shikigami: '甲',
                'power+': 1, 'shield+': 1, description: ''}};
assert.deepStrictEqual(validateCardJS(battle), []);
assert.ok(validateCardJS({{...battle, shikigami1: '甲'}}).some(e => e.includes('白名单')));
assert.ok(validateCardJS({{...battle, name: ''}}).some(e => e.includes('name')));
console.log("OK");
"""
    _run_node(tmp_path, driver)
