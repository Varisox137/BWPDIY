"""web 层项目/卡牌 REST API 测试：CRUD 全路径、错误映射、项目卡预览、卡图上传（id/卡名命名）。

fixture 用 tmp_path 的 library_dir + 共享 assets 拷贝（逐用例恢复布局），不碰真实用户数据。
存储模型：library/<项目>/{shikigami,cards}/<任意文件名>.yaml + images/；
文件名（stem）与卡名（name 字段）脱钩；list_cards 按 id+name 归组返回
{stem(最新版本), name, id, versions, count}；保存时 version_date 留空填当天。
"""

import shutil
from copy import deepcopy
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from PIL import Image

from bwpdiy.render.entity import _DEFAULT_LAYOUT
from bwpdiy.web.app import create_app

SAMPLE_ART = Path(__file__).resolve().parent / "fixtures" / "sample_art.png"


@pytest.fixture()
def assets_dir(web_assets_dir) -> Path:
    return web_assets_dir


@pytest.fixture()
def library_dir(tmp_path) -> Path:
    return tmp_path / "library"  # 不预先创建：store 对缺失 library 返回空列表


@pytest.fixture()
def client(assets_dir, library_dir):
    return TestClient(create_app(assets_dir, library_dir=library_dir))


def _shikigami_card(name="测试式神"):
    return {"type": "式神", "name": name, "faction": "红莲", "power": 3, "health": 4}


def _battle_card(name="测试斩", shikigami="测试式神"):
    return {"type": "战斗", "name": name, "level": 2, "rarity": "R",
            "shikigami": shikigami, "power+": 1, "shield+": 1,
            "description": "测试描述。"}


TODAY = date.today().strftime("%Y%m%d")


def with_today(card):
    return {**card, "version_date": TODAY}


def entry(stem, name, vd=TODAY, shiki=None, stats=False, rarity="R", ctype=None):
    version = {"stem": stem, "date": vd}
    if shiki is not None or stats:
        version.update(type=ctype or ("式神" if stats else "战斗"),
                       rarity=None if stats else rarity, shikigami=shiki,
                       shikigami1=None, shikigami2=None)
    data = {"stem": stem, "name": name, "id": None,
            "versions": [version], "count": 1,
            "shikigami": shiki, "shikigami1": None, "shikigami2": None}
    if stats:
        data.update(power=3, health=4)
    return data


def _png_size(resp) -> tuple:
    return Image.open(BytesIO(resp.content)).size


def _assert_tight_card(resp):
    """紧致导出：高≈512 顶格（框缘抗锯齿可差 1px）、宽按内容（≤512，无 512 画布留白）。"""
    w, h = _png_size(resp)
    assert 511 <= h <= 512 and 0 < w <= 512
    return True


def _img_files(library_dir, project) -> list:
    d = library_dir / project / "images"
    return sorted(p.name for p in d.iterdir()) if d.is_dir() else []


# ---------- 项目 CRUD ----------

def test_projects_empty(client):
    r = client.get("/api/projects")
    assert r.status_code == 200 and r.json() == []


def test_project_create_empty(client):
    """create_project 创建空项目（无出厂式神卡），cards 列表为两组空表。"""
    r = client.post("/api/projects", json={"name": "测试项目"})
    assert r.status_code == 200 and r.json()["ok"]
    assert client.get("/api/projects").json() == ["测试项目"]
    assert client.get("/api/projects/测试项目/cards").json() == {"shikigami": [], "cards": []}


def test_project_create_duplicate_409(client):
    assert client.post("/api/projects", json={"name": "测试项目"}).status_code == 200
    r = client.post("/api/projects", json={"name": "测试项目"})
    assert r.status_code == 409 and "已存在" in r.json()["detail"]


@pytest.mark.parametrize("bad", ["", "  ", "../evil", "a\\b", "evil.", "CON"])
def test_project_create_illegal_name_422(client, bad):
    r = client.post("/api/projects", json={"name": bad})
    assert r.status_code == 422
    assert client.get("/api/projects").json() == []


def test_project_create_missing_name_422(client):
    r = client.post("/api/projects", json={})
    assert r.status_code == 422


def test_project_rename(client):
    client.post("/api/projects", json={"name": "旧名"})
    r = client.put("/api/projects/旧名", json={"new_name": "新名"})
    assert r.status_code == 200 and r.json()["ok"]
    assert client.get("/api/projects").json() == ["新名"]
    assert client.get("/api/projects/新名/cards").status_code == 200


def test_project_rename_not_found_404(client):
    r = client.put("/api/projects/不存在", json={"new_name": "新名"})
    assert r.status_code == 404 and "不存在" in r.json()["detail"]


def test_project_rename_conflict_409(client):
    client.post("/api/projects", json={"name": "甲"})
    client.post("/api/projects", json={"name": "乙"})
    r = client.put("/api/projects/甲", json={"new_name": "乙"})
    assert r.status_code == 409


def test_project_delete(client):
    client.post("/api/projects", json={"name": "测试项目"})
    r = client.delete("/api/projects/测试项目")
    assert r.status_code == 200
    assert client.get("/api/projects").json() == []
    r = client.delete("/api/projects/测试项目")
    assert r.status_code == 404


# ---------- 卡牌 CRUD ----------

@pytest.fixture()
def project(client):
    """空项目 + 一张式神卡（stem 与卡名脱钩，此处恰好同名）。"""
    client.post("/api/projects", json={"name": "测试项目"})
    client.put("/api/projects/测试项目/cards/shikigami", json=_shikigami_card())
    return "测试项目"


_SHIKI_ENTRY = entry("shikigami", "测试式神", stats=True)


