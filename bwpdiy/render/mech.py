"""机制描述框渲染：灵咒框（invocation）/技能描述黑框（skill）/加护蚀印框（seal）。

排版口径（样式参考 assets/psd_export/文字描述-EX，取色与字号由素材实测定值）：
- 字号由机制布局配置（DEFAULT_LAYOUT，可被 assets/layout.json「机制」段覆盖）：
  正文 text_size 默认 24（方正北魏楷书 desc 字体；技能描述.png 96px/4 字实测），
  技能名 name_size 默认 26 略大于正文（不做加粗描边）；行距 = 正文字号。
  原生行距 LINE_PITCH=24 = 灵咒框相邻行数素材高度差（三/四/五行字 102/126/150，
  差恒定 24；技能框 104/131/155 取 5-4 行差 24）。
- 内容行数（技能名 + 空行 + 描述行）× 行距决定框高：原生行距且 ≤5 行直接命中
  对应行数素材（<3 行用 3 行框）；其余从 5 行素材（seal 从底框）中部切横带纵向
  拼接/裁除（顶帽+中段+底帽；行距非 24 时横带等比缩放到行距高）。seal 框仅单一
  底框（71px，容 2 行内容）。平铺带位置逐行扫描素材确定：带内与接缝逐行色差
  invocation ≤1 / skill 0 / seal ≤9（素材自带噪点纹理，色差不可见）。
- 技能名在框内左上角左对齐、金色（name_x 左边距 + name_dy 竖直微调，布局可配）；
  与描述之间空一行；描述逐行水平居中，「技能名+空行+描述」整块在框内竖直居中。
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
KEYWORD_FILL = (166, 133, 64, 255)   # [[关键字]] 高亮同技能名金
# 描述正文：浅框深字（技能描述_2.png 主色）/ 黑框浅字（技能描述.png 主色）——按框体不同
TEXT_FILL = {
    "invocation": (87, 88, 95, 255),
    "skill": (187, 188, 191, 255),
    "seal": (87, 88, 95, 255),
}

MARGIN_X = 18        # 文本区双边距（技能名左对齐起点）默认值
BADGE_POS = (6, 6)   # 加护/蚀印角标贴框左上角默认值
BADGE_NAME_GAP = 6   # 角标存在时技能名与角标右缘的间距

# 机制布局默认配置（assets/layout.json「机制」段覆盖；GUI 布局设置「机制」页编辑）
DEFAULT_LAYOUT = {
    "name_size": 26,          # 技能名字号（略大于正文，不加粗）
    "name_x": MARGIN_X,       # 技能名左对齐起点（无角标时）
    "name_dy": 0,             # 技能名竖直微调（相对行中心）
    "text_size": FONT_SIZE,   # 正文字号 = 行距
    "margin_x": MARGIN_X,     # 正文换行双边距
    "icon_scale": 1.0,        # 内嵌小图标相对文字大小
    "badge_size": 30,         # 加护/蚀印角标尺寸（素材原生 30）
    "badge_pos": list(BADGE_POS),
}

# 中段平铺带：从素材 y=BAND_Y 起切 LINE_PITCH 高横带（接缝色差实测最小处）
_BAND_Y = {"invocation": 40, "skill": 42, "seal": 30}
_SEAL_BASE_ROWS = 2  # seal 底框容量 = 2 行内容（技能名+空行即占满，任何描述都触发平铺扩展）
_MIN_TAIL = 20       # 缩框时底帽最少保留高度


def _mech_layout(layout: dict | None) -> dict:
    """合并默认机制布局：仅认 DEFAULT_LAYOUT 白名单键，畸形值回退默认。"""
    cfg = dict(DEFAULT_LAYOUT)
    cfg["badge_pos"] = list(DEFAULT_LAYOUT["badge_pos"])
    if not isinstance(layout, dict):
        return cfg
    for key in cfg:
        value = layout.get(key)
        if value is None or isinstance(value, bool):
            continue
        if key == "badge_pos":
            if (isinstance(value, (list, tuple)) and len(value) == 2
                    and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)):
                cfg[key] = [int(value[0]), int(value[1])]
        elif key == "icon_scale":
            if isinstance(value, (int, float)) and value > 0:
                cfg[key] = float(value)
        elif isinstance(value, (int, float)):
            cfg[key] = int(value)
    cfg["name_size"] = max(8, cfg["name_size"])
    cfg["text_size"] = max(8, cfg["text_size"])
    cfg["margin_x"] = max(0, cfg["margin_x"])
    cfg["badge_size"] = max(4, cfg["badge_size"])
    return cfg


def build_frame(lib: AssetLibrary, frame: str, n_rows: int,
                pitch: int = LINE_PITCH) -> Image.Image:
    """按内容行数（技能名+空行+描述行）× 行距拼框：原生行距且 ≤5 行直接命中
    对应行数素材（n_rows<3 按 3 行框）；其余从 5 行素材（seal 从底框）中部
    平铺扩展/裁除到目标高 = 顶底帽边距 + n_rows×pitch。"""
    if frame not in MECH_FRAMES:
        raise ValueError(f"未知机制框类型: {frame}")
    if frame == "seal":
        img = lib.mech("frame_seal")
        n_rows = max(n_rows, _SEAL_BASE_ROWS)  # 底框即最小框，不再缩小行数
        cap_rows = _SEAL_BASE_ROWS
    elif pitch == LINE_PITCH and n_rows <= 5:
        return lib.mech(f"frame_{frame}_{min(max(n_rows, 3), 5)}").copy()
    else:
        img, cap_rows = lib.mech(f"frame_{frame}_5"), 5
        n_rows = max(n_rows, 3)
    margin = img.height - cap_rows * LINE_PITCH
    target = margin + n_rows * pitch
    return _resize_mid(img, _BAND_Y[frame], target - img.height, pitch)


def _resize_mid(img: Image.Image, band_y: int, delta: int, pitch: int) -> Image.Image:
    """在 band_y 处纵向增减 delta px：增 = 平铺一行高横带（行距非原生时横带等比
    缩放到 pitch 高，末段不足一带截取），减 = 裁除中段紧贴 band_y 之下的部分
    （顶帽不动，底帽最少保留 _MIN_TAIL）。"""
    w, h = img.size
    if delta > 0:
        band = img.crop((0, band_y, w, band_y + LINE_PITCH))
        if pitch != LINE_PITCH:
            band = band.resize((w, pitch), Image.BILINEAR)
        out = Image.new("RGBA", (w, h + delta))
        out.paste(img.crop((0, 0, w, band_y)), (0, 0))
        y = band_y
        remaining = delta
        while remaining > 0:
            step = min(remaining, band.height)
            out.paste(band.crop((0, 0, w, step)), (0, y))
            y += step
            remaining -= step
        out.paste(img.crop((0, band_y, w, h)), (0, y))
        return out
    if delta < 0:
        remove = min(-delta, h - band_y - _MIN_TAIL)
        out = Image.new("RGBA", (w, h - remove))
        out.paste(img.crop((0, 0, w, band_y)), (0, 0))
        out.paste(img.crop((0, band_y + remove, w, h)), (0, band_y))
        return out
    return img.copy()


def _wrap_items(items: list[tuple[str, str, bool]], font, lib: AssetLibrary,
                width: float, icon_variant: str | None,
                icon_scale: float = 1.0) -> list[list]:
    """固定字号按可用宽度贪心换行（图标宽度按 icon_scale 缩放计入），\n 强制断行
    （不产生空行，与 _normalize_newlines 口径一致）。"""
    icon_w = _icon_widths(items, font, lib, icon_variant, icon_scale)
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


def render_mechanism(mech: dict, assets_dir, layout: dict | None = None) -> Image.Image:
    """渲染机制描述框，返回按最紧 alpha box 裁剪的 PNG 图。

    mech 字段：name 技能名、frame（invocation/skill/seal）、text 多行描述、
    badge（bless/eclipse，仅 seal 框合法，贴框左上角）。
    layout：机制布局配置（assets/layout.json「机制」段），缺省/缺键回退 DEFAULT_LAYOUT。
    """
    lib = get_library(Path(assets_dir))
    cfg = _mech_layout(layout)
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

    pitch = cfg["text_size"]  # 行距 = 正文字号
    font = lib.font("desc", pitch)
    name_font = lib.font("desc", cfg["name_size"])
    icon_variant = "black" if frame == "skill" else None
    frame_w = lib.mech("frame_seal").width  # 三种框同宽（281）
    items = parse_items(_normalize_newlines(text))
    lines = _wrap_items(items, font, lib, frame_w - 2 * cfg["margin_x"],
                        icon_variant, cfg["icon_scale"])
    if len(lines) > MAX_LINES:
        raise ValueError(f"机制描述行数 {len(lines)} 超软上限 {MAX_LINES} 行")

    total_rows = len(lines) + 2  # 技能名 + 空行 + 描述行
    img = build_frame(lib, frame, total_rows, pitch)

    # 「技能名 + 空行 + 描述」整块在框内竖直居中
    y0 = (img.height - total_rows * pitch) / 2
    cx = img.width / 2

    out = img.copy()
    draw = ImageDraw.Draw(out)
    # 加护/蚀印角标贴框左上角；存在时技能名右移避让（角标右缘 + BADGE_NAME_GAP）
    if badge:
        icon = lib.mech(f"badge_{badge}")
        if icon.width != cfg["badge_size"]:
            icon = icon.resize((cfg["badge_size"], cfg["badge_size"]), Image.LANCZOS)
        out.paste(icon, tuple(cfg["badge_pos"]), icon)
    name_x = (cfg["badge_pos"][0] + cfg["badge_size"] + BADGE_NAME_GAP
              if badge else cfg["name_x"])
    # 技能名：框内左上角左对齐、金色、字号略大于正文（name_dy 竖直微调）
    draw.text((name_x, y0 + pitch / 2 + cfg["name_dy"]), name, font=name_font,
              anchor="lm", fill=NAME_FILL)
    # 描述：与技能名之间空一行，逐行水平居中（[[关键字]] 金色高亮、#xx 图标；
    # 正文色按框体 TEXT_FILL）
    for i, line in enumerate(lines):
        _draw_styled_line(out, line, cx, y0 + pitch * (2.5 + i), font,
                          TEXT_FILL[frame], KEYWORD_FILL, lib, icon_variant,
                          cfg["icon_scale"])

    bbox = out.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    return out.crop(bbox) if bbox else out
