"""机制描述框渲染：灵咒框（invocation）/技能描述黑框（skill）/加护蚀印框（seal）。

排版口径（样式参考 assets/psd_export/文字描述-EX，取色与字号由素材实测定值）：
- 固定字号 24（方正北魏楷书 desc 字体；技能描述.png 96px/4 字、技能名.png 49px/2 字），
  不做字号缩放；内容行数（技能名 + 空行 + 描述行）决定框高，行距 LINE_PITCH=24 =
  灵咒框相邻行数素材高度差（三/四/五行字 102/126/150，差恒定 24；技能框 104/131/155
  取 5-4 行差 24）。
- ≤5 行用对应行数素材（<3 行用 3 行框）；>5 行从 5 行素材中部切一行高横带纵向
  拼接扩展（顶帽+平铺中段+底帽）；seal 框仅单一底框（71px，容 2 行内容），
  超出同样切中部横带平铺。平铺带位置逐行扫描素材确定：带内与接缝逐行色差
  invocation ≤1 / skill 0 / seal ≤9（素材自带噪点纹理，色差不可见）。
- 技能名在框内左上角左对齐、金色加粗（同色描边加粗，无深色描边）；与描述之间空一行；
  描述逐行水平居中，「技能名+空行+描述」整块在框内竖直居中。
- 描述复用卡面文本管线：[[关键字]] 金色高亮、#xx 内嵌小图标（text.py parse_items /
  _draw_styled_line）；正文颜色按框体（浅框深字/黑框浅字，TEXT_FILL）；
  黑框（skill）派系图标用 _black 变体。
- 软上限 MAX_LINES 行（描述行数），超过抛 ValueError 防爆图。
"""

from pathlib import Path

from PIL import Image, ImageDraw

from bwpdiy.render.assets import AssetLibrary, get_library
from bwpdiy.render.text import (
    _draw_styled_line,
    _icon_widths,
    _line_width,
    _normalize_newlines,
    parse_items,
)

MECH_FRAMES = ("invocation", "skill", "seal")

FONT_SIZE = 24
LINE_PITCH = 24
MAX_LINES = 12

NAME_FILL = (166, 133, 64, 255)      # 技能名金（技能名.png 主色）
NAME_BOLD_WIDTH = 1                  # 加粗：同色描边（不做深色描边）
KEYWORD_FILL = (166, 133, 64, 255)   # [[关键字]] 高亮同技能名金
# 描述正文：浅框深字（技能描述_2.png 主色）/ 黑框浅字（技能描述.png 主色）——按框体不同
TEXT_FILL = {
    "invocation": (87, 88, 95, 255),
    "skill": (187, 188, 191, 255),
    "seal": (87, 88, 95, 255),
}

MARGIN_X = 18        # 文本区双边距（技能名左对齐起点）
BADGE_POS = (6, 6)   # 加护/蚀印角标贴框左上角

# 中段平铺带：从素材 y=BAND_Y 起切 LINE_PITCH 高横带（接缝色差实测最小处）
_BAND_Y = {"invocation": 40, "skill": 42, "seal": 30}
_SEAL_BASE_ROWS = 2  # seal 底框容量 = 2 行内容（技能名+空行即占满，任何描述都触发平铺扩展）


def build_frame(lib: AssetLibrary, frame: str, n_rows: int) -> Image.Image:
    """按内容行数（技能名+空行+描述行）拼框：invocation/skill ≤5 行用整图、
    >5 行中段平铺扩展；seal 超过底框容量（_SEAL_BASE_ROWS 行）同样平铺扩展。
    n_rows<3 按 3 行框。"""
    if frame not in MECH_FRAMES:
        raise ValueError(f"未知机制框类型: {frame}")
    if frame == "seal":
        base = lib.mech("frame_seal")
        extra = max(0, n_rows - _SEAL_BASE_ROWS)
        return _extend(base, _BAND_Y["seal"], extra)
    n = min(max(n_rows, 3), 5)
    img = lib.mech(f"frame_{frame}_{n}")
    if n_rows > 5:
        img = _extend(img, _BAND_Y[frame], n_rows - 5)
    return img