def test_card_save_and_load_roundtrip(client, project):
    card = _battle_card()
    r = client.put(f"/api/projects/{project}/cards/测试斩", json=card)
    assert r.status_code == 200 and r.json() == {"ok": True, "updated": [], "stem": "测试斩"}
    assert client.get(f"/api/projects/{project}/cards").json() == {
        "shikigami": [_SHIKI_ENTRY], "cards": [entry("测试斩", "测试斩", shiki="测试式神")]}
    got = client.get(f"/api/projects/{project}/cards/测试斩").json()
    assert got == with_today(card)


def test_derived_shikigami_is_card_not_main_shikigami(client, project):
    """有所属式神的式神是衍生物，进入 cards/；主要式神仍只有无所属式神者。"""
    card = {"type": "式神", "name": "召唤物", "shikigami": "测试式神",
            "special_type": "召唤", "faction": "红莲", "power": 1, "health": 2, "description": ""}
    r = client.put(f"/api/projects/{project}/cards/召唤物", json=card)
    assert r.status_code == 200
    assert client.get(f"/api/projects/{project}/cards").json() == {
        "shikigami": [_SHIKI_ENTRY],
        "cards": [entry("召唤物", "召唤物", shiki="测试式神", rarity=None, ctype="式神")],
    }
    assert client.get(f"/api/projects/{project}/cards/召唤物").json() == with_today(card)


def test_card_rename_without_id_renames_file(client, project):
    """无 id 卡改名：保存后服务端重命名 yaml，响应 stem 为新文件名。"""
    client.put(f"/api/projects/{project}/cards/测试斩", json=_battle_card())
    r = client.put(f"/api/projects/{project}/cards/测试斩", json=_battle_card("斩改"))
    assert r.status_code == 200 and r.json()["stem"] == "斩改"
    assert client.get(f"/api/projects/{project}/cards").json()["cards"] == [
        entry("斩改", "斩改", shiki="测试式神")]
    r2 = client.get(f"/api/projects/{project}/cards/测试斩")
    assert r2.status_code == 404


def test_card_list_sorted_by_name(client, project):
    """list_cards 各组按卡内 name 排序（与文件名脱钩；stem 与名字序相反以排除按文件名排序）。"""
    client.put(f"/api/projects/{project}/cards/stem-a", json=_battle_card("B卡"))
    client.put(f"/api/projects/{project}/cards/stem-b", json=_battle_card("A卡"))
    lst = client.get(f"/api/projects/{project}/cards").json()
    assert lst["cards"] == [entry("stem-b", "A卡", shiki="测试式神"), entry("stem-a", "B卡", shiki="测试式神")]


def test_card_save_schema_error_422_chinese(client, project):
    bad = {"type": "战斗", "name": "测试斩", "power+": "很大", "rarity": "UR"}
    r = client.put(f"/api/projects/{project}/cards/测试斩", json=bad)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert any("rarity" in m for m in detail)      # 非法稀有度一次报全
    assert any("power+" in m for m in detail)
    assert client.get(f"/api/projects/{project}/cards").json()["cards"] == []  # 未落盘


def test_card_save_name_decoupled_from_stem(client, project):
    """卡名与文件名脱钩：stem 与 name 不一致可保存（不再强制一致）。"""
    r = client.put(f"/api/projects/{project}/cards/stem-1", json=_battle_card("卡内名"))
    assert r.status_code == 200
    lst = client.get(f"/api/projects/{project}/cards").json()
    assert lst["cards"] == [entry("stem-1", "卡内名", shiki="测试式神")]
    assert client.get(f"/api/projects/{project}/cards/stem-1").json()["name"] == "卡内名"


def test_card_save_shikigami_rename_syncs_references(client, project):
    """式神卡改名：save_card 联动更新同项目卡的 shikigami 引用，updated 返回被更新卡名。"""
    client.put(f"/api/projects/{project}/cards/测试斩", json=_battle_card())
    r = client.put(f"/api/projects/{project}/cards/shikigami", json=_shikigami_card("新名"))
    assert r.status_code == 200
    assert r.json() == {"ok": True, "updated": ["测试斩"], "stem": "shikigami"}
    assert client.get(f"/api/projects/{project}/cards/测试斩").json()["shikigami"] == "新名"
    lst = client.get(f"/api/projects/{project}/cards").json()
    assert lst["shikigami"] == [entry("shikigami", "新名", stats=True)]


def test_card_save_shikigami_overwrite(client, project):
    card = {"type": "式神", "name": "改名式神", "faction": "苍叶", "power": 2, "health": 5}
    r = client.put(f"/api/projects/{project}/cards/shikigami", json=card)
    assert r.status_code == 200
    assert client.get(f"/api/projects/{project}/cards/shikigami").json()["health"] == 5


def test_card_save_over_299_forbidden_422(client, project, library_dir):
    """非式神卡超 299 张：store 报 forbidden → 422。"""
    d = library_dir / project / "cards"
    d.mkdir(parents=True, exist_ok=True)
    for i in range(299):
        (d / f"c{i:03}.yaml").write_text(
            yaml.safe_dump(_battle_card(f"卡{i}"), allow_unicode=True), encoding="utf-8")
    r = client.put(f"/api/projects/{project}/cards/超额卡", json=_battle_card("超额卡"))
    assert r.status_code == 422


def test_card_save_reinforce_shikigami12(client, project):
    """协战白名单：shikigami1/shikigami2 可选字符串；旧 shikigami 键已移除（422）。"""
    card = {"type": "协战", "name": "共鸣", "level": 1, "rarity": "R",
            "shikigami1": "测试式神", "shikigami2": "另一式神", "description": "测试描述。"}
    r = client.put(f"/api/projects/{project}/cards/共鸣", json=card)
    assert r.status_code == 200
    assert client.get(f"/api/projects/{project}/cards/共鸣").json() == with_today(card)
    bad = dict(card, shikigami="测试式神")
    assert client.put(f"/api/projects/{project}/cards/共鸣", json=bad).status_code == 422


