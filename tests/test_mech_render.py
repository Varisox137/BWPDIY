"""机制描述框渲染测试：帧拼接（行数单调/接缝色差/自定义行距）、关键字高亮与内嵌图标、
关键字名左上角左对齐（字号略大于正文）、badge 角标、行数软上限、布局参数与 badge 交叉规则。"""

from pathlib import Path

import pytest
from PIL import ImageDraw

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.mech import (
    LINE_PITCH,
    MARGIN_X,
    MAX_LINES,
    NAME_FILL,
    _BAND_Y,
    build_frame,
    render_mechanism,
)


@pytest.fixture()
def lib(assets_dir) -> AssetLibrary:
    return AssetLibrary(assets_dir)


def _mech(**kw) -> dict:
    base = {"name": "测试机制", "frame": "skill", "text": "一行描述。"}
    base.update(kw)
    return base


def _max_row_diff(img, y1, y2) -> int:
    """两行之间逐像素逐通道最大色差。"""
    px = img.load()
    return max(max(abs(a - b) for a, b in zip(px[x, y1], px[x, y2]))
               for x in range(img.width))


# ---------- 帧拼接 ----------

@pytest.mark.parametrize("frame", ["invocation", "skill"])
def test_frame_height_by_line_count(lib, frame):
    """3/4/5 行用整图；行数越大框越高且严格单调。"""
    heights = {n: build_frame(lib, frame, n).height for n in (3, 4, 5, 6, 8)}
    assert heights[3] < heights[4] < heights[5] < heights[6] < heights[8]
    assert heights[6] - heights[5] == LINE_PITCH
    assert heights[8] - heights[5] == 3 * LINE_PITCH


def test_frame_below_3_shrinks_to_2(lib):
    """不足 3 行从 5 行素材裁除到 2 行（空描述 = 关键字名+空行仅 2 行）；1/0 行按 2 行。"""
    for frame in ("invocation", "skill"):
        h3 = build_frame(lib, frame, 3).height
        h2 = build_frame(lib, frame, 2).height
        assert h2 == h3 - LINE_PITCH
        assert build_frame(lib, frame, 1).height == h2
        assert build_frame(lib, frame, 0).height == h2
        # 与 3 行素材中部裁除一行等价：顶帽/底帽逐像素一致
        src3 = lib.mech(f"frame_{frame}_3")
        band_y = _BAND_Y[frame]
        built = build_frame(lib, frame, 2)
        assert list(built.crop((0, 0, built.width, band_y)).getdata()) == \
            list(src3.crop((0, 0, src3.width, band_y)).getdata())
        assert list(built.crop((0, band_y, built.width, built.height)).getdata()) == \
            list(src3.crop((0, band_y + LINE_PITCH, src3.width, src3.height)).getdata())


def test_seal_frame_extension(lib):
    """seal 底框容 2 行内容（关键字名+空行即占满），超出按行高平铺扩展。"""
    h2 = build_frame(lib, "seal", 2).height
    assert build_frame(lib, "seal", 1).height == h2
    assert build_frame(lib, "seal", 3).height == h2 + LINE_PITCH
    assert build_frame(lib, "seal", 6).height == h2 + 4 * LINE_PITCH


@pytest.mark.parametrize("frame", ["invocation", "skill", "seal"])
def test_frame_tiling_seam(lib, frame):
    """拼接缝无错位：顶帽/底帽与整图逐像素一致，带间/带底接缝色差在素材噪点范围内。"""
    n = {"invocation": 6, "skill": 6, "seal": 4}[frame]
    built = build_frame(lib, frame, n)
    band_y = _BAND_Y[frame]
    src = (lib.mech(f"frame_{frame}_5") if frame != "seal"
           else lib.mech("frame_seal"))
    # 顶帽与底帽逐像素来自原图
    top = built.crop((0, 0, built.width, band_y))
    assert list(top.getdata()) == list(src.crop((0, 0, src.width, band_y)).getdata())
    tail_h = src.height - band_y
    bottom = built.crop((0, built.height - tail_h, built.width, built.height))
    assert list(bottom.getdata()) == list(
        src.crop((0, band_y, src.width, src.height)).getdata())
    # 平铺带与原图横带逐像素一致；接缝（带末行 → 底帽首行）色差 ≤16（素材自带噪点）
    band = built.crop((0, band_y, built.width, band_y + LINE_PITCH))
    assert list(band.getdata()) == list(
        src.crop((0, band_y, src.width, band_y + LINE_PITCH)).getdata())
    seam_y = built.height - tail_h
    assert _max_row_diff(built, seam_y - 1, seam_y) <= 16


