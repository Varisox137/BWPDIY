from PIL import Image

import pytest

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.badges import render_element


def canvas():
    return Image.new("RGBA", (512, 512), (0, 0, 0, 0))


def opaque(img):
    return sum(1 for p in img.getdata() if p[3] > 0)


def test_level_badge(assets_dir):
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "level_badge", "pos": [120, 65], "base_size": 72, "star_size": 60, "num_size": 40}
    img = render_element(canvas(), lib, "level", elem, {"level": 2, "evolve": True})
    assert img.getpixel((120, 65))[3] > 0
    # 无 level 字段：跳过
    assert render_element(canvas(), lib, "level", elem, {}) == canvas() or \
        opaque(render_element(canvas(), lib, "level", elem, {})) == 0


def _flank_elem():
    return {"kind": "rarity_flank", "pos": [256, 358], "gap": 32, "size": 24, "margin": 8}


def test_rarity_flank_short_name_static(assets_dir):
    """短名（name_width/2+margin <= gap）双标固定在 pos±gap，位置与卡名宽度无关。"""
    lib = AssetLibrary(assets_dir)
    elem = _flank_elem()
    no_name = render_element(canvas(), lib, "rarity", elem, {"rarity": "SSR"}, {"name_width": 0})
    # 40/2+8=28 < 32：仍按默认半间距，逐像素一致
    short = render_element(canvas(), lib, "rarity", elem, {"rarity": "SSR"}, {"name_width": 40})
    assert list(no_name.getdata()) == list(short.getdata())
    assert no_name.getpixel((256 - 32, 358))[3] > 0  # 左标中心 x=224
    assert no_name.getpixel((256 - 32 - 24, 358))[3] == 0  # 左标之左无墨迹
    # 无 rarity 字段：按默认 R 渲染
    default_r = render_element(canvas(), lib, "rarity", elem, {}, {"name_width": 0})
    assert opaque(default_r) > 0
    # margin 缺省回退 8
    no_margin = render_element(canvas(), lib, "rarity",
                               {"kind": "rarity_flank", "pos": [256, 358], "gap": 32, "size": 24},
                               {"rarity": "SSR"}, {"name_width": 0})
    assert list(no_margin.getdata()) == list(no_name.getdata())


def test_rarity_flank_long_name_moves(assets_dir):
    """长名（name_width/2+margin > gap）双标按与卡名缘固定 margin 外移。"""
    lib = AssetLibrary(assets_dir)
    elem = _flank_elem()
    # 120/2+8=68 > 32：右标中心 x=256+68(+1)
    wide = render_element(canvas(), lib, "rarity", elem, {"rarity": "SSR"}, {"name_width": 120})
    assert wide.getpixel((256 + 68, 358))[3] > 0
    assert wide.getpixel((256 + 68 + 24, 358))[3] == 0
    short = render_element(canvas(), lib, "rarity", elem, {"rarity": "SSR"}, {"name_width": 0})
    assert short.getpixel((256 + 68, 358))[3] == 0


def test_rarity_flank_mirror_symmetric(assets_dir):
    """长短名下双标均关于 cx 镜像对称（右标 +1px 补偿偶数尺寸，容差 1px）。"""
    lib = AssetLibrary(assets_dir)
    elem = _flank_elem()
    for name_width in (0, 120):
        img = render_element(canvas(), lib, "rarity", elem, {"rarity": "SSR"},
                             {"name_width": name_width})
        region = img.crop((150, 340, 362, 376))
        bbox = region.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
        assert bbox
        left_edge, right_edge = bbox[0] + 150, bbox[2] + 150
        assert abs((256 - left_edge) - (right_edge - 256)) <= 1


def test_faction(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = render_element(canvas(), lib, "faction",
                         {"kind": "faction", "pos": [256, 318], "size": 44}, {"faction": "红莲"})
    assert opaque(img) > 0
    # 无相：跳过
    assert opaque(render_element(canvas(), lib, "faction",
                                 {"kind": "faction", "pos": [256, 318], "size": 44},
                                 {"faction": "无相"})) == 0


def test_stat_signed_and_offset(assets_dir):
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "power+", "icon": "ll", "pos": [160, 485],
            "icon_size": 32, "num_offset": [22, 0], "font_size": 30}
    img = render_element(canvas(), lib, "power", elem, {"type": "战斗", "power+": 1})
    assert opaque(img) > 100  # 图标+数字两处像素
    # 缺字段跳过
    assert opaque(render_element(canvas(), lib, "power", elem, {"type": "战斗"})) == 0