def test_card_crud_project_not_found_404(client):
    assert client.get("/api/projects/不存在/cards").status_code == 404
    assert client.get("/api/projects/不存在/cards/x").status_code == 404
    assert client.put("/api/projects/不存在/cards/x", json=_battle_card("x")).status_code == 404
    assert client.delete("/api/projects/不存在/cards/x").status_code == 404


def test_card_load_not_found_404(client, project):
    r = client.get(f"/api/projects/{project}/cards/不存在")
    assert r.status_code == 404 and "不存在" in r.json()["detail"]


def test_card_delete(client, project):
    client.put(f"/api/projects/{project}/cards/测试斩", json=_battle_card())
    assert client.delete(f"/api/projects/{project}/cards/测试斩").status_code == 200
    assert client.get(f"/api/projects/{project}/cards").json() == {
        "shikigami": [_SHIKI_ENTRY], "cards": []}
    assert client.delete(f"/api/projects/{project}/cards/测试斩").status_code == 404


def test_card_delete_shikigami_allowed(client, project):
    """式神卡可删（新存储模型解禁）。"""
    assert client.delete(f"/api/projects/{project}/cards/shikigami").status_code == 200
    assert client.get(f"/api/projects/{project}/cards").json() == {"shikigami": [], "cards": []}


@pytest.mark.parametrize("bad", ["a\\b", "evil.", "NUL"])
def test_card_illegal_name_422(client, project, bad):
    card = _battle_card(bad)
    r = client.put(f"/api/projects/{project}/cards/{bad}", json=card)
    assert r.status_code == 422


# ---------- 项目卡预览 ----------

def test_preview_default_shikigami_fallback_art(client, project):
    """无 artwork 的式神卡：占位图回退，渲染出紧致原尺寸 PNG（高 512、无画布留白）。"""
    r = client.post(f"/api/projects/{project}/cards/shikigami/preview", json={})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    _assert_tight_card(r)


def test_preview_no_body(client, project):
    r = client.post(f"/api/projects/{project}/cards/shikigami/preview")
    assert r.status_code == 200


def test_preview_layout_override(client, project):
    tl = client.get("/api/layout").json()["式神"]
    tl["elements"]["name"]["font_size"] = 20
    base = client.post(f"/api/projects/{project}/cards/shikigami/preview", json={})
    r = client.post(f"/api/projects/{project}/cards/shikigami/preview", json={"layout": tl})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content != base.content  # 覆盖生效


def test_preview_card_layout_field_merges(client, project):
    """卡面 layout 段（单卡布局覆盖）：不传 layout 时服务端自动合并覆盖全局布局。"""
    assert client.put(f"/api/projects/{project}/cards/测试斩", json=_battle_card()
                      ).status_code == 200
    base = client.post(f"/api/projects/{project}/cards/测试斩/preview", json={})
    card = _battle_card()
    card["layout"] = {"elements": {"name": {"font_size": 20}}}
    r = client.put(f"/api/projects/{project}/cards/测试斩", json=card)  # layout 字段过 schema
    assert r.status_code == 200, r.json()
    r = client.post(f"/api/projects/{project}/cards/测试斩/preview", json={})
    assert r.status_code == 200 and r.content != base.content  # 同一卡，覆盖后渲染不同
    # 编辑期表单覆盖（含 layout 段）同样生效
    r2 = client.post(f"/api/projects/{project}/cards/测试斩/preview",
                     json={"card": {**card, "layout": {"elements": {"name": {"font_size": 40}}}}})
    assert r2.status_code == 200 and r2.content != r.content
    # layout 形状非法：422
    bad = client.put(f"/api/projects/{project}/cards/测试斩",
                     json={**card, "layout": {"elements": {"name": "junk"}}})
    assert bad.status_code == 422


def test_preview_missing_image_fallback(client, project):
    """artwork.images 指向缺失文件：回退占位图而非 422。"""
    card = _battle_card()
    card["artwork"] = {"images": [{"path": "不存在的图.png", "scale": 1.2}]}
    assert client.put(f"/api/projects/{project}/cards/测试斩", json=card).status_code == 200
    r = client.post(f"/api/projects/{project}/cards/测试斩/preview", json={})
    assert r.status_code == 200 and _assert_tight_card(r)


def test_preview_uses_project_images_dir(client, project, library_dir):
    """artwork 基准目录 = 项目 images/：图在 images/ 下即可按相对路径渲染。"""
    shutil.copy2(SAMPLE_ART, library_dir / project / "images" / "卡图.png")
    card = _battle_card()
    card["artwork"] = {"images": [{"path": "卡图.png"}]}
    assert client.put(f"/api/projects/{project}/cards/测试斩", json=card).status_code == 200
    r = client.post(f"/api/projects/{project}/cards/测试斩/preview", json={})
    assert r.status_code == 200 and _assert_tight_card(r)


def test_preview_card_not_found_404(client, project):
    r = client.post(f"/api/projects/{project}/cards/不存在/preview", json={})
    assert r.status_code == 404


def test_preview_card_override(client, project, library_dir):
    """编辑期实时预览：body.card 整体覆盖盘上数据，artwork 相对 images/ 解析。"""
    shutil.copy2(SAMPLE_ART, library_dir / project / "images" / "图.png")
    override = _battle_card("覆盖卡")
    override["artwork"] = {"images": [{"path": "图.png", "scale": 2.0}]}
    base = client.post(f"/api/projects/{project}/cards/shikigami/preview", json={})
    r = client.post(f"/api/projects/{project}/cards/shikigami/preview", json={"card": override})
    assert r.status_code == 200 and _assert_tight_card(r)
    assert r.content != base.content  # 覆盖生效（盘上 shikigami 是式神卡，覆盖为战斗卡）


