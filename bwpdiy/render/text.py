"""文本层：矩形文本区排版（自动换行、逐行居中、字号递减适配、掩膜墨迹避让）。"""

import re

from PIL import Image, ImageDraw, ImageFont

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.geometry import clamp_span_by_mask, mask_row_runs

# 文字颜色按框品（取色来源见 T1 资产报告：文字位图不透明像素主色）：
# name 卡名 / footer 脚注 / desc 描述
FRAME_TEXT_FILL = {
    "norm": {"name": (61, 68, 75, 255), "footer": (61, 68, 75, 255),
             "desc": (92, 112, 126, 255)},
    "blue": {"name": (233, 244, 254, 255), "footer": (201, 218, 238, 255),
             "desc": (202, 219, 239, 255)},
    "black": {"name": (187, 175, 151, 255), "footer": (187, 169, 129, 255),
              "desc": (218, 194, 146, 255)},
    "red": {"name": (251, 234, 237, 255), "footer": (217, 161, 170, 255),
            "desc": (238, 206, 209, 255)},
}

TEXT_FILL = FRAME_TEXT_FILL["norm"]["desc"]

_LINE_GAP = 6


def _normalize_newlines(text: str) -> str:
    """连续 \n 合并为一个换行（显式 \n 是强制断行，但不产生空行）。"""
    return re.sub(r"\n+", "\n", text)


def _line_height(font: ImageFont.FreeTypeFont) -> float:
    box = font.getbbox("国Ag")
    return box[3] - box[1] + _LINE_GAP


def _layout_at_size(text: str, font: ImageFont.FreeTypeFont,
                    region: dict, wrap: bool,
                    row_runs: dict | None = None):
    """按给定字号在矩形区内排版，成功返回 [(行, cx, cy)]，失败返回 None。

    文本块（行数 × 行高）在区域内水平逐行居中、竖直整体居中：
    先定字号与行数，再把文本块中心对齐区域中心。居中锚点可用
    `center_offset`（缺省 [0,0]，per-type 键）平移——区域边界与行宽不变，
    只移动视觉居中基准（如右下角大数字时左移锚点让触界行视觉居中）。
    行可用宽度按掩膜墨迹（row_runs）逐行收窄，间距字段 obstacle_gap（缺省 4）。
    """
    cx, cy = region["center"]
    ox, oy = region.get("center_offset", [0, 0])
    acx, acy = cx + ox, cy + oy  # 居中锚点
    half_w, half_h = region["width"] / 2, region["height"] / 2
    y_top, y_bottom = cy - half_h, cy + half_h
    lh = _line_height(font)
    gap = region.get("obstacle_gap", 4)

    def span_at(y: float):
        span = (cx - half_w, cx + half_w)
        if row_runs:
            span = clamp_span_by_mask(span, y, lh / 2, row_runs, gap)
        return span

    def centered_cx(t: str, y: float) -> float:
        """行中心 x：默认居中锚点 acx；仅当行的实际宽度触到收窄 span 边界时
        最小平移避让（短末行不因远处角标整体偏移，保持视觉居中）。"""
        span = span_at(y)
        if span is None:
            return acx
        half = font.getlength(t) / 2
        return min(max(acx, span[0] + half), span[1] - half)

    if not wrap:
        span = span_at(acy)
        if span is None or font.getlength(text) > span[1] - span[0]:
            return None
        return [(text, centered_cx(text, acy), acy)]

    paragraphs = text.split("\n")

    def wrap_from(y: float):
        """从行中心 y 起贪心换行，返回行文本列表；排不下（出底界/被封死）返回 None。"""
        lines: list[str] = []
        current = ""
        for pi, paragraph in enumerate(paragraphs):
            for ch in paragraph:
                trial = current + ch
                span = span_at(y)
                width = (span[1] - span[0]) if span else 0.0
                if current and font.getlength(trial) > width:
                    if span is None:  # 障碍封死本行：排版失败，交由字号递减/强排兜底
                        return None
                    lines.append(current)
                    y += lh
                    if y + lh / 2 > y_bottom:
                        return None
                    current = ch
                else:
                    current = trial
            if pi < len(paragraphs) - 1 or current:
                if span_at(y) is None:
                    return None
                lines.append(current)
                current = ""
                if pi < len(paragraphs) - 1:
                    y += lh
                    if y + lh / 2 > y_bottom:
                        return None
        return lines

    # 先自上而下排版定行数，再按行数竖直居中重排；居中改变了各行 y 带的
    # 可用宽度，行数可能变化，迭代至行数稳定（计数重复 = 震荡，失败兜底）。
    line_texts = wrap_from(y_top + lh / 2)
    if not line_texts:
        return None
    seen = set()
    while len(line_texts) not in seen:
        seen.add(len(line_texts))
        n = len(line_texts)
        y0 = acy - n * lh / 2 + lh / 2
        # 文本块须整体落在区域内（锚点偏移可能把块推出界；换行推进只检查中间行）
        if y0 - lh / 2 < y_top - 1e-6 or acy + n * lh / 2 > y_bottom + 1e-6:
            return None
        recentered = wrap_from(y0)
        if recentered is None:
            return None
        if len(recentered) == n:
            return [(t, centered_cx(t, y0 + i * lh),
                     y0 + i * lh) for i, t in enumerate(recentered)]
        line_texts = recentered
    return None


def _fit(text: str, region: dict, lib: AssetLibrary, row_runs: dict | None):
    max_size, min_size = region["font_range"]
    for size in range(max_size, min_size - 1, -1):
        font = lib.font(region["font"], size)
        lines = _layout_at_size(text, font, region, region["wrap"], row_runs)
        if lines is not None:
            return font, lines
    return None


def fit_in_region(text: str, region: dict, lib: AssetLibrary,
                  obstacle_mask: Image.Image | None = None):
    """字号从大到小适配，返回 (font, lines)；最小字号仍排不下时返回 None。"""
    text = _normalize_newlines(text)
    row_runs = mask_row_runs(obstacle_mask) if obstacle_mask is not None else None
    return _fit(text, region, lib, row_runs)


def draw_region(canvas: Image.Image, lib: AssetLibrary, text: str,
                region: dict, obstacle_mask: Image.Image | None = None,
                fill=TEXT_FILL) -> Image.Image:
    text = _normalize_newlines(text)
    row_runs = mask_row_runs(obstacle_mask) if obstacle_mask is not None else None
    fitted = _fit(text, region, lib, row_runs)
    if fitted is None:
        font = lib.font(region["font"], region["font_range"][1])
        lines = _layout_at_size(text, font, region, region["wrap"], row_runs)
        if lines is None:  # 强排兜底：nowrap 超宽，或 wrap 最小字号仍排不下（含障碍封死）
            lines = [(text, region["center"][0], region["center"][1])]
        fitted = (font, lines)
    font, lines = fitted
    out = canvas.copy()
    draw = ImageDraw.Draw(out)
    for line, cx, cy in lines:
        draw.text((cx, cy), line, font=font, anchor="mm", fill=fill)
    return out
