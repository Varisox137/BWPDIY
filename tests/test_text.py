from PIL import Image

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.text import TEXT_FILL, draw_region, fit_in_region


def canvas():
    return Image.new("RGBA", (512, 512), (0, 0, 0, 0))


def rect_region(x0, y0, x1, y1, **kw):
    region = {"polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
              "font_range": [36, 12], "wrap": True, "font": "desc"}
    region.update(kw)
    return region


def test_fit_rect_single_line(assets_dir):
    lib = AssetLibrary(assets_dir)
    font, lines = fit_in_region("短句", rect_region(100, 100, 400, 200), lib)
    assert len(lines) == 1
    text, cx, cy = lines[0]
    assert text == "短句" and abs(cx - 250) < 1e-6


def test_fit_wraps_and_shrinks(assets_dir):
    lib = AssetLibrary(assets_dir)
    long = "这是一段非常非常长的描述文本需要换行并且缩小字号才能排下" * 3
    font, lines = fit_in_region(long, rect_region(100, 100, 300, 300), lib)
    assert len(lines) > 1 and font.size < 36


def test_fit_nowrap_single_line(assets_dir):
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 100, 400, 160, wrap=False, font="name")
    font, lines = fit_in_region("卡牌名", region, lib)
    assert len(lines) == 1


def test_fit_triangle_centers_per_line(assets_dir):
    lib = AssetLibrary(assets_dir)
    region = {"polygon": [[100, 300], [400, 300], [250, 100]],
              "font_range": [24, 12], "wrap": True, "font": "desc"}
    font, lines = fit_in_region("三角区域排版测试文本内容", region, lib)
    assert len(lines) >= 1
    for _, cx, _ in lines:
        assert abs(cx - 250) < 1e-6  # 对称三角，每行中心都在 x=250


def test_draw_region_renders_pixels(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = draw_region(canvas(), lib, "渲染测试", rect_region(100, 100, 400, 200))
    assert sum(1 for p in img.getdata() if p[3] > 0) > 50


def test_obstacles_narrow_bottom_lines(assets_dir):
    # 底部左右有数值标障碍：长描述末尾几行可用宽度应变窄（行数增多或末行更短）
    lib = AssetLibrary(assets_dir)
    text = "这是一段用于验证障碍避让的长描述文本，需要排很多行才能放下。" * 4
    region = rect_region(100, 100, 400, 400)
    obstacles = [(100.0, 350.0, 160.0, 400.0), (340.0, 350.0, 400.0, 400.0)]
    font, lines = fit_in_region(text, region, lib, obstacles=obstacles)
    assert lines is not None
    bottom = [l for l in lines if l[2] > 350]
    top = [l for l in lines if l[2] < 300]
    assert bottom and top
    assert max(font.getlength(l[0]) for l in bottom) < max(font.getlength(l[0]) for l in top)
