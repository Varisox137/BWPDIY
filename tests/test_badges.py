from PIL import Image

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.badges import (add_faction, add_level_badge, add_rarity,
                                  add_stats)


def canvas():
    return Image.new("RGBA", (512, 512), (0, 0, 0, 0))


def alpha_at(img, x, y):
    return img.getpixel((x, y))[3]


def test_level_badge_three_layers(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = add_level_badge(canvas(), lib, level=2, evolve=True)
    assert alpha_at(img, 120, 65) > 0  # 等级标中心已有内容


def test_level_badge_without_evolve(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = add_level_badge(canvas(), lib, level=1, evolve=False)
    assert alpha_at(img, 120, 65) > 0


def test_rarity_and_faction(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = add_rarity(canvas(), lib, "SSR")
    img = add_faction(img, lib, "red")
    a = [p[3] for p in img.getdata()]
    assert sum(1 for v in a if v > 0) > 100  # 两处图标均落上像素


def test_stats_signed_and_plain(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = add_stats(canvas(), lib, [("power", 3), ("health", 4)])
    assert sum(1 for p in img.getdata() if p[3] > 0) > 0
    img2 = add_stats(canvas(), lib, [("power+", 1), ("shield+", -1)])
    assert sum(1 for p in img2.getdata() if p[3] > 0) > 0