# ---------- 文本渲染 ----------

def test_keyword_highlight(assets_dir):
    """[[关键字]] 段金色高亮：渲染图出现金色像素，且与非高亮版不同。"""
    plain = render_mechanism(_mech(text="获得迅捷。"), assets_dir)
    kw = render_mechanism(_mech(text="获得[[迅捷]]。"), assets_dir)
    assert list(plain.getdata()) != list(kw.getdata())
    assert any(p[:3] == NAME_FILL[:3] and p[3] > 200 for p in kw.getdata())


def test_inline_icon(assets_dir):
    """#ll 行内力量图标：图标像素（ teal 力量色）出现在描述区，无图标版无此色。"""
    with_icon = render_mechanism(_mech(text="获得 #ll 1 点力量。"), assets_dir)
    without = render_mechanism(_mech(text="获得 1 点力量。"), assets_dir)
    power_teal = (92, 130, 132)

    def has_teal(img):
        return any(abs(p[0] - power_teal[0]) <= 2 and abs(p[1] - power_teal[1]) <= 2
                   and abs(p[2] - power_teal[2]) <= 2 and p[3] > 200
                   for p in img.getdata())

    assert has_teal(with_icon)
    assert not has_teal(without)


def test_unknown_icon_code_raises(assets_dir):
    with pytest.raises(ValueError, match="图标代码未知"):
        render_mechanism(_mech(text="非法 #zz 图标。"), assets_dir)


