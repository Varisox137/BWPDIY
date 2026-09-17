import json
import warnings
from pathlib import Path

import pytest

from bwpdiy.render import layout

TYPES = ["式神", "战斗", "法术", "形态", "幻境", "协战"]


def test_default_layout_covers_all_types():
    layouts = layout.load_layouts(Path("不存在的目录"))
    for t in TYPES:
        tl = layout.get_type_layout(layouts, t)
        assert "elements" in tl and "text_regions" in tl
        # name/footer 是 kind=text 点元素；text_regions 只剩 desc（矩形：center+width+height）
        assert set(tl["text_regions"]) == {"desc"}
        desc = tl["text_regions"]["desc"]
        assert desc["wrap"] is True
        assert len(desc["center"]) == 2 and desc["width"] > 0 and desc["height"] > 0
        for key in ("name", "footer"):
            elem = tl["elements"][key]
            assert elem["kind"] == "text"
            assert len(elem["pos"]) == 2 and elem["font_size"] > 0
            assert elem.get("font", "name") in ("name", "desc")


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
    base = {"name", "footer"}
    assert set(layouts["式神"]["elements"]) == {"level", "faction", "power", "health"} | base
    assert set(layouts["战斗"]["elements"]) == {"level", "rarity", "power", "shield"} | base
    assert set(layouts["法术"]["elements"]) == {"level", "rarity", "power", "health"} | base
    assert set(layouts["形态"]["elements"]) == {"level", "rarity", "power", "health"} | base
    assert set(layouts["幻境"]["elements"]) == {"level", "rarity", "durability"} | base
    assert set(layouts["协战"]["elements"]) == {"level", "rarity"} | base


def _stat(font_size):
    return {"kind": "stat", "field": "power+", "icon": "ll", "pos": [160, 485],
            "icon_size": 32, "num_offset": [22, 0], "font_size": font_size, "signed": True}


def test_normalize_size_fields_majority_wins(tmp_path):
    """跨类型同名元素尺寸类字段不一致：多数值归一 + 告警；pos 不归一。"""
    custom = {t: {"elements": {"power": _stat(30)}, "text_regions": {}} for t in TYPES}
    custom["法术"]["elements"]["power"]["font_size"] = 24  # 1:5，多数值 30 胜
    custom["法术"]["elements"]["power"]["pos"] = [200, 400]  # pos 允许按类型不同
    (tmp_path / "layout.json").write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
    with pytest.warns(UserWarning, match="font_size"):
        layouts = layout.load_layouts(tmp_path)
    for t in TYPES:
        assert layouts[t]["elements"]["power"]["font_size"] == 30
    assert layouts["法术"]["elements"]["power"]["pos"] == [200, 400]


def test_normalize_size_fields_tie_takes_first(tmp_path):
    """平票时取布局表中先出现的类型的值。"""
    custom = {"战斗": {"elements": {"power": _stat(30)}, "text_regions": {}},
              "法术": {"elements": {"power": _stat(24)}, "text_regions": {}}}
    (tmp_path / "layout.json").write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
    with pytest.warns(UserWarning):
        layouts = layout.load_layouts(tmp_path)
    assert layouts["战斗"]["elements"]["power"]["font_size"] == 30
    assert layouts["法术"]["elements"]["power"]["font_size"] == 30


def test_normalize_list_fields(tmp_path):
    """num_offset/font_range 等列表型尺寸字段同样归一。"""
    custom = {t: {"elements": {"power": _stat(30)},
                  "text_regions": {"desc": {"center": [256, 426], "width": 252, "height": 80,
                                            "font_range": [22, 12], "wrap": True, "font": "desc"}}}
              for t in TYPES}
    custom["幻境"]["elements"]["power"]["num_offset"] = [30, 0]
    custom["幻境"]["text_regions"]["desc"]["font_range"] = [18, 10]
    (tmp_path / "layout.json").write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
    with pytest.warns(UserWarning):
        layouts = layout.load_layouts(tmp_path)
    for t in TYPES:
        assert layouts[t]["elements"]["power"]["num_offset"] == [22, 0]
        assert layouts[t]["text_regions"]["desc"]["font_range"] == [22, 12]


def test_normalize_mixed_types_no_crash(tmp_path):
    """手改出混合类型值（int vs list）时告警不得 TypeError，仍完成归一。"""
    custom = {"战斗": {"elements": {"power": _stat(30)}, "text_regions": {}},
              "法术": {"elements": {"power": _stat(30)}, "text_regions": {}}}
    custom["法术"]["elements"]["power"]["font_size"] = [30]  # 畸形：list 与 int 混合
    (tmp_path / "layout.json").write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
    with pytest.warns(UserWarning):
        layouts = layout.load_layouts(tmp_path)
    assert layouts["战斗"]["elements"]["power"]["font_size"] == 30
    assert layouts["法术"]["elements"]["power"]["font_size"] == [30]  # 归一写回保持原形态


def test_normalize_skips_bool_fields(tmp_path):
    """bool 是 int 子类：新增 bool 内容字段不得被误当尺寸类归一。"""
    custom = {t: {"elements": {"power": dict(_stat(30), bold=(t != "法术"))},
                  "text_regions": {}} for t in TYPES}
    (tmp_path / "layout.json").write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        layouts = layout.load_layouts(tmp_path)
    assert not [w for w in caught if issubclass(w.category, UserWarning)]
    assert layouts["法术"]["elements"]["power"]["bold"] is False
    assert layouts["战斗"]["elements"]["power"]["bold"] is True


def test_shipped_layouts_already_normalized():
    """出厂与包内默认布局不得触发归一告警（数据已一致）。"""
    for path in (Path("assets"), Path("bwpdiy/render")):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            layout.load_layouts(path)
        assert not [w for w in caught if issubclass(w.category, UserWarning)]
