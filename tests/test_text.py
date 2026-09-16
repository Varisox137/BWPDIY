from PIL import Image, ImageFont

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.text import draw_description, draw_name, layout_lines


def canvas():
    return Image.new("RGBA", (512, 512), (0, 0, 0, 0))


def test_layout_lines_wraps(assets_dir):
    lib = AssetLibrary(assets_dir)
    font = lib.font("desc", 22)
    lines = layout_lines("这是一段很长很长的描述文本用来测试自动换行功能是否正常", font, 120)
    assert len(lines) >= 3
    for line in lines:
        assert font.getlength(line) <= 120 + 1


def test_layout_lines_explicit_newline(assets_dir):
    lib = AssetLibrary(assets_dir)
    font = lib.font("desc", 22)
    assert layout_lines("甲\n乙", font, 9999) == ["甲", "乙"]


def test_draw_name_fits_and_renders(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = draw_name(canvas(), lib, "测试卡名")
    assert sum(1 for p in img.getdata() if p[3] > 0) > 50


def test_draw_name_shrinks_long_name(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = draw_name(canvas(), lib, "这是一个非常非常非常长的卡名")
    assert sum(1 for p in img.getdata() if p[3] > 0) > 50  # 不抛异常、有像素


def test_draw_description_autofit(assets_dir):
    lib = AssetLibrary(assets_dir)
    long_text = "造成3点伤害。" * 30
    img = draw_description(canvas(), lib, long_text)
    assert sum(1 for p in img.getdata() if p[3] > 0) > 100