@pytest.mark.parametrize("exists", [True, False])
def test_preview_override_artwork_outside_images_422(client, project, tmp_path, exists):
    """覆盖 card 的 artwork 越出 images/：无论外部文件是否存在都拒绝，不探测后回退。"""
    outside = tmp_path / "outside.png"
    if exists:
        Image.new("RGB", (32, 32), "red").save(outside)
    override = _battle_card()
    override["artwork"] = {"images": [{"path": str(outside.resolve())}]}
    r = client.post(f"/api/projects/{project}/cards/shikigami/preview", json={"card": override})
    assert r.status_code == 422
    assert "渲染失败: 卡图路径越出基准目录" in r.json()["detail"]


def test_preview_unrenderable_card_422(client, project, library_dir):
    """手写空 yaml（load 不校验）→ 渲染异常映射 422。"""
    (library_dir / project / "cards" / "空卡.yaml").write_text("", encoding="utf-8")
    r = client.post(f"/api/projects/{project}/cards/空卡/preview", json={})
    assert r.status_code == 422 and "渲染失败" in r.json()["detail"]


# ---------- 对局式神预览 ----------


def _entity_card(card_type="式神", **extra):
    return {"type": card_type, "name": "对局样例", **extra}


def _entity_body(card=None, state=None, **extra):
    return {"card": _entity_card() if card is None else card,
            "state": {} if state is None else state, **extra}


@pytest.mark.parametrize("card", [
    _entity_card(),
    _entity_card("形态"),
    _entity_card("战斗", evolve=True),
    _entity_card("法术", evolve=True),
])
def test_entity_preview_project_eligible_cards(client, project, card):
    r = client.post("/api/entity-preview", json=_entity_body(card, project=project))
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.headers["x-crop-offset"].count(",") == 1
    image = Image.open(BytesIO(r.content))
    assert image.width > 0 and image.height > 0


def test_entity_preview_project_rejects_normal_combat(client, project):
    r = client.post("/api/entity-preview",
                    json=_entity_body(_entity_card("战斗"), project=project))
    assert r.status_code == 422


def test_entity_preview_rejects_invalid_layout_422(client):
    entity_layout = deepcopy(_DEFAULT_LAYOUT)
    entity_layout["elements"]["power"]["icon_size"] = True
    r = client.post("/api/entity-preview",
                    json=_entity_body(layout=entity_layout))
    assert r.status_code == 422
    assert "icon_size" in r.json()["detail"]


@pytest.mark.parametrize("state", [True, {"level": 4}, {"power": True}, {"art_scale": True}])
def test_entity_preview_project_rejects_invalid_state(client, project, state):
    r = client.post("/api/entity-preview",
                    json={"project": project, "card": _entity_card(), "state": state})
    assert r.status_code == 422


def test_entity_preview_project_not_found_404(client):
    r = client.post("/api/entity-preview", json=_entity_body(project="不存在"))
    assert r.status_code == 404


@pytest.mark.parametrize("bad", ["../evil", "a\\b", "CON"])
def test_entity_preview_invalid_project_name_422_without_fs(client, monkeypatch, bad):
    directory_checks = []

    def no_directory_access(path):
        directory_checks.append(path)
        return False

    monkeypatch.setattr(Path, "is_dir", no_directory_access)
    r = client.post("/api/entity-preview", json=_entity_body(project=bad))
    assert r.status_code == 422
    assert "项目名" in r.json()["detail"]
    assert directory_checks == []


def test_entity_preview_project_ignores_request_base_dir(client, project, tmp_path):
    outside = tmp_path / "outside.png"
    Image.new("RGB", (32, 32), "red").save(outside)
    baseline = client.post("/api/entity-preview", json=_entity_body(project=project))
    card = _entity_card(_base_dir=str(tmp_path),
                        artwork={"images": [{"path": outside.name}]})
    r = client.post("/api/entity-preview", json=_entity_body(card, project=project))
    assert r.status_code == 200
    assert r.content == baseline.content


@pytest.mark.parametrize("exists", [True, False])
def test_entity_preview_project_rejects_artwork_outside_images(client, project, tmp_path, exists):
    outside = tmp_path / "outside.png"
    if exists:
        Image.new("RGB", (32, 32), "red").save(outside)
    card = _entity_card(artwork={"images": [{"path": str(outside.resolve())}]})
    r = client.post("/api/entity-preview", json=_entity_body(card, project=project))
    assert r.status_code == 422
    assert "渲染失败: 卡图路径越出基准目录" in r.json()["detail"]


def test_entity_preview_project_missing_image_fallback(client, project):
    card = _entity_card(artwork={"images": [{"path": "不存在.png"}]})
    baseline = client.post("/api/entity-preview", json=_entity_body(project=project))
    r = client.post("/api/entity-preview", json=_entity_body(card, project=project))
    assert r.status_code == 200
    assert r.content == baseline.content


def test_entity_preview_is_read_only(client, project, library_dir):
    yaml_path = library_dir / project / "shikigami" / "shikigami.yaml"
    before = yaml_path.read_bytes()
    r = client.post("/api/entity-preview", json=_entity_body(project=project))
    assert r.status_code == 200
    assert yaml_path.read_bytes() == before


# ---------- 页面路由 ----------

