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


def test_frozen_layout_uses_home_config(tmp_path, monkeypatch):
    from bwpdiy import resources

    home = tmp_path / "home"
    assets = tmp_path / "assets"
    assets.mkdir()
    local = {"战斗": {"elements": {"name": {"pos": [1, 2]}}, "text_regions": {}}}
    user = {"战斗": {"elements": {"name": {"pos": [9, 10]}}, "text_regions": {}}}
    (assets / "layout.json").write_text(json.dumps(local), encoding="utf-8")
    config = home / ".bwpdiy" / "layout.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps(user), encoding="utf-8")
    monkeypatch.setattr(resources, "is_frozen", lambda: True)
    monkeypatch.setattr(resources.Path, "home", lambda: home)

    assert resources.layout_config_path(assets) == config
    assert layout.load_layouts(assets)["战斗"]["elements"]["name"]["pos"] == [9, 10]


def test_entity_layout_backfilled(tmp_path):
    (tmp_path / "layout.json").write_text(
        '{"式神": {"elements": {}, "text_regions": {}}}', encoding="utf-8")
    layouts = layout.load_layouts(tmp_path)
    entity = layouts["对局式神"]
    assert entity["version"] == 2
    assert entity["art_window"] == {
        "center": [48, 72], "width": 84, "height": 132,
        "frame_center": True, "offset_y": 0,
    }
    assert entity["elements"]["level"]["pos"] == [48, 137]
    assert "机制" in layouts
    assert "text_regions" not in entity


def test_entity_layout_independent_from_card_types(tmp_path):
    custom = {t: {"elements": {"power": _stat(30)}, "text_regions": {}} for t in TYPES}
    custom["对局式神"] = {"version": 2, "elements": {"power": _stat(18)}}
    (tmp_path / "layout.json").write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
    layouts = layout.load_layouts(tmp_path)
    assert layouts["对局式神"]["elements"]["power"]["font_size"] == 18
    assert all(layouts[t]["elements"]["power"]["font_size"] == 30 for t in TYPES)


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
    assert set(layouts["协战"]["elements"]) == {"level", "rarity", "duo_frame"} | base


def _stat(font_size):
    return {"kind": "stat", "field": "power+", "pos": [160, 485],
            "icon_size": 32, "num_offset": [22, 0], "font_size": font_size}


def test_shipped_layouts_schema_current():
    """出厂与包内默认布局：signed/icon/icon_neg 键已删除；stat 具备 sign_offset/sign_size_plus/sign_size_minus；
    四类带符号数值（战斗力量/护破甲、法术觉醒力量/生命）具备 group_offset。"""
    for path in (Path("assets"), Path("bwpdiy/render")):
        layouts = layout.load_layouts(path)
        for t in TYPES:
            elems = layouts[t]["elements"]
            for name, elem in elems.items():
                assert "signed" not in elem, f"{path}/{t}/{name} 仍含 signed"
                assert "icon" not in elem and "icon_neg" not in elem, \
                    f"{path}/{t}/{name} 仍含 icon/icon_neg"
                if elem["kind"] == "stat":
                    assert isinstance(elem.get("sign_offset"), list)
                    assert elem.get("sign_size_plus", 0) > 0
                    assert elem.get("sign_size_minus", 0) > 0
                    if elem["field"] in ("power+", "shield+", "health+"):
                        assert isinstance(elem.get("group_offset"), list), \
                            f"{path}/{t}/{name} 缺 group_offset"
            rarity = elems.get("rarity")
            if rarity is not None:
                assert rarity["gap"] > 0 and rarity["margin"] > 0


# 各类型 stat 元素 field 的钉死口径（与 stat 适用矩阵、样卡字段一致）
EXPECTED_STAT_FIELDS = {
    "式神": {"power": "power", "health": "health"},
    "战斗": {"power": "power+", "shield": "shield+"},
    "法术": {"power": "power+", "health": "health+"},
    "形态": {"power": "power", "health": "health"},
    "幻境": {"durability": "durability"},
    "协战": {},
}


def test_shipped_layout_stat_fields():
    """出厂与包内默认布局的 stat 元素 field 按类型钉死。"""
    for path in (Path("assets"), Path("bwpdiy/render")):
        layouts = layout.load_layouts(path)
        for t in TYPES:
            fields = {n: e["field"] for n, e in layouts[t]["elements"].items()
                      if e["kind"] == "stat"}
            assert fields == EXPECTED_STAT_FIELDS[t], f"{path}/{t}: {fields}"


