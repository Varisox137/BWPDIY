"""文本层：矩形文本区排版（自动换行、行内居中、字号递减适配、障碍避让）。"""

from PIL import Image, ImageDraw, ImageFont

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.geometry import clamp_span_by_obstacles

TEXT_FILL = (60, 45, 30, 255)

_LINE_GAP = 6


def _line_height(font: ImageFont.FreeTypeFont) -> float:
    box = font.getbbox("国Ag")
    return box[3] - box[1] + _LINE_GAP


def _layout_at_size(text: str, font: ImageFont.FreeTypeFont,
                    region: dict, wrap: bool,
                    obstacles: list | None = None):
    """按给定字号在矩形区内排版，成功返回 [(行, cx, cy)]，失败返回 None。"""
    obstacles = obstacles or []
    cx, cy = region["center"]
    half_w, half_h = region["width"] / 2, region["height"] / 2
    y_top, y_bottom = cy - half_h, cy + half_h
    lh = _line_height(font)

    def span_at(y: float):
        span = (cx - half_w, cx + half_w)
        if obstacles:
            span = clamp_span_by_obstacles(span, y, lh / 2, obstacles)
        return span

    if not wrap:
        y = (y_top + y_bottom) / 2
        span = span_at(y)
        if span is None or font.getlength(text) > span[1] - span[0]:
            return None
        return [(text, (span[0] + span[1]) / 2, y)]
    lines: list[tuple[str, float, float]] = []
    current = ""
    y = y_top + lh / 2
    paragraphs = text.split("\n")
    for pi, paragraph in enumerate(paragraphs):
        for ch in paragraph:
            trial = current + ch
            span = span_at(y)
            width = (span[1] - span[0]) if span else 0.0
            if current and font.getlength(trial) > width:
                if span is None:  # 障碍封死本行：排版失败，交由字号递减/强排兜底
                    return None
                lines.append((current, (span[0] + span[1]) / 2, y))
                y += lh
                if y + lh / 2 > y_bottom:
                    return None
                current = ch
            else:
                current = trial
        if pi < len(paragraphs) - 1 or current:
            span = span_at(y)
            if span is None:
                return None
            lines.append((current, (span[0] + span[1]) / 2, y))
            current = ""
            if pi < len(paragraphs) - 1:
                y += lh
                if y + lh / 2 > y_bottom:
                    return None
    return lines or None


def fit_in_region(text: str, region: dict, lib: AssetLibrary,
                  obstacles: list | None = None):
    """字号从大到小适配，返回 (font, lines)；最小字号仍排不下时返回 None。"""
    max_size, min_size = region["font_range"]
    for size in range(max_size, min_size - 1, -1):
        font = lib.font(region["font"], size)
        lines = _layout_at_size(text, font, region, region["wrap"], obstacles)
        if lines is not None:
            return font, lines
    return None


def draw_region(canvas: Image.Image, lib: AssetLibrary, text: str,
                region: dict, obstacles: list | None = None,
                fill=TEXT_FILL) -> Image.Image:
    fitted = fit_in_region(text, region, lib, obstacles)
    if fitted is None:
        font = lib.font(region["font"], region["font_range"][1])
        lines = _layout_at_size(text, font, region, region["wrap"], obstacles)
        if lines is None:  # 强排兜底：nowrap 超宽，或 wrap 最小字号仍排不下（含障碍封死）
            lines = [(text, region["center"][0], region["center"][1])]
        fitted = (font, lines)
    font, lines = fitted
    out = canvas.copy()
    draw = ImageDraw.Draw(out)
    for line, cx, cy in lines:
        draw.text((cx, cy), line, font=font, anchor="mm", fill=fill)
    return out