def test_editor_page_at_root(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    # 编辑器主体页含两 tab：卡牌库 / 布局设置
    assert "卡牌库" in r.text and "布局设置" in r.text


def test_layout_redirects_to_editor_layout_tab(client):
    """独立布局页已退役：/layout 重定向到编辑器主体页的布局设置 tab。"""
    r = client.get("/layout", follow_redirects=False)
    assert r.status_code in (301, 302, 303, 307, 308)
    assert r.headers["location"] == "/#layout"


# ---------- 修复轮 1：StoreError.code 分派 + 坏 artwork 容错 ----------

def test_error_status_immune_to_keyword_in_name(client):
    """名字含「不存在」子串不得翻转状态码：按 StoreError.code 分派而非消息关键词。"""
    assert client.post("/api/projects", json={"name": "不存在"}).status_code == 200
    r = client.post("/api/projects", json={"name": "不存在"})
    assert r.status_code == 409 and "已存在" in r.json()["detail"]
    assert client.post("/api/projects", json={"name": "并不存在xx"}).status_code == 200
    r = client.post("/api/projects", json={"name": "并不存在xx"})
    assert r.status_code == 409
    # 非法名「不存在.」（以点结尾）：消息含「不存在」子串，仍须 422
    r = client.post("/api/projects", json={"name": "不存在."})
    assert r.status_code == 422
    # 删除名为「不存在」的项目后再次删除：真正的 not_found
    assert client.delete("/api/projects/不存在").status_code == 200
    assert client.delete("/api/projects/不存在").status_code == 404


@pytest.mark.parametrize("artwork", [
    "烂",                          # artwork 非映射
    [1, 2],                        # artwork 为列表
    {"images": "不是列表"},         # images 非列表
    {"images": [{"path": 123}]},   # path 非字符串
])
def test_preview_bad_artwork_shape_fallback(client, project, library_dir, artwork):
    """手写坏 yaml 的 artwork 形状非法：视为无图回退占位（load 不校验、预览宽容），不 500。"""
    card = _battle_card("坏图卡")
    card["artwork"] = artwork
    (library_dir / project / "cards" / "坏图卡.yaml").write_text(
        yaml.safe_dump(card, allow_unicode=True), encoding="utf-8")
    r = client.post(f"/api/projects/{project}/cards/坏图卡/preview", json={})
    assert r.status_code == 200 and _assert_tight_card(r)


def test_preview_multi_images_uses_first(client, project, library_dir):
    """多图列表：渲染消费首图，首图存在时后续条目缺失不影响。"""
    shutil.copy2(SAMPLE_ART, library_dir / project / "images" / "卡图.png")
    card = _battle_card()
    card["artwork"] = {"images": [{"path": "卡图.png"}, {"path": "异画缺图.png"}]}
    assert client.put(f"/api/projects/{project}/cards/测试斩", json=card).status_code == 200
    r = client.post(f"/api/projects/{project}/cards/测试斩/preview", json={})
    assert r.status_code == 200 and _assert_tight_card(r)


def test_encoded_slash_in_path_rejected(client, project):
    """%2F 编码路径：Starlette 解码后多段不匹配路由（404），不会落到文件系统。"""
    r = client.get("/api/projects/a%2Fb/cards")
    assert r.status_code == 404


# ---------- 卡图上传（落盘名 = <id 或卡名><ext>） ----------

def test_artwork_upload_roundtrip(client, project, library_dir):
    """上传合法 png（卡无 id）：落盘 images/<卡名>.png、yaml 写回 artwork.images[0].path、预览可用。"""
    client.put(f"/api/projects/{project}/cards/测试斩", json=_battle_card())
    data = SAMPLE_ART.read_bytes()
    r = client.post(f"/api/projects/{project}/cards/测试斩/artwork?filename=立绘.PNG",
                    content=data)
    assert r.status_code == 200 and r.json()["path"] == "测试斩.png"  # 扩展名小写化
    assert _img_files(library_dir, project) == ["测试斩.png"]
    card = client.get(f"/api/projects/{project}/cards/测试斩").json()
    assert card["artwork"]["images"][0]["path"] == "测试斩.png"
    r = client.post(f"/api/projects/{project}/cards/测试斩/preview", json={})
    assert r.status_code == 200 and _assert_tight_card(r)


def test_artwork_upload_named_by_id(client, project, library_dir):
    """卡有 id 字段：落盘 <id>.<ext>（对齐 BWPro 按 id 取卡图）；同图重传同名复用。"""
    client.put(f"/api/projects/{project}/cards/测试斩",
               json={**_battle_card(), "id": "100301"})
    data = SAMPLE_ART.read_bytes()
    r1 = client.post(f"/api/projects/{project}/cards/测试斩/artwork?filename=a.png", content=data)
    r2 = client.post(f"/api/projects/{project}/cards/测试斩/artwork?filename=b.png", content=data)
    assert r1.json()["path"] == "100301.png" == r2.json()["path"]
    assert _img_files(library_dir, project) == ["100301.png"]


def test_artwork_upload_same_name_versions(client, project, library_dir):
    """同卡名不同版本：id 不同 → 各自卡图文件并存（同卡名同卡图不同版本场景）。"""
    client.put(f"/api/projects/{project}/cards/v1", json={**_battle_card(), "id": "100301"})
    client.put(f"/api/projects/{project}/cards/v2", json={**_battle_card(), "id": "10030101"})
    data = SAMPLE_ART.read_bytes()
    client.post(f"/api/projects/{project}/cards/v1/artwork?filename=a.png", content=data)
    client.post(f"/api/projects/{project}/cards/v2/artwork?filename=a.png", content=data)
    assert _img_files(library_dir, project) == ["100301.png", "10030101.png"]


def test_artwork_upload_preserves_offset_scale_and_keeps_old(client, project, library_dir):
    """换图重传：保留已有 offset/scale；不清理旧图（孤儿文件用户自理）。"""
    card = _battle_card()
    card["artwork"] = {"images": [{"path": "旧图.png", "offset_x": 5, "scale": 1.2}]}
    client.put(f"/api/projects/{project}/cards/测试斩", json=card)
    client.post(f"/api/projects/{project}/cards/测试斩/artwork?filename=a.png",
                content=SAMPLE_ART.read_bytes())
    jpg = BytesIO()
    Image.new("RGB", (8, 8)).save(jpg, "JPEG")
    r = client.post(f"/api/projects/{project}/cards/测试斩/artwork?filename=b.jpg",
                    content=jpg.getvalue())
    assert r.status_code == 200 and r.json()["path"] == "测试斩.jpg"
    assert _img_files(library_dir, project) == ["测试斩.jpg", "测试斩.png"]  # 旧图保留
    got = client.get(f"/api/projects/{project}/cards/测试斩").json()["artwork"]["images"][0]
    assert got["path"] == "测试斩.jpg" and got["offset_x"] == 5 and got["scale"] == 1.2


def test_artwork_upload_write_failure_preserves_existing_file(client, project, library_dir, monkeypatch):
    """写盘异常不得截断同名旧图；原子替换失败时旧内容原样保留。"""
    client.put(f"/api/projects/{project}/cards/测试斩", json=_battle_card())
    target = library_dir / project / "images" / "测试斩.png"
    target.write_bytes(b"ORIGINAL")
    monkeypatch.setattr("bwpdiy.web.app._atomic_write_bytes",
                        lambda *args: (_ for _ in ()).throw(OSError("模拟磁盘写入失败")))
    r = client.post(f"/api/projects/{project}/cards/测试斩/artwork?filename=x.png",
                    content=SAMPLE_ART.read_bytes())
    assert r.status_code == 422
    assert target.read_bytes() == b"ORIGINAL"


def test_artwork_upload_bad_ext_422(client, project, library_dir):
    client.put(f"/api/projects/{project}/cards/测试斩", json=_battle_card())
    r = client.post(f"/api/projects/{project}/cards/测试斩/artwork?filename=x.gif",
                    content=SAMPLE_ART.read_bytes())
    assert r.status_code == 422 and "格式" in r.json()["detail"]
    assert _img_files(library_dir, project) == []  # 未落盘


def test_artwork_upload_not_an_image_422(client, project, library_dir):
    """伪造图片字节：写盘前解码校验拒绝，且 yaml 不被改动。"""
    client.put(f"/api/projects/{project}/cards/测试斩", json=_battle_card())
    r = client.post(f"/api/projects/{project}/cards/测试斩/artwork?filename=x.png",
                    content="这不是图片".encode("utf-8"))
    assert r.status_code == 422 and "图片" in r.json()["detail"]
    assert _img_files(library_dir, project) == []
    assert "artwork" not in client.get(f"/api/projects/{project}/cards/测试斩").json()


def test_artwork_upload_card_not_found_404(client, project):
    r = client.post(f"/api/projects/{project}/cards/不存在/artwork?filename=x.png",
                    content=SAMPLE_ART.read_bytes())
    assert r.status_code == 404


# ---------- 协战双式神框预览（_duo 注入） ----------

def _duo_card(**kw):
    card = {"type": "协战", "name": "共鸣", "level": 1, "rarity": "R",
            "shikigami1": "测试式神", "shikigami2": "式神乙",
            "duo_frame": True, "description": "测试描述。"}
    card.update(kw)
    return card


def test_preview_duo_frame_injects_shikigami_art(client, project, library_dir):
    """协战 duo_frame 预览：_duo 按 shikigami1/2 在项目 shikigami/ 按名找式神卡，
    注入其卡图（缺省 <卡名>.png）与派系；缺式神引用的槽位留空仍渲染成功。"""
    images = library_dir / project / "images"
    shutil.copy2(SAMPLE_ART, images / "测试式神.png")  # 槽位1：缺省 <卡名>.png 命中
    client.put(f"/api/projects/{project}/cards/shiki-b",
               json={"type": "式神", "name": "式神乙", "faction": "苍叶", "power": 2,
                     "health": 5, "artwork": {"images": [{"path": "式神乙.png"}]}})
    shutil.copy2(SAMPLE_ART, images / "式神乙.png")     # 槽位2：显式 artwork path
    assert client.put(f"/api/projects/{project}/cards/共鸣", json=_duo_card()).status_code == 200
    on = client.post(f"/api/projects/{project}/cards/共鸣/preview", json={})
    assert on.status_code == 200 and _assert_tight_card(on)
    # 关闭 duo_frame：渲染不同（override 整体替换口径）
    off = client.post(f"/api/projects/{project}/cards/共鸣/preview",
                      json={"card": _duo_card(duo_frame=False)})
    assert off.status_code == 200 and off.content != on.content
    # 缺式神引用：槽位 None 回退空菱形，仍 200
    missing = client.post(f"/api/projects/{project}/cards/共鸣/preview",
                          json={"card": _duo_card(shikigami1="无此人", shikigami2="也无此人")})
    assert missing.status_code == 200 and _assert_tight_card(missing)
    assert missing.content != on.content  # 空槽位 ≠ 注入头像


def test_preview_duo_frame_missing_image_slot_empty(client, project, library_dir):
    """式神卡存在但卡图缺失：该槽位 None（不劫持占位图回退），渲染仍成功。"""
    client.put(f"/api/projects/{project}/cards/shiki-b",
               json={"type": "式神", "name": "式神乙", "faction": "苍叶", "power": 2,
                     "health": 5})
    assert client.put(f"/api/projects/{project}/cards/共鸣", json=_duo_card()).status_code == 200
    r = client.post(f"/api/projects/{project}/cards/共鸣/preview", json={})
    assert r.status_code == 200 and _assert_tight_card(r)


def test_duo_frame_not_in_saved_card(client, project):
    """_duo 是预览期内部键：不进 schema 白名单（PUT 带 _duo 拒绝），落盘卡不含 _duo。"""
    r = client.put(f"/api/projects/{project}/cards/共鸣", json={**_duo_card(), "_duo": [None, None]})
    assert r.status_code == 422
    assert client.put(f"/api/projects/{project}/cards/共鸣", json=_duo_card()).status_code == 200
    assert "_duo" not in client.get(f"/api/projects/{project}/cards/共鸣").json()


# ---------- 式神头像预览（portrait_preview，双式神框单槽位 2 倍渲染） ----------

def test_portrait_preview_shikigami_200(client, project, library_dir):
    """式神头像预览：缺图→空槽位（底板+框+派系标）仍 200；上传卡图后输出变化。"""
    empty = client.post(f"/api/projects/{project}/cards/shikigami/portrait_preview", json={})
    assert empty.status_code == 200 and empty.headers["content-type"] == "image/png"
    images = library_dir / project / "images"
    images.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SAMPLE_ART, images / "测试式神.png")  # 缺省 <卡名>.png 命中
    with_art = client.post(f"/api/projects/{project}/cards/shikigami/portrait_preview", json={})
    assert with_art.status_code == 200 and with_art.content != empty.content


