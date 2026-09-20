from PIL import Image, ImageChops, ImageFilter
import pytest

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
    # 直接测排版层口径（fit 层另有末行居中/锚点上移验收，与宽窄口径无关）：
    # 墨迹口径 36 号排得下；bbox 口径（右缘到 x180+4）排不下
    from bwpdiy.render.geometry import mask_row_runs
    from bwpdiy.render.text import _layout_at_size, parse_items
    chars = parse_items(text)
    assert _layout_at_size(chars, font36, region, region["wrap"],
                           mask_row_runs(ink)) is not None
    assert _layout_at_size(chars, font36, region, region["wrap"],
                           mask_row_runs(bbox)) is None


def test_no_obstacle_mask_keeps_full_width(assets_dir):
    """无角标 / 空掩膜：回退全宽，行中心即区域中心。"""
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 100, 400, 200)
    empty = Image.new("L", (512, 512), 0)
    for mask in (None, empty):
        font, lines = fit_in_region("回退全宽验证", region, lib, obstacle_mask=mask)
        assert len(lines) == 1 and abs(lines[0][1] - 250) < 1e-6


def test_obstacle_gap_field(assets_dir):
    """desc 文本区可选字段 obstacle_gap 覆盖缺省 4：gap 越大行可用区间越窄；
    行默认以区域中心居中，实际宽度触到收窄边界时才最小平移避让。"""
    lib = AssetLibrary(assets_dir)
    mask = ink_mask([(105, 360, 125, 400)])  # 行带内墨迹右缘 x=125
    base = rect_region(100, 360, 400, 400, wrap=False)  # 区域中心 cx=250
    # 短行：不触界，保持区域中心居中，与 gap 无关（旧口径：收窄 span 内居中会偏移）
    for kw in ({}, {"obstacle_gap": 4}, {"obstacle_gap": 10}):
        font, lines = fit_in_region("验证间距", dict(base, **kw), lib, obstacle_mask=mask)
        assert abs(lines[0][1] - 250) < 1e-6
    # 长行：宽度顶到收窄 span 左界时按边界最小平移，gap 越大平移越多
    font36 = lib.font("desc", 36)
    text = ""
    while font36.getlength(text + "测") <= 242:  # 242=触界阈值 2×(250-129)
        text += "测"
    text += "测"
    assert 242 < font36.getlength(text) <= 265, "字体度量变化导致窗口失效，需重选窗口"
    half = font36.getlength(text) / 2
    # 触界平移是排版层（_layout_at_size）口径；fit 层会先尝试锚点上移/缩字号避免触界
    from bwpdiy.render.geometry import mask_row_runs
    from bwpdiy.render.text import _layout_at_size, parse_items
    runs = mask_row_runs(mask)
    chars = parse_items(text)
    lines = _layout_at_size(chars, font36, dict(base), False, runs)
    assert abs(lines[0][1] - (129 + half)) < 1e-6  # 左界 125+4
    lines = _layout_at_size(chars, font36, dict(base, obstacle_gap=10), False, runs)
    assert abs(lines[0][1] - (135 + half)) < 1e-6  # 左界 125+10


def test_gap_between_text_and_obstacle_ink(assets_dir):
    """gap 语义：竖直贴邻（≤1px）的行之间，描述墨迹与角标墨迹横向相距 ≥ obstacle_gap（缺省 4）。"""
    from bwpdiy.render.geometry import mask_row_runs
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 300, 400, 380)
    mask = ink_mask([(100, 320, 200, 380)])
    text = "描述文本避让验证需要足够长度填满收窄后的行宽。" * 2
    img = draw_region(canvas(), lib, text, region, obstacle_mask=mask)
    text_ink = img.getchannel("A").point(lambda v: 255 if v > 10 else 0)
    text_runs = mask_row_runs(text_ink)
    obstacle_runs = mask_row_runs(mask)
    gap = 4
    for y, truns in text_runs.items():
        for dy in (-1, 0, 1):  # 竖直避让 1px：只看竖直贴邻行
            for sx0, sx1 in obstacle_runs.get(y + dy, ()):
                for tx0, tx1 in truns:
                    assert tx1 + gap <= sx0 or sx1 + gap <= tx0


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


