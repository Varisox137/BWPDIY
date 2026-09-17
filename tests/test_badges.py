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


def test_rarity_flank_symmetric(assets_dir):
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "rarity_flank", "pos": [256, 358], "gap": 16, "size": 24}
    # 卡名越宽，两标越外移：比较短名/长名 ctx 下右标位置的像素差异
    narrow = render_element(canvas(), lib, "rarity", elem, {"rarity": "SSR"}, {"name_width": 40})
    wide = render_element(canvas(), lib, "rarity", elem, {"rarity": "SSR"}, {"name_width": 160})
    assert opaque(narrow) > 0 and opaque(wide) > 0
    # 右标中心 x = 256 + name_width/2 + 16 + 12：宽名时右标右侧应有像素而窄名时没有
    assert wide.getpixel((256 + 80 + 16 + 24, 358))[3] > 0
    assert narrow.getpixel((256 + 80 + 16 + 24, 358))[3] == 0
    # 无 rarity 字段：按默认 R 渲染
    default_r = render_element(canvas(), lib, "rarity", elem, {}, {"name_width": 40})
    assert opaque(default_r) > 0


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
            "icon_size": 32, "num_offset": [22, 0], "font_size": 30, "signed": True}
    img = render_element(canvas(), lib, "power", elem, {"power+": 1})
    assert opaque(img) > 100  # 图标+数字两处像素
    # 缺字段跳过
    assert opaque(render_element(canvas(), lib, "power", elem, {})) == 0


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
def test_stat_signed_vertical_alignment(assets_dir, value):
    """signed stat：正负号与数字竖直居中对齐；带号与不带号数字位置一致（容差 1px）。

    覆盖 + 与 -：田氏颜体 `-` 字形预测 bbox 虚报底边，按预测口径对齐会错位（审查回归）。
    """
    lib = AssetLibrary(assets_dir)
    # num_offset 拉大，使数字带与图标像素分离便于测量
    base = {"kind": "stat", "field": "power+", "icon": "ll", "pos": [100, 485],
            "icon_size": 32, "num_offset": [60, 0], "font_size": 30}
    signed = render_element(canvas(), lib, "power", dict(base, signed=True), {"power+": value})
    unsigned = render_element(canvas(), lib, "power", dict(base, signed=False), {"power+": abs(value)})
    # 数字带：num_pos=(160,485) 附近（图标在 x≤116，不进带）
    u_digits = _band_bbox(unsigned, 120, 220)
    assert u_digits
    # signed 图中：数字墨迹 = 不带号数字 x 范围内的墨迹；符号墨迹 = 其左侧
    s_digits = _band_bbox(signed, u_digits[0], u_digits[2])
    s_sign = _band_bbox(signed, 120, u_digits[0])
    assert s_digits and s_sign
    # 数字部分位置逐像素一致（含多位数 12）
    assert s_digits == u_digits
    # 符号中心与数字中心竖直对齐（容差 1px）
    assert abs(_cy(s_sign) - _cy(s_digits)) <= 1


def test_stat_icon_neg(assets_dir):
    from bwpdiy.render.badges import stat_obstacle
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "shield+", "icon": "hj", "icon_neg": "pj",
            "pos": [360, 485], "icon_size": 32, "num_offset": [22, 0],
            "font_size": 30, "signed": True}
    pos_img = render_element(canvas(), lib, "shield", elem, {"shield+": 1})
    neg_img = render_element(canvas(), lib, "shield", elem, {"shield+": -1})
    assert list(pos_img.getdata()) != list(neg_img.getdata())  # 负值换用破甲贴图
    # stat_obstacle 矩形公式
    x0, y0, x1, y1 = stat_obstacle(elem)
    assert x0 == 360 - 16 and y0 == 485 - 16
    assert x1 > 360 + 16 and y1 == 485 + 16
