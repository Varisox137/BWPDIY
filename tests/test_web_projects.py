"""web 层项目/卡牌 REST API 测试：CRUD 全路径、错误映射、项目卡预览、卡图上传（id/卡名命名）。

fixture 用 tmp_path 的 library_dir + assets 拷贝，不碰真实 library/ 与 assets/layout.json。
存储模型：library/<项目>/{shikigami,cards}/<任意文件名>.yaml + images/；
文件名（stem）与卡名（name 字段）脱钩，list_cards 返回 {shikigami, cards} 两组 [{stem, name}]。
"""

import shutil
from io import BytesIO
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from PIL import Image

from bwpdiy.web.app import create_app

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SAMPLE_ART = Path(__file__).resolve().parent / "fixtures" / "sample_art.png"


@pytest.fixture()
def assets_dir(tmp_path) -> Path:
    dst = tmp_path / "assets"
    shutil.copytree(ASSETS, dst)
    return dst


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


def _png_size(resp) -> tuple:
    return Image.open(BytesIO(resp.content)).size


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


_SHIKI_ENTRY = {"stem": "shikigami", "name": "测试式神"}


def test_card_save_and_load_roundtrip(client, project):
    card = _battle_card()
    r = client.put(f"/api/projects/{project}/cards/测试斩", json=card)
    assert r.status_code == 200 and r.json() == {"ok": True, "updated": []}
    assert client.get(f"/api/projects/{project}/cards").json() == {
        "shikigami": [_SHIKI_ENTRY], "cards": [{"stem": "测试斩", "name": "测试斩"}]}
    got = client.get(f"/api/projects/{project}/cards/测试斩").json()
    assert got == card


def test_card_list_sorted_by_name(client, project):
    """list_cards 各组按卡内 name 排序（与文件名脱钩；stem 与名字序相反以排除按文件名排序）。"""
    client.put(f"/api/projects/{project}/cards/stem-a", json=_battle_card("B卡"))
    client.put(f"/api/projects/{project}/cards/stem-b", json=_battle_card("A卡"))
    lst = client.get(f"/api/projects/{project}/cards").json()
    assert lst["cards"] == [{"stem": "stem-b", "name": "A卡"},
                            {"stem": "stem-a", "name": "B卡"}]


def test_card_save_schema_error_422_chinese(client, project):
    bad = {"type": "战斗", "name": "测试斩", "power+": "很大"}
    r = client.put(f"/api/projects/{project}/cards/测试斩", json=bad)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert any("rarity" in m for m in detail)      # 缺 rarity 一次报全
    assert any("power+" in m for m in detail)
    assert client.get(f"/api/projects/{project}/cards").json()["cards"] == []  # 未落盘


def test_card_save_name_decoupled_from_stem(client, project):
    """卡名与文件名脱钩：stem 与 name 不一致可保存（不再强制一致）。"""
    r = client.put(f"/api/projects/{project}/cards/stem-1", json=_battle_card("卡内名"))
    assert r.status_code == 200
    lst = client.get(f"/api/projects/{project}/cards").json()
    assert lst["cards"] == [{"stem": "stem-1", "name": "卡内名"}]
    assert client.get(f"/api/projects/{project}/cards/stem-1").json()["name"] == "卡内名"


def test_card_save_shikigami_rename_syncs_references(client, project):
    """式神卡改名：save_card 联动更新同项目卡的 shikigami 引用，updated 返回被更新卡名。"""
    client.put(f"/api/projects/{project}/cards/测试斩", json=_battle_card())
    r = client.put(f"/api/projects/{project}/cards/shikigami", json=_shikigami_card("新名"))
    assert r.status_code == 200
    assert r.json() == {"ok": True, "updated": ["测试斩"]}
    assert client.get(f"/api/projects/{project}/cards/测试斩").json()["shikigami"] == "新名"
    lst = client.get(f"/api/projects/{project}/cards").json()
    assert lst["shikigami"] == [{"stem": "shikigami", "name": "新名"}]


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
    assert client.get(f"/api/projects/{project}/cards/共鸣").json() == card
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
    """无 artwork 的式神卡：占位图回退，渲染出完整 512×512 PNG。"""
    r = client.post(f"/api/projects/{project}/cards/shikigami/preview", json={})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert _png_size(r) == (512, 512)


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


