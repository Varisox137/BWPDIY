"""web 层项目/卡牌 REST API 测试：CRUD 全路径、错误映射、项目卡预览。

fixture 用 tmp_path 的 library_dir + assets 拷贝，不碰真实 library/ 与 assets/layout.json。
"""

import shutil
from io import BytesIO
from pathlib import Path

import pytest
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


def _battle_card(name="测试斩"):
    return {"type": "战斗", "name": name, "level": 2, "rarity": "R",
            "shikigami": "测试项目", "power+": 1, "shield+": 1,
            "description": "测试描述。"}


def _png_size(resp) -> tuple:
    return Image.open(BytesIO(resp.content)).size


# ---------- 项目 CRUD ----------

def test_projects_empty(client):
    r = client.get("/api/projects")
    assert r.status_code == 200 and r.json() == []


def test_project_create_with_default_shikigami(client, library_dir):
    r = client.post("/api/projects", json={"name": "测试项目"})
    assert r.status_code == 200 and r.json()["ok"]
    assert client.get("/api/projects").json() == ["测试项目"]
    # 出厂含默认式神卡
    assert client.get("/api/projects/测试项目/cards").json() == ["shikigami"]
    card = client.get("/api/projects/测试项目/cards/shikigami").json()
    assert card["type"] == "式神" and card["name"] == "测试项目"
    assert (library_dir / "测试项目" / "images").is_dir()


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
    client.post("/api/projects", json={"name": "测试项目"})
    return "测试项目"


def test_card_save_and_load_roundtrip(client, project):
    card = _battle_card()
    r = client.put(f"/api/projects/{project}/cards/测试斩", json=card)
    assert r.status_code == 200 and r.json()["ok"]
    assert client.get(f"/api/projects/{project}/cards").json() == ["shikigami", "测试斩"]
    got = client.get(f"/api/projects/{project}/cards/测试斩").json()
    assert got == card


def test_card_save_schema_error_422_chinese(client, project):
    bad = {"type": "战斗", "name": "测试斩", "power+": "很大"}
    r = client.put(f"/api/projects/{project}/cards/测试斩", json=bad)
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert any("rarity" in m for m in detail)      # 缺 rarity 一次报全
    assert any("power+" in m for m in detail)
    assert client.get(f"/api/projects/{project}/cards").json() == ["shikigami"]  # 未落盘


def test_card_save_name_mismatch_422(client, project):
    r = client.put(f"/api/projects/{project}/cards/文件名", json=_battle_card("卡内名"))
    assert r.status_code == 422
    assert any("一致" in m for m in r.json()["detail"])


def test_card_save_shikigami_must_be_shikigami_type(client, project):
    r = client.put(f"/api/projects/{project}/cards/shikigami", json=_battle_card("shikigami"))
    assert r.status_code == 422


def test_card_save_cards_dir_no_shikigami_type(client, project):
    card = {"type": "式神", "name": "第二式神", "faction": "红莲", "power": 3, "health": 4}
    r = client.put(f"/api/projects/{project}/cards/第二式神", json=card)
    assert r.status_code == 422


def test_card_save_shikigami_overwrite(client, project):
    card = {"type": "式神", "name": "改名式神", "faction": "苍叶", "power": 2, "health": 5}
    r = client.put(f"/api/projects/{project}/cards/shikigami", json=card)
    assert r.status_code == 200
    assert client.get(f"/api/projects/{project}/cards/shikigami").json()["health"] == 5


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
    assert client.get(f"/api/projects/{project}/cards").json() == ["shikigami"]
    assert client.delete(f"/api/projects/{project}/cards/测试斩").status_code == 404


def test_card_delete_shikigami_refused(client, project):
    r = client.delete(f"/api/projects/{project}/cards/shikigami")
    assert r.status_code == 422 and "不可删除" in r.json()["detail"]
    assert client.get(f"/api/projects/{project}/cards").json() == ["shikigami"]


@pytest.mark.parametrize("bad", ["a\\b", "evil.", "NUL"])
def test_card_illegal_name_422(client, project, bad):
    card = _battle_card(bad)
    r = client.put(f"/api/projects/{project}/cards/{bad}", json=card)
    assert r.status_code == 422


# ---------- 项目卡预览 ----------

def test_preview_default_shikigami_fallback_art(client, project):
    """无 artwork 的出厂式神卡：占位图回退，渲染出完整 512×512 PNG。"""
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


def test_preview_unrenderable_card_422(client, project, library_dir):
    """手写空 yaml（load 不校验）→ 渲染异常映射 422。"""
    (library_dir / project / "cards" / "空卡.yaml").write_text("", encoding="utf-8")
    r = client.post(f"/api/projects/{project}/cards/空卡/preview", json={})
    assert r.status_code == 422 and "渲染失败" in r.json()["detail"]


# ---------- 页面路由 ----------

def test_editor_page_at_root(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]


def test_layout_page_kept(client):
    r = client.get("/layout")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
