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


@pytest.mark.parametrize("card_type", ["式神", "战斗", "法术", "形态", "幻境", "协战"])
def test_preview_all_types(client, card_type):
    from bwpdiy.render.layout import load_layouts, get_type_layout
    tl = get_type_layout(load_layouts(client.app.state.assets_dir), card_type)
    r = client.post("/api/preview", json={"type": card_type, "layout": tl})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"


def test_preview_bad_type(client):
    r = client.post("/api/preview", json={"type": "不存在", "layout": {"elements": {}, "text_regions": {}}})
    assert r.status_code == 400