def test_portrait_preview_override_transform(client, project, library_dir):
    """override 合并表单数据：portrait 偏移改变输出；派系标随 faction。"""
    images = library_dir / project / "images"
    images.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SAMPLE_ART, images / "测试式神.png")
    base = client.post(f"/api/projects/{project}/cards/shikigami/portrait_preview", json={})
    moved = client.post(
        f"/api/projects/{project}/cards/shikigami/portrait_preview",
        json={"card": {**_shikigami_card(), "portrait": {"offset_x": 8, "offset_y": -6}}})
    assert moved.status_code == 200 and moved.content != base.content
    other_faction = client.post(
        f"/api/projects/{project}/cards/shikigami/portrait_preview",
        json={"card": {**_shikigami_card(), "faction": "青岚"}})
    assert other_faction.status_code == 200 and other_faction.content != base.content


def test_portrait_preview_rejects_non_shikigami(client, project):
    """非式神卡请求头像预览 → 400；不存在的卡 → 404。"""
    client.put(f"/api/projects/{project}/cards/测试斩", json=_battle_card())
    r = client.post(f"/api/projects/{project}/cards/测试斩/portrait_preview", json={})
    assert r.status_code == 400
    assert client.post(f"/api/projects/{project}/cards/不存在/portrait_preview",
                       json={}).status_code == 404