def test_center_offset_shifts_anchor(assets_dir):
    """desc 文本区 center_offset：平移居中锚点（水平逐行居中与竖直整体居中的基准），
    区域边界/行宽不变——缺省 [0,0] 与无键行为一致。"""
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 100, 400, 200)  # 中心 (250, 150)
    font, lines = fit_in_region("短句", region, lib)
    assert abs(lines[0][1] - 250) < 1e-6 and abs(lines[0][2] - 150) < 1e-6
    # 锚点右移 20、下移 10：单行中心随之平移
    shifted = fit_in_region("短句", dict(region, center_offset=[20, 10]), lib)
    assert abs(shifted[1][0][1] - 270) < 1e-6 and abs(shifted[1][0][2] - 160) < 1e-6
    # 显式 [0,0] == 缺省
    zero = fit_in_region("短句", dict(region, center_offset=[0, 0]), lib)
    assert abs(zero[1][0][1] - 250) < 1e-6 and abs(zero[1][0][2] - 150) < 1e-6
    # 锚点偏移不改变区域边界：下移 60 时单行底边出底界（y_bottom=200）→ 排版失败 None
    assert fit_in_region("短句", dict(region, center_offset=[0, 60]), lib) is None


def test_fit_lifts_anchor_to_recenter_last_line(assets_dir):
    """末行被右下角障碍挤偏时：fit 先逐 px 上移居中锚点（≤半行高）救回末行居中，
    不行才缩字号。"""
    from bwpdiy.render.geometry import mask_row_runs
    from bwpdiy.render.text import _layout_at_size, parse_items
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 300, 400, 420)  # 中心 (250,360)
    mask = ink_mask([(300, 390, 400, 420)])  # 右下角墨迹块
    text = "第一行文本内容\n第二行居中验证"
    font, lines = fit_in_region(text, region, lib, obstacle_mask=mask)
    assert lines is not None and len(lines) == 2
    assert abs(lines[-1][1] - 250) < 1e-6  # 末行回中
    # 同字号锚点不上移时末行被挤偏（证明确为上移救回，而非字号缩小顺带解决）
    raw = _layout_at_size(parse_items(text), font, region, region["wrap"], mask_row_runs(mask))
    assert raw is None or abs(raw[-1][1] - 250) > 1e-6


def test_fit_recenters_any_line_not_just_last(assets_dir):
    """接受条件=每一行都水平居中（v1.2.2 起，原仅末行）：障碍只挤偏中间行时
    同样触发上移/降字号，最终所有行回中。"""
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 280, 400, 440)  # 中心 (250,360)
    mask = ink_mask([(340, 342, 400, 378)])   # 右侧中间墨迹块：只覆盖中间行的 y 带
    text = "第一行文本内容\n第二行居中验证内容\n第三行文本内容"
    font, lines = fit_in_region(text, region, lib, obstacle_mask=mask)
    assert lines is not None and len(lines) == 3
    assert all(abs(cx - 250) < 1e-6 for _, cx, _ in lines)


def test_vertical_center_with_obstacles(assets_dir):
    """有角标墨迹时：末行须保持水平居中（锚点按需自动上移），块整体不出区域。"""
    lib = AssetLibrary(assets_dir)
    text = "这是一段用于验证竖直居中的长描述文本，需要排很多行才能放下。" * 3
    region = rect_region(100, 100, 400, 400)
    mask = ink_mask([(100, 350, 160, 400), (340, 350, 400, 400)])
    font, lines = fit_in_region(text, region, lib, obstacle_mask=mask)
    assert len(lines) > 1
    assert abs(lines[-1][1] - 250) < 1e-6  # 末行水平居中（锚点已按需上移）
    assert lines[0][2] >= 100 and lines[-1][2] <= 400  # 块不出区域


# ---------- 内嵌图标（#xx） ----------

