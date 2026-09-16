from PIL import Image

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