def test_card_layout_fields_independent_across_types(tmp_path):
    custom = {t: {
        "elements": {"power": _stat(30)},
        "text_regions": {"desc": {
            "center": [256, 426], "width": 252, "height": 80,
            "font_range": [22, 12], "wrap": True, "font": "desc", "icon_scale": 1.0,
        }},
    } for t in TYPES}
    custom["法术"]["elements"]["power"].update(font_size=24, num_offset=[30, 0])
    custom["法术"]["text_regions"]["desc"].update(
        width=300, font_range=[18, 10], icon_scale=1.25)
    (tmp_path / "layout.json").write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
    layouts = layout.load_layouts(tmp_path)

    assert layouts["法术"]["elements"]["power"]["font_size"] == 24
    assert layouts["法术"]["elements"]["power"]["num_offset"] == [30, 0]
    assert layouts["法术"]["text_regions"]["desc"]["width"] == 300
    assert layouts["法术"]["text_regions"]["desc"]["font_range"] == [18, 10]
    assert layouts["法术"]["text_regions"]["desc"]["icon_scale"] == 1.25
    for card_type in TYPES:
        if card_type == "法术":
            continue
        assert layouts[card_type]["elements"]["power"]["font_size"] == 30
        assert layouts[card_type]["elements"]["power"]["num_offset"] == [22, 0]
        assert layouts[card_type]["text_regions"]["desc"]["width"] == 252
        assert layouts[card_type]["text_regions"]["desc"]["font_range"] == [22, 12]
        assert layouts[card_type]["text_regions"]["desc"]["icon_scale"] == 1.0


def test_frame_variant_sparse_layout_merges_without_polluting_norm(tmp_path):
    custom = {"战斗": {
        "elements": {"name": {"kind": "text", "pos": [100, 60], "font_size": 30}},
        "text_regions": {},
        "frame_variants": {"black": {"elements": {"name": {"pos": [12, 34]}}}},
    }}
    (tmp_path / "layout.json").write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
    layouts = layout.load_layouts(tmp_path)

    norm = layout.get_type_layout(layouts, "战斗")
    black = layout.get_type_layout(layouts, "战斗", "black")
    blue = layout.get_type_layout(layouts, "战斗", "blue")
    assert norm["elements"]["name"]["pos"] == [100, 60]
    assert black["elements"]["name"] == {"kind": "text", "pos": [12, 34], "font_size": 30}
    assert blue == norm
    assert "frame_variants" not in norm and "frame_variants" not in black


def test_frame_variant_layout_independent_across_types(tmp_path):
    custom = {}
    for card_type in layout.FRAME_LAYOUT_TYPES:
        custom[card_type] = {
            "elements": {"power": _stat(30)},
            "text_regions": {},
            "frame_variants": {"black": {"elements": {"power": {"font_size": 24}}}},
        }
    custom["法术"]["frame_variants"]["black"]["elements"]["power"]["font_size"] = 18
    custom["战斗"]["frame_variants"]["black"]["elements"]["power"]["pos"] = [8, 9]
    (tmp_path / "layout.json").write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
    layouts = layout.load_layouts(tmp_path)

    for card_type in layout.FRAME_LAYOUT_TYPES:
        assert layout.get_type_layout(layouts, card_type)["elements"]["power"]["font_size"] == 30
        assert layout.get_type_layout(
            layouts, card_type, "blue")["elements"]["power"]["font_size"] == 30
        expected = 18 if card_type == "法术" else 24
        assert layout.get_type_layout(
            layouts, card_type, "black")["elements"]["power"]["font_size"] == expected
    assert layout.get_type_layout(
        layouts, "战斗", "black")["elements"]["power"]["pos"] == [8, 9]


def test_merge_card_layout():
    """单卡布局覆盖：按键两级合并、base 不被修改、畸形 override 安全跳过。"""
    base = {"elements": {"name": {"kind": "text", "pos": [256, 60], "font_size": 30}},
            "text_regions": {"desc": {"center": [256, 400], "width": 400}}}
    override = {"elements": {"name": {"pos": [200, 60]}, "rarity": {"gap": 40}},
                "text_regions": {"desc": {"width": 300}},
                "junk_section": {"x": 1}, "bad": "not-dict"}
    merged = layout.merge_card_layout(base, override)
    assert merged["elements"]["name"] == {"kind": "text", "pos": [200, 60], "font_size": 30}
    assert merged["elements"]["rarity"] == {"gap": 40}  # 全局没有的元素也能补入
    assert merged["text_regions"]["desc"]["width"] == 300
    assert "junk_section" not in merged and "bad" not in merged
    # base 未被改动
    assert base["elements"]["name"]["pos"] == [256, 60]
    assert "rarity" not in base["elements"]
    # 非 dict override / None：原样（深拷贝）返回
    assert layout.merge_card_layout(base, None)["elements"]["name"]["pos"] == [256, 60]
    assert layout.merge_card_layout(base, "junk")["elements"]["name"]["pos"] == [256, 60]


def _write_entity_layout(tmp_path, entity):
    (tmp_path / "layout.json").write_text(
        json.dumps({"对局式神": entity}, ensure_ascii=False), encoding="utf-8")


