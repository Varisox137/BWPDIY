"""机制描述框渲染：灵咒框（invocation）/关键字框（skill，技能描述黑框素材）/加护蚀印框（seal）。

排版口径（样式参考 assets/psd_export/文字描述-EX，取色与字号由素材实测定值）：
- 字号由机制布局配置（DEFAULT_LAYOUT，可被 assets/layout.json「机制」段覆盖）：
  正文 text_size 默认 24（方正北魏楷书 desc 字体；技能描述.png 96px/4 字实测），
  关键字名 name_size 默认 26 略大于正文（不做加粗描边）；行距 = 正文字号。
  原生行距 LINE_PITCH=24 = 灵咒框相邻行数素材高度差（三/四/五行字 102/126/150，
  差恒定 24；关键字框 104/131/155 取 5-4 行差 24）。
- 内容行数（关键字名 + 空行 + 描述行）× 行距决定框高：原生行距且 ≤5 行直接命中
  对应行数素材（<3 行用 3 行框）；其余从 5 行素材（seal 从底框）中部切横带纵向
  拼接/裁除（顶帽+中段+底帽；行距非 24 时横带等比缩放到行距高）。seal 框仅单一
  底框（71px，容 2 行内容）。平铺带位置逐行扫描素材确定：带内与接缝逐行色差
  invocation ≤1 / skill 0 / seal ≤9（素材自带噪点纹理，色差不可见）。
- 关键字名在框内左上角左对齐、金色；每种框体有独立文本区域（frames.<框>：
  text_x 左缘 / text_dy 竖直偏移 / width 换行宽——框高随内容行数动态变化，
  区域竖直方向以框中心 + text_dy 为基准，不设固定高度；GUI 浅绿框按实际
  文本块（行数×行距）画出）；关键字名另有 name_offset 微调；与描述之间
  空一行；描述逐行**左对齐**（同行左缘 = 区域左缘），文本块竖直居中于
  框中心 + text_dy。
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

NAME_FILL = (166, 133, 64, 255)      # 关键字名金（技能名.png 主色）
KEYWORD_FILL = (166, 133, 64, 255)   # [[关键字]] 高亮同关键字名金
# 描述正文：浅框深字（技能描述_2.png 主色）/ 黑框浅字（技能描述.png 主色）——按框体不同
TEXT_FILL = {
    "invocation": (87, 88, 95, 255),
    "skill": (187, 188, 191, 255),
    "seal": (87, 88, 95, 255),
}

MARGIN_X = 18        # 文本左缘默认值
BADGE_POS = (6, 6)   # 加护/蚀印角标贴框左上角默认值
BADGE_NAME_GAP = 6   # 角标存在时关键字名与角标右缘的间距

# 机制布局默认配置（assets/layout.json「机制」段覆盖；GUI 布局设置「机制」页编辑）。
# 字号/角标三类框共用；文本区域完全分框独立（frames.<框>），无共用基础偏移。
_DEFAULT_REGION = {"text_x": MARGIN_X, "text_dy": 0, "width": 245}
DEFAULT_LAYOUT = {
    "name_size": 26,          # 关键字名字号（略大于正文，不加粗）
    "text_size": FONT_SIZE,   # 正文字号 = 行距
    "icon_scale": 1.0,        # 内嵌小图标相对文字大小
    "badge_size": 30,         # 加护/蚀印角标尺寸（素材原生 30）
    "badge_pos": list(BADGE_POS),
    "name_offset": [0, 0],    # 关键字名相对文本左缘/行中心的额外偏移
    # 各框独立文本区域：text_x 左缘（关键字名与描述共用）/ text_dy 竖直偏移
    # （相对框中心）/ width 换行宽；区域不设高度——框高随内容行数动态变化，
    # GUI 浅绿轮廓按实际文本块（行数×行距）画出
    "frames": {f: dict(_DEFAULT_REGION) for f in MECH_FRAMES},
}

# 中段平铺带：从素材 y=BAND_Y 起切 LINE_PITCH 高横带（接缝色差实测最小处）
_BAND_Y = {"invocation": 40, "skill": 42, "seal": 30}
_SEAL_BASE_ROWS = 2  # seal 底框容量 = 2 行内容（关键字名+空行即占满，任何描述都触发平铺扩展）
_MIN_TAIL = 20       # 缩框时底帽最少保留高度


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _pair(value) -> list | None:
    """[x, y] 数值对校验，合法返回 int 列表，否则 None。"""
    if (isinstance(value, (list, tuple)) and len(value) == 2
            and all(_is_num(v) for v in value)):
        return [int(value[0]), int(value[1])]
    return None


def _mech_layout(layout: dict | None) -> dict:
    """合并默认机制布局：仅认 DEFAULT_LAYOUT 白名单键，畸形值回退默认。"""
    cfg = dict(DEFAULT_LAYOUT)
    cfg["name_offset"] = list(DEFAULT_LAYOUT["name_offset"])
    cfg["badge_pos"] = list(DEFAULT_LAYOUT["badge_pos"])
    cfg["frames"] = {f: dict(_DEFAULT_REGION) for f in MECH_FRAMES}
    if not isinstance(layout, dict):
        return cfg
    for key in cfg:
        value = layout.get(key)
        if value is None or isinstance(value, bool):
            continue
        if key in ("name_offset", "badge_pos"):
            pair = _pair(value)
            if pair is not None:
                cfg[key] = pair
        elif key == "frames":
            if isinstance(value, dict):
                for f in MECH_FRAMES:
                    region = value.get(f)
                    if not isinstance(region, dict):
                        continue
                    for rk in _DEFAULT_REGION:
                        rv = region.get(rk)
                        if _is_num(rv):
                            cfg[key][f][rk] = int(rv)
        elif key == "icon_scale":
            if _is_num(value) and value > 0:
                cfg[key] = float(value)
        elif _is_num(value):
            cfg[key] = int(value)
    cfg["name_size"] = max(8, cfg["name_size"])
    cfg["text_size"] = max(8, cfg["text_size"])
    cfg["badge_size"] = max(4, cfg["badge_size"])
    for f in MECH_FRAMES:
        cfg["frames"][f]["width"] = max(20, cfg["frames"][f]["width"])
    return cfg


def build_frame(lib: AssetLibrary, frame: str, n_rows: int,
                pitch: int = LINE_PITCH) -> Image.Image:
    """按内容行数（关键字名+空行+描述行）× 行距拼框：原生行距且 ≤5 行直接命中
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