def test_name_top_left(assets_dir):
    """关键字名在框内左上角左对齐（x≈name_x 默认 12）、金色；与描述之间空一行。
    不再加粗描边，墨迹左缘 = text_x + 字体左轴承（约 3px）。"""
    img = render_mechanism(_mech(), assets_dir)
    gold_xs = [x for x in range(img.width) for y in range(img.height // 3)
               if (lambda p: p[:3] == NAME_FILL[:3] and p[3] > 200)(img.getpixel((x, y)))]
    assert gold_xs and min(gold_xs) <= MARGIN_X + 4  # 左对齐：金色墨迹贴近左边距


# ---------- 布局参数（layout 段，对应 assets/layout.json「机制」） ----------

def test_layout_none_and_unknown_keys_equal_default(assets_dir):
    """layout=None / 未知键 / 畸形值（含嵌套键）均回退默认，渲染逐像素一致。"""
    a = render_mechanism(_mech(), assets_dir)
    b = render_mechanism(_mech(), assets_dir, layout=None)
    c = render_mechanism(_mech(), assets_dir,
                         layout={"unknown_key": 1, "text_size": None, "badge_pos": "x",
                                 "name_offset": [1], "frames": "bad",
                                 "text_x": 60})  # text_x/text_y/margin_x/frame_offset
    # 等顶层旧键为开发期废弃键，已被忽略（frames 内的同名键才是当前 schema）
    assert list(a.getdata()) == list(b.getdata()) == list(c.getdata())


def test_layout_text_size_changes_pitch(assets_dir):
    """正文字号 = 行距：字号增大框增高、减小框变矮（行数不变）。"""
    text = "第一行描述文字。\n第二行描述文字。"
    base = render_mechanism(_mech(text=text), assets_dir)
    big = render_mechanism(_mech(text=text), assets_dir, layout={"text_size": 30})
    small = render_mechanism(_mech(text=text), assets_dir, layout={"text_size": 18})
    assert big.height > base.height > small.height


def _gold_min_x(img):
    """关键字名金色墨迹左缘（框上部 1/3 区域内）。"""
    xs = [x for x in range(img.width) for y in range(img.height // 3)
          if (lambda p: p[:3] == NAME_FILL[:3] and p[3] > 200)(img.getpixel((x, y)))]
    return min(xs)


def test_layout_text_x(assets_dir):
    """文本偏移 x（分框独立）：关键字名金色墨迹左缘随本框 text_x 右移。"""
    assert _gold_min_x(render_mechanism(_mech(), assets_dir)) <= 22
    assert _gold_min_x(render_mechanism(
        _mech(), assets_dir, layout={"frames": {"skill": {"text_x": 60}}})) >= 60


def test_layout_frames_region(assets_dir):
    """文本区域完全分框独立：本框 text_x 生效，其他框逐像素不变。"""
    base = _gold_min_x(render_mechanism(_mech(), assets_dir))
    moved = _gold_min_x(render_mechanism(
        _mech(), assets_dir, layout={"frames": {"skill": {"text_x": 28}}}))
    assert moved - base == 28 - MARGIN_X
    # 其他框不受 skill 区域影响（invocation 与默认逐像素一致）
    a = render_mechanism(_mech(frame="invocation"), assets_dir)
    b = render_mechanism(_mech(frame="invocation"), assets_dir,
                         layout={"frames": {"skill": {"text_x": 28}}})
    assert list(a.getdata()) == list(b.getdata())


def test_layout_region_width_wraps(assets_dir):
    """区域宽 width 决定换行：收窄产生更多行、框更高。"""
    text = "一段长度适中的机制描述文字，用于验证换行宽度。"
    wide = render_mechanism(_mech(text=text), assets_dir)
    narrow = render_mechanism(_mech(text=text), assets_dir,
                              layout={"frames": {"skill": {"width": 100}}})
    assert narrow.height > wide.height


@pytest.mark.parametrize("frame", ["invocation", "skill", "seal"])
def test_default_region_fits_twelve_hanzi(assets_dir, frame):
    from bwpdiy.render.layout import load_layouts

    info12, info13 = {}, {}
    img12 = render_mechanism(_mech(frame=frame, text="一" * 12), assets_dir, info=info12)
    img13 = render_mechanism(_mech(frame=frame, text="一" * 13), assets_dir, info=info13)

    assert info12["text_width"] == 288
    assert info12["text_x"] == 12
    assert img12.width == 312  # 内置回退：左右各 12px，288px 文本区不溢出
    assert info12["text_height"] == 3 * 24
    assert info13["text_height"] == 4 * 24
    assert img13.height > img12.height
    shipped = render_mechanism(_mech(frame=frame, text="一" * 12), assets_dir,
                               layout=load_layouts(assets_dir)["机制"])
    assert shipped.width == 312 and shipped.height == img12.height  # 出厂布局：左右各 12px


def test_render_info_text_block(assets_dir):
    """info 回填实际文本块矩形（裁剪后坐标系）：左缘=text_x、高=行数×行距、
    竖直居中于框中心+text_dy；裁剪零偏移时与框坐标一致。"""
    info: dict = {}
    img = render_mechanism(_mech(text="两行中的第一行。\n第二行。"), assets_dir,
                           info=info)
    # 2 描述行 + 关键字名 + 空行 = 4 行 × 24
    assert info["text_width"] == 288 and info["text_height"] == 4 * 24
    assert info["text_x"] == 12
    assert info["text_top"] == pytest.approx((img.height - 4 * 24) / 2)
    # 分框 text_dy 生效
    info2: dict = {}
    render_mechanism(_mech(text="两行中的第一行。\n第二行。"), assets_dir,
                     layout={"frames": {"skill": {"text_dy": 7}}}, info=info2)
    assert info2["text_top"] == pytest.approx(info["text_top"] + 7)


def test_desc_left_aligned(assets_dir):
    """描述逐行左对齐：不同长度的描述行墨迹左缘一致（ invocation 深字）。"""
    from bwpdiy.render.mech import TEXT_FILL
    img = render_mechanism(
        _mech(frame="invocation", text="较长的描述文字。\n短。"), assets_dir)
    fill = TEXT_FILL["invocation"]
    rows: dict[int, int] = {}  # y -> 该行文字墨迹最小 x
    for y in range(img.height):
        for x in range(img.width):
            p = img.getpixel((x, y))
            if p[:3] == fill[:3] and p[3] > 200:
                rows.setdefault(y, x)
                break
    ys = sorted(rows)
    assert ys
    # 按行间空隙分行（行距 24，同一段内行 y 连续）
    line_starts, prev = [], None
    for y in ys:
        if prev is None or y - prev > 2:
            line_starts.append(rows[y])
        prev = y
    assert len(line_starts) == 2
    assert abs(line_starts[0] - line_starts[1]) <= 2  # 左缘对齐（抗锯齿 1-2px 容差）


def test_layout_badge_size(assets_dir):
    """角标尺寸可调：seal 区域 badge_size 改变 seal 框左上角角标渲染。"""
    small = render_mechanism(_mech(frame="seal", badge="bless", text="加护。"), assets_dir)
    big = render_mechanism(_mech(frame="seal", badge="bless", text="加护。"), assets_dir,
                           layout={"frames": {"seal": {"badge_size": 44}}})
    assert list(small.getdata()) != list(big.getdata())


def test_build_frame_custom_pitch(lib):
    """非原生行距：框高 = 顶底帽边距 + 行数×行距（以 5 行整图为基准增减）。"""
    base = lib.mech("frame_skill_5").height  # 155（边距 35）
    assert build_frame(lib, "skill", 5, pitch=30).height == base + 5 * 6
    assert build_frame(lib, "skill", 5, pitch=18).height == base - 5 * 6
    # 原生行距且 ≤5 行仍直接命中对应行数整图
    assert build_frame(lib, "skill", 3, pitch=24).height == lib.mech("frame_skill_3").height
    # seal 底框为最小框：行数不足容量不缩小
    assert build_frame(lib, "seal", 1, pitch=18).height == 71 - (24 - 18) * 2


def test_badge_rendered_on_seal(assets_dir):
    """加护角标贴 seal 框左上角：角标深色圆盘像素覆盖浅底框左上角。"""
    base = render_mechanism(_mech(frame="seal", text="加护测试。"), assets_dir)
    badged = render_mechanism(
        _mech(frame="seal", badge="bless", text="加护测试。"), assets_dir)
    assert list(base.getdata()) != list(badged.getdata())
    # 底框左上角（22,14）原为浅底，贴角标后变为深色圆盘（实测角标该点为暗紫）
    px = badged.load()
    r, g, b, a = px[22, 14]
    assert a > 200 and r < 120 and b < 140


def test_badge_rejected_on_non_seal(assets_dir):
    for frame in ("invocation", "skill"):
        with pytest.raises(ValueError, match="badge"):
            render_mechanism(_mech(frame=frame, badge="bless"), assets_dir)


def test_too_many_lines_raises(assets_dir):
    text = "\n".join(f"第{i}行。" for i in range(MAX_LINES + 1))
    with pytest.raises(ValueError, match="软上限"):
        render_mechanism(_mech(text=text), assets_dir)


def test_unknown_frame_raises(assets_dir):
    with pytest.raises(ValueError, match="未知机制框类型"):
        render_mechanism(_mech(frame="unknown"), assets_dir)


def test_missing_name_raises(assets_dir):
    with pytest.raises(ValueError, match="关键字名"):
        render_mechanism(_mech(name=""), assets_dir)


def test_render_sizes_and_crop(assets_dir):
    """返回图按最紧 box 裁剪：行数单调决定高度；多行文本自动换行加高。"""
    img1 = render_mechanism(_mech(text="短。"), assets_dir)
    img2 = render_mechanism(
        _mech(text="一段足够长的描述文本，必然会超出框内可用宽度而自动换行，"
                   "从而把关键字框撑高一行。"), assets_dir)
    assert img2.height > img1.height
    # 裁剪后无整行透明留白（底缘有非透明像素）
    alpha = img2.getchannel("A")
    assert any(alpha.getpixel((x, img2.height - 1)) > 10 for x in range(img2.width))


def test_unknown_badge_raises(assets_dir):
    """badge 白名单校验：非法角标值拒绝（防注入拼资源路径），渲染层自带兜底。"""
    with pytest.raises(ValueError, match="badge"):
        render_mechanism(_mech(frame="seal", badge="../frame_skill_3"), assets_dir)


def test_layout_extreme_values_clamped(assets_dir):
    """畸形极大 layout 值被钳制：字号/icon_scale/badge_size 上限兜底，不撑出超大图。"""
    img = render_mechanism(_mech(frame="seal", badge="bless"), assets_dir,
                           layout={"text_size": 100000, "name_size": 10**6,
                                   "icon_scale": 1e9,
                                   "frames": {"seal": {"badge_size": 10**6}}})
    assert img.height <= 35 + 14 * 200 + 10  # 上限行数×上限行距 + 边帽


@pytest.mark.parametrize("frame", ["invocation", "skill", "seal"])
def test_render_chars_per_line_extends_frame_without_resampling_edges(assets_dir, frame):
    """每行字数只居中拼接框体中段，三类框的左右边缘均不重采样。"""
    base = render_mechanism(_mech(frame=frame), assets_dir, chars_per_line=12)
    narrow = render_mechanism(_mech(frame=frame), assets_dir, chars_per_line=11)
    wide = render_mechanism(_mech(frame=frame), assets_dir, chars_per_line=13)
    assert narrow.width == base.width - 24 and narrow.height == base.height
    assert wide.width == base.width + 24 and wide.height == base.height
    for image in (narrow, wide):
        assert list(image.crop((0, 0, 20, 8)).getdata()) == list(
            base.crop((0, 0, 20, 8)).getdata())
        assert list(image.crop((image.width - 20, 0, image.width, 8)).getdata()) == list(
            base.crop((base.width - 20, 0, base.width, 8)).getdata())


def test_render_chars_per_line_updates_text_region_without_overflow(assets_dir):
    """显式每行字数保持文本区在底框内，行距和文本块高度不变。"""
    base_info, narrow_info, wide_info = {}, {}, {}
    base = render_mechanism(_mech(), assets_dir, info=base_info)
    narrow = render_mechanism(_mech(), assets_dir, chars_per_line=11, info=narrow_info)
    wide = render_mechanism(_mech(), assets_dir, chars_per_line=13, info=wide_info)
    assert narrow_info["text_x"] == base_info["text_x"] == wide_info["text_x"] == 12
    assert narrow_info["text_width"] == base_info["text_width"] - 24
    assert wide_info["text_width"] == base_info["text_width"] + 24
    for image, info in ((base, base_info), (narrow, narrow_info), (wide, wide_info)):
        assert info["text_x"] >= 0
        assert info["text_x"] + info["text_width"] <= image.width
    assert narrow_info["text_height"] == wide_info["text_height"] == base_info["text_height"]


def test_render_chars_per_line_keeps_natural_frame_width(assets_dir):
    """字数较少时不裁窄原生框，文本区在框内居中且仍严格按字数换行。"""
    info10, info11 = {}, {}
    img = render_mechanism(_mech(text="一" * 10), assets_dir,
                           chars_per_line=10, info=info10)
    render_mechanism(_mech(text="一" * 11), assets_dir, chars_per_line=10, info=info11)
    assert img.width == 281
    assert info10["text_x"] == 20.5 and info10["text_width"] == 240
    assert info10["text_height"] == 3 * 24
    assert info11["text_height"] == 4 * 24


def test_long_name_shrinks_to_fit_chars_per_line(assets_dir, monkeypatch):
    """长机制名在字号倍率与显式每行字数下也不得被右框缘裁断。"""
    name = "超长机制名称" * 4
    captured = {}
    original = ImageDraw.ImageDraw.text

    def tracked(draw, xy, text, *args, **kwargs):
        if text == name:
            captured.update(x=xy[0], font=kwargs["font"])
        return original(draw, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", tracked)
    img = render_mechanism(_mech(name=name), assets_dir, chars_per_line=12, font_scale=2)
    assert captured["font"].size < 52
    assert captured["x"] >= 0
    assert captured["x"] + captured["font"].getlength(name) <= img.width


def test_render_font_scale_changes_text_frame_and_pitch(assets_dir):
    """字号倍率同步作用于文字、横向布局和框高；缺省倍率逐像素不变。"""
    base_info, scaled_info = {}, {}
    base = render_mechanism(_mech(), assets_dir, info=base_info)
    scaled = render_mechanism(_mech(), assets_dir, font_scale=1.5, info=scaled_info)
    assert scaled_info["text_height"] == base_info["text_height"] * 1.5
    assert scaled.height == 35 + 3 * 36  # 非原生行距沿用 5 行素材的 35px 顶底帽边距
    assert scaled.width == base.width * 1.5
    assert scaled_info["text_x"] == base_info["text_x"] * 1.5
    assert scaled_info["text_width"] == base_info["text_width"] * 1.5
    again = render_mechanism(_mech(), assets_dir, font_scale=1)
    assert list(again.getdata()) == list(base.getdata()) and again.size == base.size


def test_chars_per_line_survives_font_scale(assets_dir):
    """字号倍率改变后，显式每行字数仍保持不变。"""
    info12, info13 = {}, {}
    img = render_mechanism(_mech(text="一" * 12), assets_dir,
                           chars_per_line=12, font_scale=1.5, info=info12)
    render_mechanism(_mech(text="一" * 13), assets_dir,
                     chars_per_line=12, font_scale=1.5, info=info13)
    assert img.width == 468
    assert info12["text_height"] == 3 * 36
    assert info13["text_height"] == 4 * 36


@pytest.mark.parametrize("kwargs", [
    {"chars_per_line": 0}, {"chars_per_line": -1}, {"chars_per_line": 1.5},
    {"chars_per_line": True}, {"chars_per_line": 8193},
    {"font_scale": 0}, {"font_scale": -1}, {"font_scale": True},
    {"font_scale": float("nan")}, {"font_scale": float("inf")}, {"font_scale": 1e9},
])
def test_render_size_parameters_validated(assets_dir, kwargs):
    with pytest.raises(ValueError):
        render_mechanism(_mech(), assets_dir, **kwargs)