def test_portrait_preview_rejects_derived_shikigami(client, project):
    """衍生物式神不请求头像预览/导出；主要式神仍保持可用。"""
    card = {**_shikigami_card("召唤物"), "shikigami": "测试式神", "special_type": "召唤"}
    client.put(f"/api/projects/{project}/cards/召唤物", json=card)
    r = client.post(f"/api/projects/{project}/cards/召唤物/portrait_preview", json={})
    assert r.status_code == 400 and "衍生物" in r.json()["detail"]
    assert client.post(f"/api/projects/{project}/cards/shikigami/portrait_preview",
                       json={}).status_code == 200


def test_portrait_preview_frame_toggle(client, project, library_dir):
    """头像框开关：portrait.frame=false 时预览不画斜方框与派系标（输出不同且仍 200）。"""
    images = library_dir / project / "images"
    images.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SAMPLE_ART, images / "测试式神.png")
    framed = client.post(f"/api/projects/{project}/cards/shikigami/portrait_preview", json={})
    bare = client.post(
        f"/api/projects/{project}/cards/shikigami/portrait_preview",
        json={"card": {**_shikigami_card(), "portrait": {"frame": False}}})
    assert bare.status_code == 200 and bare.content != framed.content
    assert _png_size(bare)[0] < _png_size(framed)[0]  # 不画框画布更小


# ---------- 机制 REST（全局共享池 /api/mechanisms） ----------

def _mech(name="蛊蚀", **kw):
    base = {"name": name, "frame": "skill", "text": "敌方式神气绝时结附。"}
    base.update(kw)
    return base


def test_mechanisms_empty(client):
    r = client.get("/api/mechanisms")
    assert r.status_code == 200 and r.json() == []


def test_mechanism_crud_roundtrip(client, library_dir):
    r = client.post("/api/mechanisms", json=_mech())
    assert r.status_code == 200 and r.json()["stem"] == "蛊蚀"
    assert (library_dir / "mechanisms" / "蛊蚀.yaml").is_file()
    assert client.get("/api/mechanisms").json() == [entry("蛊蚀", "蛊蚀")]
    assert client.get("/api/mechanisms/蛊蚀").json() == with_today(_mech())
    # 更新（PUT 同名覆盖）
    r = client.put("/api/mechanisms/蛊蚀", json=_mech(text="改后的描述。"))
    assert r.status_code == 200
    assert client.get("/api/mechanisms/蛊蚀").json()["text"] == "改后的描述。"
    # 删除
    assert client.delete("/api/mechanisms/蛊蚀").status_code == 200
    assert client.get("/api/mechanisms").json() == []
    assert client.delete("/api/mechanisms/蛊蚀").status_code == 404


def test_mechanism_create_duplicate_409(client):
    assert client.post("/api/mechanisms", json=_mech()).status_code == 200
    r = client.post("/api/mechanisms", json=_mech())
    assert r.status_code == 409 and "已存在" in r.json()["detail"]


def test_mechanism_rename_via_put(client, library_dir):
    client.post("/api/mechanisms", json=_mech())
    r = client.put("/api/mechanisms/蛊蚀", json=_mech(name="魔蛊"))
    assert r.status_code == 200 and r.json()["stem"] == "魔蛊"
    assert not (library_dir / "mechanisms" / "蛊蚀.yaml").exists()
    assert client.get("/api/mechanisms").json() == [entry("魔蛊", "魔蛊")]


def test_mechanism_save_schema_error_422_chinese(client):
    r = client.post("/api/mechanisms", json=_mech(frame="gold"))
    assert r.status_code == 422
    assert any("frame" in e for e in r.json()["detail"])
    assert client.get("/api/mechanisms").json() == []  # 校验不过不落盘


def test_mechanism_badge_only_on_seal(client):
    r = client.post("/api/mechanisms", json=_mech(badge="bless"))
    assert r.status_code == 422 and any("badge" in e for e in r.json()["detail"])
    r = client.post("/api/mechanisms",
                    json=_mech(name="加护", frame="seal", badge="bless"))
    assert r.status_code == 200


