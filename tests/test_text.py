from PIL import Image, ImageChops, ImageFilter

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.text import TEXT_FILL, draw_region, fit_in_region


def canvas():
    return Image.new("RGBA", (512, 512), (0, 0, 0, 0))


def ink_mask(rects, size=(512, 512)):
    """L 掩膜：rects 为 (x0, y0, x1, y1) 半开区间实心墨迹。"""
    mask = Image.new("L", size, 0)
    for r in rects:
        mask.paste(255, r)
    return mask


def rect_region(x0, y0, x1, y1, **kw):
    region = {"center": [(x0 + x1) / 2, (y0 + y1) / 2],
              "width": x1 - x0, "height": y1 - y0,
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


def test_draw_region_renders_pixels(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = draw_region(canvas(), lib, "渲染测试", rect_region(100, 100, 400, 200))
    assert sum(1 for p in img.getdata() if p[3] > 0) > 50


def test_obstacles_sealing_line_returns_none(assets_dir):
    # 双侧墨迹把中间行 y 带完全封死（收窄后宽度 ≤0）：fit 返回 None，draw 强排兜底不抛异常
    lib = AssetLibrary(assets_dir)
    text = "障碍封死回归测试文本内容需要足够长才能排到被封死的行。" * 4
    region = rect_region(100, 100, 400, 400)
    mask = ink_mask([(100, 150, 260, 350), (260, 150, 400, 350)])
    assert fit_in_region(text, region, lib, obstacle_mask=mask) is None
    img = draw_region(canvas(), lib, text, region, obstacle_mask=mask)
    assert img is not None


def test_explicit_newline_forces_break(assets_dir):
    """显式 \n 强制断行：每段内再自动换行、逐行居中。"""
    lib = AssetLibrary(assets_dir)
    font, lines = fit_in_region("第一行\n第二行", rect_region(100, 100, 400, 200), lib)
    assert [l[0] for l in lines] == ["第一行", "第二行"]
    assert lines[0][2] < lines[1][2]  # 第二行在下方


def test_consecutive_newlines_merged(assets_dir):
    """连续 \n 合并为一个换行（不产生空行）。"""
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 100, 400, 200)
    font, lines = fit_in_region("甲\n\n\n乙", region, lib)
    assert [l[0] for l in lines] == ["甲", "乙"]
    img = draw_region(canvas(), lib, "甲\n\n乙", region)
    assert sum(1 for p in img.getdata() if p[3] > 0) > 50


def test_obstacles_narrow_bottom_lines(assets_dir):
    # 底部左右有数值标墨迹：长描述末尾几行可用宽度应变窄（行数增多或末行更短）
    lib = AssetLibrary(assets_dir)
    text = "这是一段用于验证障碍避让的长描述文本，需要排很多行才能放下。" * 4
    region = rect_region(100, 100, 400, 400)
    mask = ink_mask([(100, 350, 160, 400), (340, 350, 400, 400)])
    font, lines = fit_in_region(text, region, lib, obstacle_mask=mask)
    assert lines is not None
    bottom = [l for l in lines if l[2] > 350]
    top = [l for l in lines if l[2] < 300]
    assert bottom and top
    assert max(font.getlength(l[0]) for l in bottom) < max(font.getlength(l[0]) for l in top)


# ---------- 墨迹避让：掩膜口径取代矩形 bbox ----------

def test_ink_mask_avoidance_wider_than_bbox(assets_dir):
    """贴图带透明边场景：真实墨迹避让比 bbox 避让显著更宽（同行可用更大字号）。"""
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 360, 400, 400, wrap=False)
    font36 = lib.font("desc", 36)
    # bbox 口径（含透明边，墨迹占 x105..125 但组件矩形到 x180）把可用宽压到 216，
    # 墨迹口径只压到 271；造一段宽度落在两者之间的文本
    text = ""
    while font36.getlength(text + "测") <= 216:
        text += "测"
    text += "测"
    assert 216 < font36.getlength(text) <= 271, "字体度量变化导致窗口失效，需重选窗口"
    ink = ink_mask([(105, 360, 125, 400)])
    bbox = ink_mask([(100, 360, 180, 400)])
    fitted_ink = fit_in_region(text, region, lib, obstacle_mask=ink)
    fitted_bbox = fit_in_region(text, region, lib, obstacle_mask=bbox)
    assert fitted_ink[0].size == 36  # 墨迹口径：最大字号即可放下
    assert fitted_bbox[0].size < fitted_ink[0].size  # bbox 口径：必须缩字号