def test_legacy_default_entity_layout_migrates_to_96(tmp_path):
    legacy = {
        "elements": {
            "level": {"kind": "level_badge", "pos": [32, 88], "base_size": 18,
                      "num_size": 14, "num_offset": [0, 0]},
            "power": {"kind": "stat", "field": "power", "pos": [10, 82],
                      "icon_size": 16, "num_offset": [0, 10],
                      "font_size": 14, "stroke_width": 1},
            "health": {"kind": "stat", "field": "health", "pos": [54, 82],
                       "icon_size": 16, "num_offset": [0, 10],
                       "font_size": 14, "stroke_width": 1},
            "combat_power": {"kind": "stat", "field": "combat_power", "pos": [10, 62],
                             "icon_size": 14, "num_offset": [0, 9],
                             "font_size": 12, "stroke_width": 1},
            "shield": {"kind": "stat", "field": "shield", "pos": [54, 62],
                       "icon_size": 14, "num_offset": [0, 9],
                       "font_size": 12, "stroke_width": 1},
        },
    }
    _write_entity_layout(tmp_path, legacy)
    entity = layout.load_layouts(tmp_path)["对局式神"]
    assert entity["version"] == 2
    assert entity["art_window"] == {
        "center": [48, 72], "width": 84, "height": 132,
        "frame_center": True, "offset_y": 0,
    }
    assert entity["elements"]["level"] == {
        "kind": "level_badge", "pos": [48, 132], "base_size": 27,
        "num_size": 21, "num_offset": [0, 0],
    }
    assert entity["elements"]["power"]["pos"] == [15, 123]
    assert entity["elements"]["power"]["num_offset"] == [0, 6]
    assert entity["elements"]["power"]["icon_size"] == 24
    assert entity["elements"]["power"]["font_size"] == 21
    assert entity["elements"]["combat_power"]["num_offset"] == [0, 5]
    assert entity["elements"]["shield"]["num_offset"] == [0, 5]


def test_legacy_custom_entity_numbers_scale_once(tmp_path):
    legacy = {
        "elements": {
            "level": {"kind": "level_badge", "pos": [20, 30], "base_size": 20,
                      "num_size": 10, "num_offset": [2, 4]},
            "power": {"kind": "stat", "field": "power", "pos": [8, 70],
                      "icon_size": 20, "num_offset": [1, 12],
                      "font_size": 10, "stroke_width": 2},
        },
    }
    _write_entity_layout(tmp_path, legacy)
    migrated = layout.load_layouts(tmp_path)
    entity = migrated["对局式神"]
    assert entity["elements"]["level"] == {
        "kind": "level_badge", "pos": [30, 45], "base_size": 30,
        "num_size": 15, "num_offset": [3, 6],
    }
    assert entity["elements"]["power"] == {
        "kind": "stat", "field": "power", "pos": [12, 105],
        "icon_size": 30, "num_offset": [1.5, 18],
        "font_size": 15, "stroke_width": 3,
    }
    _write_entity_layout(tmp_path, migrated["对局式神"])
    assert layout.load_layouts(tmp_path) == migrated


@pytest.mark.parametrize("element_name, offset_y, expected", [
    ("power", 10, 6),
    ("health", 10, 6),
    ("combat_power", 9, 5),
    ("shield", 9, 5),
    ("level", 10, 15),
    ("level", 9, 13.5),
    ("combat_power", 10, 15),
    ("shield", 10, 15),
    ("power", 9, 13.5),
    ("health", 9, 13.5),
])
def test_legacy_num_offset_special_cases_depend_on_element_name(
        tmp_path, element_name, offset_y, expected):
    _write_entity_layout(tmp_path, {
        "elements": {element_name: {"num_offset": [0, offset_y]}},
    })
    entity = layout.load_layouts(tmp_path)["对局式神"]
    assert entity["elements"][element_name]["num_offset"] == [0, expected]


def test_version_2_entity_layout_only_deep_fills_defaults(tmp_path):
    from bwpdiy.render.entity import _DEFAULT_LAYOUT

    current = {
        "version": 2,
        "art_window": {"width": 100},
        "elements": {"level": {"pos": [32, 88], "num_offset": [0, 10]}},
    }
    _write_entity_layout(tmp_path, current)
    entity = layout.load_layouts(tmp_path)["对局式神"]
    assert entity["version"] == 2
    assert entity["art_window"] == {
        "center": [48, 72], "width": 100, "height": 132,
        "frame_center": True, "offset_y": 0,
    }
    assert entity["elements"]["level"]["pos"] == [32, 88]
    assert entity["elements"]["level"]["num_offset"] == [0, 10]
    assert entity["elements"]["level"]["base_size"] == 27
    assert entity["elements"]["power"] == _DEFAULT_LAYOUT["elements"]["power"]


def test_three_default_entity_layouts_are_synchronized():
    from bwpdiy.render.entity import _DEFAULT_LAYOUT

    packaged = layout.load_layouts(Path("bwpdiy/render"))["对局式神"]
    shipped = layout.load_layouts(Path("assets"))["对局式神"]
    assert packaged == shipped == _DEFAULT_LAYOUT
    assert packaged["version"] == 2
    assert packaged["elements"]["power"]["num_offset"] == [-1, 1]
    assert packaged["elements"]["combat_power"]["num_offset"] == [1, -1]
    assert packaged["elements"]["shield"]["num_offset"] == [1, 0]
