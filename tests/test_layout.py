import json
from pathlib import Path

import pytest

from bwpdiy.render import layout

TYPES = ["式神", "战斗", "法术", "形态", "幻境", "协战"]


def test_default_layout_covers_all_types():
    layouts = layout.load_layouts(Path("不存在的目录"))
    for t in TYPES:
        tl = layout.get_type_layout(layouts, t)
        assert "elements" in tl and "text_regions" in tl
        assert tl["text_regions"]["name"]["wrap"] is False
        assert tl["text_regions"]["desc"]["wrap"] is True
        for region in tl["text_regions"].values():
            assert len(region["polygon"]) >= 3
            assert region["font"] in ("name", "desc")


def test_assets_layout_takes_precedence(tmp_path):
    custom = {t: {"elements": {}, "text_regions": {}} for t in TYPES}
    custom["战斗"]["elements"]["rarity"] = {"kind": "rarity_flank", "pos": [1, 2], "gap": 16, "size": 24}
    (tmp_path / "layout.json").write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
    layouts = layout.load_layouts(tmp_path)
    assert layouts["战斗"]["elements"]["rarity"]["pos"] == [1, 2]


def test_unknown_type_raises():
    layouts = layout.load_layouts(Path("不存在的目录"))
    with pytest.raises(ValueError, match="布局缺失"):
        layout.get_type_layout(layouts, "不存在")


def test_expected_elements_per_type():
    layouts = layout.load_layouts(Path("不存在的目录"))
    assert set(layouts["式神"]["elements"]) == {"faction", "power", "health"}
    assert set(layouts["战斗"]["elements"]) == {"level", "rarity", "power", "shield"}
    assert set(layouts["法术"]["elements"]) == {"level", "rarity", "power", "health"}
    assert set(layouts["形态"]["elements"]) == {"level", "rarity", "power", "health"}
    assert set(layouts["幻境"]["elements"]) == {"level", "rarity", "durability"}
    assert set(layouts["协战"]["elements"]) == {"level", "rarity"}