def test_text_element_centered(assets_dir):
    """kind=text 点元素：以 pos 为中心水平居中单行文本；字段缺失跳过。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "text", "pos": [256, 358], "font_size": 30, "font": "name"}
    img = render_element(canvas(), lib, "name", elem, {"name": "测试卡名"})
    bbox = img.getchannel("A").getbbox()
    assert bbox
    cx = (bbox[0] + bbox[2]) / 2
    assert abs(cx - 256) <= 1  # 水平居中于 pos
    cy = (bbox[1] + bbox[3]) / 2
    assert abs(cy - 358) < elem["font_size"] / 2  # 竖直在 pos 附近（mm 锚点按字体度量居中）
    # 字段缺失/为空：原样返回
    assert opaque(render_element(canvas(), lib, "footer", elem, {})) == 0


def _band_bbox(img, x0, x1, y0=460, y1=510):
    """条带内不透明像素的整体 bbox（原图坐标）；无墨迹返回 None。"""
    region = img.crop((x0, y0, x1, y1))
    bbox = region.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    if bbox is None:
        return None
    return (bbox[0] + x0, bbox[1] + y0, bbox[2] + x0, bbox[3] + y0)


def _cy(bbox):
    return (bbox[1] + bbox[3]) / 2


@pytest.mark.parametrize("value", [3, -3, -12])
def test_stat_signed_block_centered(assets_dir, value):
    """带号 stat（战斗）：符号+数字整体块的视觉中心对齐 num_pos（容差 1px）。

    覆盖 + 与 -：田氏颜体 `-` 字形预测 bbox 虚报底边，按预测口径对齐会错位（审查回归）。
    """
    from bwpdiy.render.badges import _render_ink
    lib = AssetLibrary(assets_dir)
    # num_offset 拉大，使数字带与图标像素分离便于测量；num_pos=(160,485)
    elem = {"kind": "stat", "field": "power+", "icon": "ll", "pos": [100, 485],
            "icon_size": 32, "num_offset": [60, 0], "font_size": 30}
    signed = render_element(canvas(), lib, "power", elem, {"type": "战斗", "power+": value})
    # 整体块：num_pos=(160,485) 附近（图标在 x≤116，不进带）
    block = _band_bbox(signed, 120, 260)
    assert block
    assert abs((block[0] + block[2]) / 2 - 160) <= 1  # 块视觉中心对齐 num_pos.x
    # 符号/数字竖直居中：数字带 = 块右侧 digit_ink 宽（与渲染同源 _render_ink 口径）
    font = lib.font("name", 30)
    dw = _render_ink(str(abs(value)), font)[0].width
    s_digits = _band_bbox(signed, block[2] - dw, block[2])
    s_sign = _band_bbox(signed, block[0], block[2] - dw - 1)
    assert s_digits and s_sign
    assert abs(_cy(s_sign) - _cy(s_digits)) <= 1
    # 符号半宽化：符号明显窄于数字（田氏颜体 +/- 为全宽字形，须水平压缩；用户裁定 0.65）
    assert (s_sign[2] - s_sign[0]) < (s_digits[2] - s_digits[0])


def test_stat_unsigned_block_centered(assets_dir):
    """不带号 stat（式神/形态/幻境等其余类型）：数字视觉中心对齐 num_pos。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "power", "icon": "ll", "pos": [100, 485],
            "icon_size": 32, "num_offset": [60, 0], "font_size": 30}
    img = render_element(canvas(), lib, "power", elem, {"type": "式神", "power": 12})
    block = _band_bbox(img, 120, 260)
    assert block
    assert abs((block[0] + block[2]) / 2 - 160) <= 1


def test_stat_sign_derived_by_type(assets_dir):
    """符号规则按 stat 适用矩阵：战斗/法术觉醒 ±，式神/形态/幻境不带号。

    法术觉醒与战斗共用同一 signed 路径（含负值压缩符号），同值渲染逐像素一致——
    钉死审查遗留的"法术负值走全宽 - 路径"不一致。
    """
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "power+", "icon": "ll", "pos": [100, 485],
            "icon_size": 32, "num_offset": [60, 0], "font_size": 30}

    def digit_band(card):
        img = render_element(canvas(), lib, "power", elem, card)
        return _band_bbox(img, 120, 260)

    spell = digit_band({"type": "法术", "evolve": True, "power+": 3})  # 法术觉醒：+
    combat = digit_band({"type": "战斗", "power+": -3})  # 战斗：+/-
    assert spell and combat
    # 法术觉醒 +3 与战斗 +3 逐像素一致（同一 signed 路径）
    combat_pos = render_element(canvas(), lib, "power", elem, {"type": "战斗", "power+": 3})
    spell_img = render_element(canvas(), lib, "power", elem,
                               {"type": "法术", "evolve": True, "power+": 3})
    assert list(combat_pos.getdata()) == list(spell_img.getdata())
    # 法术觉醒 -3 与战斗 -3 逐像素一致：负值同走 0.65 压缩符号路径
    combat_neg = render_element(canvas(), lib, "power", elem, {"type": "战斗", "power+": -3})
    spell_neg = render_element(canvas(), lib, "power", elem,
                               {"type": "法术", "evolve": True, "power+": -3})
    assert list(combat_neg.getdata()) == list(spell_neg.getdata())