def test_parse_items_icon_codes():
    from bwpdiy.render.text import parse_items
    # 纯文本：全 char 项
    assert parse_items("甲乙") == [("char", "甲", False), ("char", "乙", False)]
    # #ll → icon 项，记号本身不进入字符流
    assert parse_items("获得#ll点力量") == [
        ("char", "获", False), ("char", "得", False), ("icon", "ll", False),
        ("char", "点", False), ("char", "力", False), ("char", "量", False)]
    # 代码不区分大小写
    assert parse_items("#LL") == [("icon", "ll", False)]
    # 关键字段内的图标继承 kw 标记
    assert parse_items("[[#ll]]") == [("icon", "ll", True)]
    # '#' 后非两个英文字母：字面字符
    assert parse_items("#1")[0] == ("char", "#", False)
    # 未知代码报错
    with pytest.raises(ValueError, match="图标代码未知"):
        parse_items("#xx")


def test_draw_region_inline_icon(assets_dir):
    """行内图标参与排版并绘制：同字号下墨迹多于纯文本；fit 行文本不含图标项。"""
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 100, 400, 200)
    ink = lambda img: sum(1 for p in img.getdata() if p[3] > 0)
    plain = draw_region(canvas(), lib, "测试图标", region)
    with_icon = draw_region(canvas(), lib, "测试#ll图标", region)
    assert ink(with_icon) > ink(plain)
    font, lines = fit_in_region("测试#ll图标", region, lib)
    assert lines[0][0] == "测试图标"  # 行纯文本不含图标记号


def test_icon_black_variant_for_faction(assets_dir):
    """墨染框（icon_variant='black'）派系图标用 _black 变体；无变体的图标回退原图。"""
    from bwpdiy.render.text import _icon_image
    lib = AssetLibrary(assets_dir)
    assert _icon_image("hl", lib, "black").tobytes() != _icon_image("hl", lib, None).tobytes()
    assert _icon_image("ll", lib, "black").tobytes() == _icon_image("ll", lib, None).tobytes()


def test_icon_counts_toward_line_width(assets_dir):
    """图标宽度计入行宽（换行与逐行居中共用 _line_width）：
    nowrap 区域恰好排得下纯文本时，末尾追加图标即排版失败。"""
    from bwpdiy.render.text import _icon_widths, _layout_at_size, _line_width, parse_items
    lib = AssetLibrary(assets_dir)
    font36 = lib.font("desc", 36)
    items = parse_items("甲乙#ll")
    iw = _icon_widths(items, font36, lib, None)
    # 行宽 = 字符宽度 + 图标缩放宽度（居中/换行均按此口径）
    assert _line_width(items, font36, iw) == font36.getlength("甲乙") + iw["ll"]
    text = "甲乙丙丁"
    w = font36.getlength(text)
    region = rect_region(0, 0, round(w) + 2, 100, wrap=False)  # 恰好排下纯文本
    assert _layout_at_size(parse_items(text), font36, region, False, lib=lib) is not None
    assert _layout_at_size(parse_items(text + "#ll"), font36, region, False, lib=lib) is None


def test_icon_scale_field(assets_dir):
    """desc 区 icon_scale（缺省 1.0）：图标高=字号×系数，排版宽度随系数缩小。"""
    from bwpdiy.render.text import _icon_size, _layout_at_size, parse_items
    lib = AssetLibrary(assets_dir)
    w1, h1 = _icon_size("ll", 36, lib, None)
    w2, h2 = _icon_size("ll", 36, lib, None, 0.5)
    assert (h1, h2) == (36, 18) and w2 < w1
    font36 = lib.font("desc", 36)
    items = parse_items("甲乙丙丁#ll")
    region = rect_region(0, 0, round(font36.getlength("甲乙丙丁") + w2) + 1, 100, wrap=False)
    # 宽度介于「半系数」与「全系数」之间：0.5 排得下，缺省 1.0 超宽失败
    assert _layout_at_size(items, font36, dict(region, icon_scale=0.5), False, lib=lib) is not None
    assert _layout_at_size(items, font36, region, False, lib=lib) is None