def test_mechanism_unknown_field_422(client):
    r = client.post("/api/mechanisms", json=_mech(未知字段=1))
    assert r.status_code == 422 and any("未知字段" in e for e in r.json()["detail"])


def test_mechanism_not_found_404(client):
    assert client.get("/api/mechanisms/不存在").status_code == 404
    assert client.post("/api/mechanisms/不存在/preview", json={}).status_code == 404


def test_mechanism_put_upsert_creates(client):
    """PUT 为 upsert 语义（与卡牌保存一致）：路径名不存在时新建。"""
    r = client.put("/api/mechanisms/新机制", json=_mech(name="新机制"))
    assert r.status_code == 200 and r.json()["stem"] == "新机制"
    assert client.get("/api/mechanisms").json() == [entry("新机制", "新机制")]


def test_mechanism_preview_png(client):
    client.post("/api/mechanisms", json=_mech())
    r = client.post("/api/mechanisms/蛊蚀/preview", json={})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert _png_size(r)[0] > 0
    # 无 body 也可预览（渲染落盘数据）
    assert client.post("/api/mechanisms/蛊蚀/preview").status_code == 200


def test_mechanism_preview_override_unsaved(client):
    """body 带未保存表单数据（mechanism 键整体替换）直接渲染，不改落盘文件。"""
    client.post("/api/mechanisms", json=_mech())
    override = _mech(frame="seal", badge="eclipse", text="受到的伤害+1。")
    r = client.post("/api/mechanisms/蛊蚀/preview", json={"mechanism": override})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get("/api/mechanisms/蛊蚀").json() == with_today(_mech())  # 落盘未变


def test_mechanism_preview_unrenderable_422(client):
    client.post("/api/mechanisms", json=_mech())
    badge_on_skill = _mech(badge="bless")  # badge 仅 seal：渲染层拒绝
    r = client.post("/api/mechanisms/蛊蚀/preview", json={"mechanism": badge_on_skill})
    assert r.status_code == 422 and "渲染失败" in r.json()["detail"]


def test_mechanism_cross_project_visible(client):
    """机制全局共享：不属于任何项目，项目列表不出现 mechanisms。"""
    client.post("/api/projects", json={"name": "项目甲"})
    client.post("/api/mechanisms", json=_mech())
    assert client.get("/api/projects").json() == ["项目甲"]
    assert client.get("/api/mechanisms").json() == [entry("蛊蚀", "蛊蚀")]


# ---------- 版本日期与多版本（v1.6.0） ----------

def test_new_version_endpoint_and_grouped_list(client, project):
    client.put(f"/api/projects/{project}/cards/测试斩", json=_battle_card())
    r = client.post(f"/api/projects/{project}/cards/测试斩/new_version", json={"date": "20990102"})
    assert r.status_code == 200 and r.json()["stem"] == "测试斩@20990102"
    listed = client.get(f"/api/projects/{project}/cards").json()["cards"]
    assert len(listed) == 1 and listed[0]["count"] == 2
    assert listed[0]["stem"] == "测试斩@20990102"
    assert [v["date"] for v in listed[0]["versions"]] == ["20990102", TODAY]
    assert client.post(f"/api/projects/{project}/cards/测试斩/new_version",
                       json={"date": "20990102"}).status_code == 409
    assert client.post(f"/api/projects/{project}/cards/测试斩/new_version",
                       json={"date": "不是日期"}).status_code == 422


def test_upload_artwork_shared_across_versions(client, project, library_dir):
    """同图同设置：上传到任一版本，同组其他版本 artwork 同步。"""
    client.put(f"/api/projects/{project}/cards/测试斩", json=_battle_card())
    client.post(f"/api/projects/{project}/cards/测试斩/new_version", json={"date": "20990102"})
    r = client.post(f"/api/projects/{project}/cards/测试斩@20990102/artwork?filename=a.png",
                    content=SAMPLE_ART.read_bytes(),
                    headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 200
    old = client.get(f"/api/projects/{project}/cards/测试斩").json()
    assert old["artwork"]["images"][0]["path"] == r.json()["path"]


def test_save_invalid_version_date_422(client, project):
    r = client.put(f"/api/projects/{project}/cards/测试斩",
                   json={**_battle_card(), "version_date": "20260230"})
    assert r.status_code == 422 and any("version_date" in e for e in r.json()["detail"])


def test_mechanism_new_version_endpoint(client):
    client.post("/api/mechanisms", json=_mech())
    r = client.post("/api/mechanisms/蛊蚀/new_version", json={"date": "20990102"})
    assert r.status_code == 200 and r.json()["stem"] == "蛊蚀@20990102"
    listed = client.get("/api/mechanisms").json()
    assert len(listed) == 1 and listed[0]["count"] == 2
    assert listed[0]["stem"] == "蛊蚀@20990102"
    assert client.post("/api/mechanisms/蛊蚀/new_version",
                       json={"date": "20990102"}).status_code == 409


def test_upload_artwork_uses_form_id(client, project):
    """上传卡图优先按 id 命名：query 带表单当前 id（可未保存）；两位简写同样展开。"""
    client.put(f"/api/projects/{project}/cards/shikigami", json={**_shikigami_card(), "id": "100101"})
    client.put(f"/api/projects/{project}/cards/测试斩", json=_battle_card())
    r = client.post(f"/api/projects/{project}/cards/测试斩/artwork?filename=a.png&id=01",
                    content=SAMPLE_ART.read_bytes(),
                    headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 200 and r.json()["path"] == "10010101.png"
    # 无 id 卡且不带 query：回退卡名命名
    client.put(f"/api/projects/{project}/cards/无id卡",
               json={"type": "法术", "name": "无id卡", "level": 1, "rarity": "R"})
    r = client.post(f"/api/projects/{project}/cards/无id卡/artwork?filename=a.png",
                    content=SAMPLE_ART.read_bytes(),
                    headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 200 and r.json()["path"] == "无id卡.png"
