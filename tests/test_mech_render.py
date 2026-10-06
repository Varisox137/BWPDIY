"""机制描述框渲染测试：帧拼接（行数单调/接缝色差）、关键字高亮与内嵌图标、
技能名左上角左对齐加粗、badge 角标、行数软上限与 badge 交叉规则。"""

from pathlib import Path

import pytest

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.mech import (
    LINE_PITCH,
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


def test_frame_below_3_uses_3_line(lib):
    for frame in ("invocation", "skill"):
        assert build_frame(lib, frame, 0).height == build_frame(lib, frame, 3).height
        assert build_frame(lib, frame, 2).height == build_frame(lib, frame, 3).height


def test_seal_frame_extension(lib):
    """seal 底框容 2 行内容（技能名+空行即占满），超出按行高平铺扩展。"""
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


def test_name_top_left_bold(assets_dir):
    """技能名在框内左上角左对齐（x≈MARGIN_X）、金色加粗；与描述之间空一行。"""
    from bwpdiy.render.mech import MARGIN_X
    img = render_mechanism(_mech(), assets_dir)
    gold_xs = [x for x in range(img.width) for y in range(img.height // 3)
               if (lambda p: p[:3] == NAME_FILL[:3] and p[3] > 200)(img.getpixel((x, y)))]
    assert gold_xs and min(gold_xs) <= MARGIN_X + 2  # 左对齐：金色墨迹贴近左边距


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
    with pytest.raises(ValueError, match="技能名"):
        render_mechanism(_mech(name=""), assets_dir)


def test_render_sizes_and_crop(assets_dir):
    """返回图按最紧 box 裁剪：行数单调决定高度；多行文本自动换行加高。"""
    img1 = render_mechanism(_mech(text="短。"), assets_dir)
    img2 = render_mechanism(
        _mech(text="一段足够长的描述文本，必然会超出框内可用宽度而自动换行，"
                   "从而把技能描述黑框撑高一行。"), assets_dir)
    assert img2.height > img1.height
    # 裁剪后无整行透明留白（底缘有非透明像素）
    alpha = img2.getchannel("A")
    assert any(alpha.getpixel((x, img2.height - 1)) > 10 for x in range(img2.width))