def _extend(img: Image.Image, band_y: int, count: int) -> Image.Image:
    """在 band_y 处插入 count 份一行高横带（顶帽+平铺中段+底帽）。"""
    if count <= 0:
        return img.copy()
    w, h = img.size
    band = img.crop((0, band_y, w, band_y + LINE_PITCH))
    out = Image.new("RGBA", (w, h + count * LINE_PITCH))
    out.paste(img.crop((0, 0, w, band_y)), (0, 0))
    for i in range(count):
        out.paste(band, (0, band_y + i * LINE_PITCH))
    out.paste(img.crop((0, band_y, w, h)), (0, band_y + count * LINE_PITCH))
    return out


def _wrap_items(items: list[tuple[str, str, bool]], font, lib: AssetLibrary,
                width: float, icon_variant: str | None) -> list[list]:
    """固定字号按可用宽度贪心换行（图标宽度计入），\n 强制断行（不产生空行，
    与 _normalize_newlines 口径一致）。"""
    icon_w = _icon_widths(items, font, lib, icon_variant, 1.0)
    paragraphs = [[]]
    for item in items:
        if item[0] == "char" and item[1] == "\n":
            paragraphs.append([])
        else:
            paragraphs[-1].append(item)
    lines: list[list] = []
    for pi, paragraph in enumerate(paragraphs):
        current: list = []
        for item in paragraph:
            trial = current + [item]
            if current and _line_width(trial, font, icon_w) > width:
                lines.append(current)
                current = [item]
            else:
                current = trial
        if current or pi < len(paragraphs) - 1:
            lines.append(current)
    return lines


def render_mechanism(mech: dict, assets_dir) -> Image.Image:
    """渲染机制描述框，返回按最紧 alpha box 裁剪的 PNG 图。

    mech 字段：name 技能名、frame（invocation/skill/seal）、text 多行描述、
    badge（bless/eclipse，仅 seal 框合法，贴框左上角）。
    """
    lib = get_library(Path(assets_dir))
    frame = mech.get("frame")
    if frame not in MECH_FRAMES:
        raise ValueError(f"未知机制框类型: {frame}")
    badge = mech.get("badge")
    if badge and frame != "seal":
        raise ValueError("加护/蚀印角标（badge）仅加护蚀印框（seal）可用")
    name = mech.get("name") or ""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("机制缺少技能名（name）")
    text = mech.get("text") or ""
    if not isinstance(text, str):
        raise ValueError("机制描述（text）必须是字符串")

    font = lib.font("desc", FONT_SIZE)
    icon_variant = "black" if frame == "skill" else None
    frame_w = lib.mech("frame_seal").width  # 三种框同宽（281）
    items = parse_items(_normalize_newlines(text))
    lines = _wrap_items(items, font, lib, frame_w - 2 * MARGIN_X, icon_variant)
    if len(lines) > MAX_LINES:
        raise ValueError(f"机制描述行数 {len(lines)} 超软上限 {MAX_LINES} 行")

    total_rows = len(lines) + 2  # 技能名 + 空行 + 描述行
    img = build_frame(lib, frame, total_rows)

    # 「技能名 + 空行 + 描述」整块在框内竖直居中
    y0 = (img.height - total_rows * LINE_PITCH) / 2
    cx = img.width / 2

    out = img.copy()
    draw = ImageDraw.Draw(out)
    # 加护/蚀印角标贴框左上角；存在时技能名右移避让（角标 30×30 @ BADGE_POS）
    if badge:
        icon = lib.mech(f"badge_{badge}")
        out.paste(icon, BADGE_POS, icon)
    name_x = BADGE_POS[0] + 36 if badge else MARGIN_X
    # 技能名：框内左上角左对齐、金色加粗（同色描边加粗，无深色描边）
    draw.text((name_x, y0 + LINE_PITCH / 2), name, font=font, anchor="lm",
              fill=NAME_FILL, stroke_width=NAME_BOLD_WIDTH, stroke_fill=NAME_FILL)
    # 描述：与技能名之间空一行，逐行水平居中（[[关键字]] 金色高亮、#xx 图标；
    # 正文色按框体 TEXT_FILL）
    for i, line in enumerate(lines):
        _draw_styled_line(out, line, cx, y0 + LINE_PITCH * (2.5 + i), font,
                          TEXT_FILL[frame], KEYWORD_FILL, lib, icon_variant, 1.0)

    bbox = out.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    return out.crop(bbox) if bbox else out