def test_no_obstacle_mask_keeps_full_width(assets_dir):
    """无角标 / 空掩膜：回退全宽，行中心即区域中心。"""
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 100, 400, 200)
    empty = Image.new("L", (512, 512), 0)
    for mask in (None, empty):
        font, lines = fit_in_region("回退全宽验证", region, lib, obstacle_mask=mask)
        assert len(lines) == 1 and abs(lines[0][1] - 250) < 1e-6


def test_obstacle_gap_field(assets_dir):
    """desc 文本区可选字段 obstacle_gap 覆盖缺省 4：gap 越大行可用区间越窄。"""
    lib = AssetLibrary(assets_dir)
    mask = ink_mask([(105, 360, 125, 400)])  # 行带内墨迹右缘 x=125
    text = "验证间距字段"  # 收窄后仍放得下的短句
    base = rect_region(100, 360, 400, 400, wrap=False)
    # 缺省 = 显式 4：左界 125+4 → 行中心 (129+400)/2
    font, lines = fit_in_region(text, dict(base), lib, obstacle_mask=mask)
    assert abs(lines[0][1] - 264.5) < 1e-6
    font, lines = fit_in_region(text, dict(base, obstacle_gap=4), lib, obstacle_mask=mask)
    assert abs(lines[0][1] - 264.5) < 1e-6
    # gap=10：左界 125+10 → 行中心 (135+400)/2
    font, lines = fit_in_region(text, dict(base, obstacle_gap=10), lib, obstacle_mask=mask)
    assert abs(lines[0][1] - 267.5) < 1e-6


def test_gap_between_text_and_obstacle_ink(assets_dir):
    """gap 语义：描述墨迹与角标墨迹的最近距离 ≥ obstacle_gap（缺省 4）。"""
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 300, 400, 380)
    mask = ink_mask([(100, 320, 200, 380)])
    text = "描述文本避让验证需要足够长度填满收窄后的行宽。" * 2
    img = draw_region(canvas(), lib, text, region, obstacle_mask=mask)
    text_ink = img.getchannel("A").point(lambda v: 255 if v > 10 else 0)
    # 掩膜墨迹外扩 gap-1 px 后仍与描述墨迹零重叠 ⇔ 两者距离 ≥ gap
    dilated = mask.filter(ImageFilter.MaxFilter(2 * 4 - 1))
    assert ImageChops.darker(text_ink, dilated).getbbox() is None


# ---------- 竖直居中 ----------

def test_vertical_center_single_line(assets_dir):
    lib = AssetLibrary(assets_dir)
    font, lines = fit_in_region("短句", rect_region(100, 100, 400, 200), lib)
    assert len(lines) == 1 and abs(lines[0][2] - 150) < 1e-6


def test_vertical_center_multiline(assets_dir):
    lib = AssetLibrary(assets_dir)
    text = "这是一段非常非常长的描述文本需要换行并且缩小字号才能排下" * 3
    font, lines = fit_in_region(text, rect_region(100, 100, 300, 300), lib)
    assert len(lines) > 1
    assert abs((lines[0][2] + lines[-1][2]) / 2 - 200) <= 1


def test_vertical_center_with_obstacles(assets_dir):
    """有角标墨迹时文本块仍竖直居中（收窄只影响行宽与行数）。"""
    lib = AssetLibrary(assets_dir)
    text = "这是一段用于验证竖直居中的长描述文本，需要排很多行才能放下。" * 3
    region = rect_region(100, 100, 400, 400)
    mask = ink_mask([(100, 350, 160, 400), (340, 350, 400, 400)])
    font, lines = fit_in_region(text, region, lib, obstacle_mask=mask)
    assert len(lines) > 1
    assert abs((lines[0][2] + lines[-1][2]) / 2 - 250) <= 1