@pytest.mark.parametrize("card", [
    {"type": "法术", "power+": 3},                # 非觉醒法术：无任何角标
    {"type": "法术", "evolve": False, "power+": 3},
    {"type": "协战", "power+": 3},                # 协战：无 stat
    {"type": "式神", "power+": 3},                # 表外 (type, field) 组合
    {"type": "形态", "shield+": 2},               # 表外：形态无护甲加成
    {"power+": 3},                                # 缺 type
])
def test_stat_matrix_off_whitelist_skipped(assets_dir, card):
    """适用矩阵表外组合即使 card 带该字段也不绘制。"""
    lib = AssetLibrary(assets_dir)
    field = "shield+" if "shield+" in card else "power+"
    elem = {"kind": "stat", "field": field, "icon": "ll", "pos": [160, 485],
            "icon_size": 32, "num_offset": [22, 0], "font_size": 30}
    assert opaque(render_element(canvas(), lib, "stat", elem, card)) == 0


@pytest.mark.parametrize("card_type,field", [("战斗", "power+"), ("战斗", "shield+"),
                                             ("法术", "power+"), ("法术", "health+")])
def test_stat_zero_skipped_for_combat_evolve_spell(assets_dir, card_type, field):
    """战斗/法术觉醒的加成 stat 值为 0 时整个角标（图标+数字）不渲染。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": field, "icon": "ll", "pos": [160, 485],
            "icon_size": 32, "num_offset": [22, 0], "font_size": 30}
    card = {field: 0, "type": card_type, "evolve": True}
    assert opaque(render_element(canvas(), lib, "stat", elem, card)) == 0
    card[field] = 1
    assert opaque(render_element(canvas(), lib, "stat", elem, card)) > 0


@pytest.mark.parametrize("card_type,field", [("式神", "power"), ("形态", "health"),
                                             ("幻境", "durability")])
def test_stat_zero_rendered_for_body_types(assets_dir, card_type, field):
    """式神/形态/幻境的 stat 值为 0 也照常渲染。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": field, "icon": "ll", "pos": [160, 485],
            "icon_size": 32, "num_offset": [22, 0], "font_size": 30}
    assert opaque(render_element(canvas(), lib, "stat", elem, {field: 0, "type": card_type})) > 0


def test_stat_rendered_helper():
    """stat_rendered：stat 元素实际渲染判定（渲染与文本避让障碍同口径），按适用矩阵。"""
    from bwpdiy.render.badges import stat_rendered
    shield = {"kind": "stat", "field": "shield+"}
    assert stat_rendered(shield, {"type": "战斗", "shield+": 2})
    assert stat_rendered(shield, {"type": "战斗", "shield+": -1})
    assert not stat_rendered(shield, {"type": "战斗", "shield+": 0})
    assert not stat_rendered(shield, {"type": "战斗"})  # 字段缺失
    durability = {"kind": "stat", "field": "durability"}
    assert stat_rendered(durability, {"type": "幻境", "durability": 0})  # 幻境 0 照渲
    power = {"kind": "stat", "field": "power+"}
    assert stat_rendered(power, {"type": "法术", "evolve": True, "power+": 3})  # 法术觉醒
    assert not stat_rendered(power, {"type": "法术", "evolve": True, "power+": 0})  # 觉醒 0 不绘
    assert not stat_rendered(power, {"type": "法术", "power+": 3})  # 非觉醒法术不绘
    assert not stat_rendered(power, {"type": "协战", "power+": 3})  # 协战无 stat
    assert not stat_rendered(power, {"type": "式神", "power+": 3})  # 表外组合
    body = {"kind": "stat", "field": "power"}
    assert stat_rendered(body, {"type": "式神", "power": 0})  # 式神 0 照渲


def test_level_badge_disabled(assets_dir):
    """level_badge 支持 per-type enabled 开关：enabled=false 整体跳过，缺省/true 照常渲染。"""
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "level_badge", "pos": [120, 65], "base_size": 72, "star_size": 60, "num_size": 40}
    assert opaque(render_element(canvas(), lib, "level", dict(elem, enabled=False),
                                 {"level": 2, "evolve": True})) == 0
    assert opaque(render_element(canvas(), lib, "level", dict(elem, enabled=True),
                                 {"level": 2})) > 0
    # 缺省 enabled 视为 true（兼容旧布局）
    assert opaque(render_element(canvas(), lib, "level", elem, {"level": 2})) > 0


def test_stat_icon_neg(assets_dir):
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "shield+", "icon": "hj", "icon_neg": "pj",
            "pos": [360, 485], "icon_size": 32, "num_offset": [22, 0],
            "font_size": 30}
    # 战斗护甲按当前值自动选贴图：值 < 0 用破甲 pj，否则护甲 hj
    pos_img = render_element(canvas(), lib, "shield", elem, {"type": "战斗", "shield+": 1})
    neg_img = render_element(canvas(), lib, "shield", elem, {"type": "战斗", "shield+": -1})
    assert list(pos_img.getdata()) != list(neg_img.getdata())  # 负值换用破甲贴图