def test_preview_missing_image_fallback(client, project):
    """artwork.images 指向缺失文件：回退占位图而非 422。"""
    card = _battle_card()
    card["artwork"] = {"images": [{"path": "不存在的图.png", "scale": 1.2}]}
    assert client.put(f"/api/projects/{project}/cards/测试斩", json=card).status_code == 200
    r = client.post(f"/api/projects/{project}/cards/测试斩/preview", json={})
    assert r.status_code == 200 and _png_size(r) == (512, 512)


def test_preview_uses_project_images_dir(client, project, library_dir):
    """artwork 基准目录 = 项目 images/：图在 images/ 下即可按相对路径渲染。"""
    shutil.copy2(SAMPLE_ART, library_dir / project / "images" / "卡图.png")
    card = _battle_card()
    card["artwork"] = {"images": [{"path": "卡图.png"}]}
    assert client.put(f"/api/projects/{project}/cards/测试斩", json=card).status_code == 200
    r = client.post(f"/api/projects/{project}/cards/测试斩/preview", json={})
    assert r.status_code == 200 and _png_size(r) == (512, 512)


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
    assert r.status_code == 200 and _png_size(r) == (512, 512)
    assert r.content != base.content  # 覆盖生效（盘上 shikigami 是式神卡，覆盖为战斗卡）


def test_preview_override_artwork_outside_images_422(client, project):
    """覆盖 card 的 artwork 指向 images/ 外的真实文件：渲染层路径校验拒绝（不读本机任意文件）。"""
    override = _battle_card()
    override["artwork"] = {"images": [{"path": str(SAMPLE_ART.resolve())}]}
    r = client.post(f"/api/projects/{project}/cards/shikigami/preview", json={"card": override})
    assert r.status_code == 422 and "渲染失败" in r.json()["detail"]


def test_preview_unrenderable_card_422(client, project, library_dir):
    """手写空 yaml（load 不校验）→ 渲染异常映射 422。"""
    (library_dir / project / "cards" / "空卡.yaml").write_text("", encoding="utf-8")
    r = client.post(f"/api/projects/{project}/cards/空卡/preview", json={})
    assert r.status_code == 422 and "渲染失败" in r.json()["detail"]


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
    assert r.status_code == 200 and _png_size(r) == (512, 512)


def test_preview_multi_images_uses_first(client, project, library_dir):
    """多图列表：渲染消费首图，首图存在时后续条目缺失不影响。"""
    shutil.copy2(SAMPLE_ART, library_dir / project / "images" / "卡图.png")
    card = _battle_card()
    card["artwork"] = {"images": [{"path": "卡图.png"}, {"path": "异画缺图.png"}]}
    assert client.put(f"/api/projects/{project}/cards/测试斩", json=card).status_code == 200
    r = client.post(f"/api/projects/{project}/cards/测试斩/preview", json={})
    assert r.status_code == 200 and _png_size(r) == (512, 512)


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
    assert r.status_code == 200 and _png_size(r) == (512, 512)


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
    assert on.status_code == 200 and _png_size(on) == (512, 512)
    # 关闭 duo_frame：渲染不同（override 整体替换口径）
    off = client.post(f"/api/projects/{project}/cards/共鸣/preview",
                      json={"card": _duo_card(duo_frame=False)})
    assert off.status_code == 200 and off.content != on.content
    # 缺式神引用：槽位 None 回退空菱形，仍 200
    missing = client.post(f"/api/projects/{project}/cards/共鸣/preview",
                          json={"card": _duo_card(shikigami1="无此人", shikigami2="也无此人")})
    assert missing.status_code == 200 and _png_size(missing) == (512, 512)
    assert missing.content != on.content  # 空槽位 ≠ 注入头像


def test_preview_duo_frame_missing_image_slot_empty(client, project, library_dir):
    """式神卡存在但卡图缺失：该槽位 None（不劫持占位图回退），渲染仍成功。"""
    client.put(f"/api/projects/{project}/cards/shiki-b",
               json={"type": "式神", "name": "式神乙", "faction": "苍叶", "power": 2,
                     "health": 5})
    assert client.put(f"/api/projects/{project}/cards/共鸣", json=_duo_card()).status_code == 200
    r = client.post(f"/api/projects/{project}/cards/共鸣/preview", json={})
    assert r.status_code == 200 and _png_size(r) == (512, 512)


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
