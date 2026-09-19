"""文本层：矩形文本区排版（自动换行、逐行居中、字号递减适配、掩膜墨迹避让、关键字异色）。

关键字高亮：描述文本中 [[关键字]] 用双英文方括号标记（v1.2.1 起；单 [ ] 为字面字符），
括号不绘制、内容按框品异色（FRAME_KEYWORD_FILL）。括号匹配校验在排版入口执行
（parse_keyword_segments）。
"""

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

# 关键字异色按框品（norm 取色自官方卡面关键字样本：金棕；其余框品取同族高对比色）
FRAME_KEYWORD_FILL = {
    "norm": (176, 132, 66, 255),
    "blue": (216, 168, 74, 255),
    "black": (242, 158, 46, 255),
    "red": (204, 128, 52, 255),
}

TEXT_FILL = FRAME_TEXT_FILL["norm"]["desc"]
KEYWORD_FILL = FRAME_KEYWORD_FILL["norm"]

_LINE_GAP = 6


def parse_keyword_segments(text: str) -> list[tuple[str, bool]]:
    """解析 [[关键字]] 双括号标记 → [(文本段, 是否关键字)]；标记本身不进入输出。

    单 [ / ] 为字面字符（可正常输入）。校验（均 ValueError）：
    '[[' 未闭合、']]' 无配对、'[[' 嵌套、'[[]]' 为空。
    连续三个以上括号按贪心解析：'[[[' = 开标记 + 字面 '['，']]]' = 闭标记 + 字面 ']'。
    """
    segs: list[tuple[str, bool]] = []
    plain, kw = "", None
    i = 0
    while i < len(text):
        pair = text[i:i + 2]
        if pair == "[[":
            if kw is not None:
                raise ValueError("描述文本方括号不匹配：'[[' 内不能嵌套 '[['")
            if plain:
                segs.append((plain, False))
                plain = ""
            kw = ""
            i += 2
        elif pair == "]]":
            if kw is None:
                raise ValueError("描述文本方括号不匹配：']]' 缺少配对的 '[['")
            if not kw:
                raise ValueError("描述文本方括号不匹配：'[[]]' 内容为空")
            segs.append((kw, True))
            kw = None
            i += 2
        else:
            if kw is not None:
                kw += text[i]
            else:
                plain += text[i]
            i += 1
    if kw is not None:
        raise ValueError("描述文本方括号不匹配：'[[' 未闭合")
    if plain:
        segs.append((plain, False))
    return segs


def _styled_chars(text: str) -> list[tuple[str, bool]]:
    """str → [(字符, 是否关键字)]：剥离 [[关键字]] 标记，排版宽度按可见字符计。"""
    return [(ch, kw) for seg, kw in parse_keyword_segments(text) for ch in seg]


def _plain(chars: list[tuple[str, bool]]) -> str:
    return "".join(ch for ch, _ in chars)


def _normalize_newlines(text: str) -> str:
    """连续 \n 合并为一个换行（显式 \n 是强制断行，但不产生空行）。"""
    return re.sub(r"\n+", "\n", text)


def _line_height(font: ImageFont.FreeTypeFont) -> float:
    box = font.getbbox("国Ag")
    return box[3] - box[1] + _LINE_GAP


def _layout_at_size(chars: list[tuple[str, bool]], font: ImageFont.FreeTypeFont,
                    region: dict, wrap: bool,
                    row_runs: dict | None = None, dy: float = 0):
    """按给定字号在矩形区内排版，成功返回 [(行字符列表, cx, cy)]，失败返回 None。

    文本块（行数 × 行高）在区域内水平逐行居中、竖直整体居中：
    先定字号与行数，再把文本块中心对齐居中锚点。居中锚点 =
    区域中心 + `center_offset`（缺省 [0,0]，per-type 键）- 临时上移 dy
    （_fit 的自适应尝试用，见 _fit）；区域边界与行宽不变。
    行可用宽度按掩膜墨迹（row_runs）逐行收窄，间距字段 obstacle_gap（缺省 4）。
    """
    cx, cy = region["center"]
    ox, oy = region.get("center_offset", [0, 0])
    acx, acy = cx + ox, cy + oy - dy  # 居中锚点（dy=自适应临时上移量）
    half_w, half_h = region["width"] / 2, region["height"] / 2
    y_top, y_bottom = cy - half_h, cy + half_h
    lh = _line_height(font)
    gap = region.get("obstacle_gap", 4)

    def span_at(y: float):
        span = (cx - half_w, cx + half_w)
        if row_runs:
            span = clamp_span_by_mask(span, y, lh / 2, row_runs, gap)
        return span

    def centered_cx(t: list, y: float) -> float:
        """行中心 x：默认居中锚点 acx；仅当行的实际宽度触到收窄 span 边界时
        最小平移避让（短末行不因远处角标整体偏移，保持视觉居中）。"""
        span = span_at(y)
        if span is None:
            return acx
        half = font.getlength(_plain(t)) / 2
        return min(max(acx, span[0] + half), span[1] - half)

    if not wrap:
        span = span_at(acy)
        if span is None or font.getlength(_plain(chars)) > span[1] - span[0]:
            return None
        return [(chars, centered_cx(chars, acy), acy)]

    paragraphs = [[]]
    for ch in chars:
        if ch[0] == "\n":
            paragraphs.append([])
        else:
            paragraphs[-1].append(ch)

    def wrap_from(y: float):
        """从行中心 y 起贪心换行，返回行字符列表；排不下（出底界/被封死）返回 None。"""
        lines: list[list] = []
        current: list = []
        for pi, paragraph in enumerate(paragraphs):
            for ch in paragraph:
                trial = current + [ch]
                span = span_at(y)
                width = (span[1] - span[0]) if span else 0.0
                if current and font.getlength(_plain(trial)) > width:
                    if span is None:  # 障碍封死本行：排版失败，交由字号递减/强排兜底
                        return None
                    lines.append(current)
                    y += lh
                    if y + lh / 2 > y_bottom:
                        return None
                    current = [ch]
                else:
                    current = trial
            if pi < len(paragraphs) - 1 or current:
                if span_at(y) is None:
                    return None
                lines.append(current)
                current = []
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