def render_mechanism(mech: dict, assets_dir, layout: dict | None = None,
                     info: dict | None = None) -> Image.Image:
    """渲染机制描述框，返回按最紧 alpha box 裁剪的 PNG 图。

    mech 字段：name 关键字名、frame（invocation/skill/seal）、text 多行描述、
    badge（bless/eclipse，仅 seal 框合法，贴框左上角）。
    layout：机制布局配置（assets/layout.json「机制」段），缺省/缺键回退 DEFAULT_LAYOUT。
    info：传入 dict 时回填实际文本块矩形（裁剪后坐标系）
    {text_x, text_top, text_width, text_height}，供 GUI 画文本区域轮廓。
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
        raise ValueError("机制缺少关键字名（name）")
    text = mech.get("text") or ""
    if not isinstance(text, str):
        raise ValueError("机制描述（text）必须是字符串")

    pitch = cfg["text_size"]  # 行距 = 正文字号
    font = lib.font("desc", pitch)
    name_font = lib.font("desc", cfg["name_size"])
    icon_variant = "black" if frame == "skill" else None
    region = cfg["frames"][frame]           # 本框独立文本区域
    text_x = region["text_x"]               # 文本（关键字名+描述）左缘
    items = parse_items(_normalize_newlines(text))
    lines = _wrap_items(items, font, lib, region["width"],
                        icon_variant, cfg["icon_scale"])
    if len(lines) > MAX_LINES:
        raise ValueError(f"机制描述行数 {len(lines)} 超软上限 {MAX_LINES} 行")

    total_rows = len(lines) + 2  # 关键字名 + 空行 + 描述行
    img = build_frame(lib, frame, total_rows, pitch)

    # 文本块竖直居中于框中心 + 本框 text_dy
    y0 = (img.height - total_rows * pitch) / 2 + region["text_dy"]

    out = img.copy()
    draw = ImageDraw.Draw(out)
    # 加护/蚀印角标贴框左上角；存在时关键字名右移避让（角标右缘 + BADGE_NAME_GAP）
    if badge:
        icon = lib.mech(f"badge_{badge}")
        if icon.width != cfg["badge_size"]:
            icon = icon.resize((cfg["badge_size"], cfg["badge_size"]), Image.LANCZOS)
        out.paste(icon, tuple(cfg["badge_pos"]), icon)
    name_x = (text_x if not badge else
              cfg["badge_pos"][0] + cfg["badge_size"] + BADGE_NAME_GAP)
    name_x += cfg["name_offset"][0]
    # 关键字名：框内左上角左对齐、金色、字号略大于正文（name_offset 额外微调）
    draw.text((name_x, y0 + pitch / 2 + cfg["name_offset"][1]), name, font=name_font,
              anchor="lm", fill=NAME_FILL)
    # 描述：与关键字名之间空一行，逐行左对齐（同行左缘 = 区域左缘；[[关键字]] 金色
    # 高亮、#xx 图标；正文色按框体 TEXT_FILL）
    icon_w = _icon_widths(items, font, lib, icon_variant, cfg["icon_scale"])
    for i, line in enumerate(lines):
        cx = text_x + _line_width(line, font, icon_w) / 2  # 左缘锚定换算为中心锚点
        _draw_styled_line(out, line, cx, y0 + pitch * (2.5 + i), font,
                          TEXT_FILL[frame], KEYWORD_FILL, lib, icon_variant,
                          cfg["icon_scale"])

    if info is not None:  # 实际文本块矩形（关键字名+空行+描述行）：左缘/顶/换行宽/行数×行距
        info.update(text_x=text_x, text_top=y0, text_width=region["width"],
                    text_height=total_rows * pitch)
    bbox = out.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    if not bbox:
        return out
    if info is not None:  # 换算到裁剪后坐标系
        info["text_x"] -= bbox[0]
        info["text_top"] -= bbox[1]
    return out.crop(bbox)