def _fit(chars: list[tuple[str, bool]], region: dict, lib: AssetLibrary,
         row_runs: dict | None):
    """字号从大到小适配；每个字号上先尝试逐 px 临时上移居中锚点（1px 步进、
    至多半行高）——接受条件：排得下且每一行都水平居中（未被障碍挤偏）。
    当前字号所有上移量都不行才减小字号。"""
    max_size, min_size = region["font_range"]
    acx = region["center"][0] + region.get("center_offset", [0, 0])[0]
    for size in range(max_size, min_size - 1, -1):
        font = lib.font(region["font"], size)
        max_dy = int(_line_height(font) / 2)
        for dy in range(0, max_dy + 1):
            lines = _layout_at_size(chars, font, region, region["wrap"], row_runs, dy=dy)
            if lines is not None and all(abs(cx - acx) < 1e-6 for _, cx, _ in lines):
                return font, lines
    return None


def fit_in_region(text: str, region: dict, lib: AssetLibrary,
                  obstacle_mask: Image.Image | None = None):
    """字号从大到小适配，返回 (font, [(行文本, cx, cy)])；最小字号仍排不下时返回 None。

    [[关键字]] 标记在排版前剥离（宽度按可见字符计），返回的行文本为纯文本。
    """
    text = _normalize_newlines(text)
    chars = _styled_chars(text)
    row_runs = mask_row_runs(obstacle_mask) if obstacle_mask is not None else None
    fitted = _fit(chars, region, lib, row_runs)
    if fitted is None:
        return None
    font, lines = fitted
    return font, [(_plain(line), cx, cy) for line, cx, cy in lines]


def draw_region(canvas: Image.Image, lib: AssetLibrary, text: str,
                region: dict, obstacle_mask: Image.Image | None = None,
                fill=TEXT_FILL, keyword_fill=None) -> Image.Image:
    """排版并绘制文本。[[关键字]] 段用 keyword_fill 异色绘制（None 时与正文同色）。"""
    text = _normalize_newlines(text)
    chars = _styled_chars(text)
    row_runs = mask_row_runs(obstacle_mask) if obstacle_mask is not None else None
    fitted = _fit(chars, region, lib, row_runs)
    if fitted is None:
        font = lib.font(region["font"], region["font_range"][1])
        lines = _layout_at_size(chars, font, region, region["wrap"], row_runs)
        if lines is None:  # 强排兜底：nowrap 超宽，或 wrap 最小字号仍排不下（含障碍封死）
            lines = [(chars, region["center"][0], region["center"][1])]
        fitted = (font, lines)
    font, lines = fitted
    out = canvas.copy()
    draw = ImageDraw.Draw(out)
    for line, cx, cy in lines:
        _draw_styled_line(draw, line, cx, cy, font, fill, keyword_fill)
    return out


def _draw_styled_line(draw: ImageDraw.ImageDraw, line: list[tuple[str, bool]],
                      cx: float, cy: float, font: ImageFont.FreeTypeFont,
                      fill, keyword_fill) -> None:
    """无关键字段时整行 anchor=mm 一次绘制；含关键字段时按段异色、anchor=lm 横向推进。"""
    if not line:
        return
    if keyword_fill is None or not any(kw for _, kw in line):
        draw.text((cx, cy), _plain(line), font=font, anchor="mm", fill=fill)
        return
    x = cx - font.getlength(_plain(line)) / 2
    run, run_kw = [], line[0][1]
    for ch, kw in line:
        if kw != run_kw:
            s = _plain(run)
            draw.text((x, cy), s, font=font, anchor="lm",
                      fill=keyword_fill if run_kw else fill)
            x += font.getlength(s)
            run, run_kw = [], kw
        run.append((ch, kw))
    s = _plain(run)
    draw.text((x, cy), s, font=font, anchor="lm", fill=keyword_fill if run_kw else fill)
