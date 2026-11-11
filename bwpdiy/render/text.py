"""文本层：矩形文本区排版（自动换行、逐行居中、字号递减适配、掩膜墨迹避让、关键字异色、内嵌图标）。

v1.8.3 卡牌可选 smart/wrap/off：smart 独立开头纯关键字短句并比较条件类候选断行；
同字号且不增加行数时，另依次避免高亮跨行、符号留行尾、图标作行首；
wrap 仅自动换行与字号适配；off 仅显式分行、固定最大字号。通用文本与机制缺省 wrap。
换行与水平居中按整行文字掩膜的最紧边界测宽，段内 advance/字距保持不变。

关键字高亮：描述文本中 [[关键字]] 用双英文方括号标记（v1.2.1 起；单 [ ] 为字面字符），
括号不绘制、内容按框品异色（FRAME_KEYWORD_FILL）。从左往右匹配（'[[' 配其后
最近 ']]'），未匹配的括号按字面文本显示（v1.3.0 起不再报错）；高亮内部不再
解析新的 '[['，# 图标照常解析（异色对图标无效果）。

内嵌图标（v1.3.0）：`#<两位拼音首字母>` 在行内绘制为小图标（如 #ll → 力量），
记号本身不进入输出；图标高度=字号×icon_scale（desc 文本区布局字段，缺省 1.0，
按类型与框品独立），内嵌前预处理为 alpha bbox 外接的最紧方形 box（内容居中、占位
恒为正方形）、竖直中心对齐行中心；图标宽度计入换行与
逐行居中（随字号递减一同缩小）。图标与相邻文字之间自动加八分之一宽空格（0.125em）；
图标处于行首/行尾时该侧无空格（空格只存在于同一行内的文字-图标相邻处，
图标与图标相邻不加）。
'#' 后跟两个英文字母才视为图标代码：未知代码 ValueError；其余 '#' 为字面字符。
派系图标按条目 inline_faction_style 使用 _1/_2/_3（缺省 _1，icon_variant 不改变派系样式）。
"""

import re
from functools import lru_cache

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

# 内嵌图标代码（两位拼音首字母，不区分大小写）→ assets/icons/<name>.png
ICON_CODES = {
    "ll": "power",          # 力量
    "sm": "health",         # 生命
    "hj": "shield",         # 护甲
    "pj": "fragile",        # 破甲
    "nl": "energy",         # 能量
    "nj": "intensity",      # 耐久（幻境）
    "zl": "combat_power",   # 战力
    "fl": "weak",           # 乏力
    "sj": "bounty",         # 赏金
    "hl": "faction_red",    # 红莲
    "cy": "faction_green",  # 苍叶
    "ql": "faction_blue",   # 青岚
    "zy": "faction_purple", # 紫岩
}

_ICON_RE = re.compile(r"#([A-Za-z]{2})")


def parse_keyword_segments(text: str) -> list[tuple[str, bool]]:
    """解析 [[关键字]] 双括号标记 → [(文本段, 是否关键字)]；标记本身不进入输出。

    从左往右匹配：'[[' 配其后最近的 ']]'，内容为关键字（内部不再解析新的
    '[['——字面进入关键字内容；# 图标照常解析，但异色对图标无实际效果）。
    未匹配的括号一律按字面文本显示：'[[' 无闭合、']]' 无配对、'[[]]' 空内容；
    单 [ ] 为字面字符。
    """
    segs: list[tuple[str, bool]] = []
    plain = ""
    i = 0
    while i < len(text):
        pair = text[i:i + 2]
        if pair == "[[":
            end = text.find("]]", i + 2)
            if end == -1 or end == i + 2:  # 未闭合或空内容：按字面文本
                plain += "[["
                i += 2
                continue
            if plain:
                segs.append((plain, False))
                plain = ""
            segs.append((text[i + 2:end], True))
            i = end + 2
        elif pair == "]]":
            plain += "]]"  # 无配对闭标记：按字面文本
            i += 2
        else:
            plain += text[i]
            i += 1
    if plain:
        segs.append((plain, False))
    return segs


def parse_items(text: str) -> list[tuple[str, str, bool]]:
    """解析 [[关键字]] 与 #xx 内嵌图标 → [(kind, value, kw)]。

    kind ∈ "char"（单字符）/ "icon"（图标代码）；kw = 是否在关键字段内。
    排版宽度按可见内容计（图标按缩放后宽度），标记本身不进入输出。
    '#' 后两个英文字母查 ICON_CODES（不区分大小写），未知代码 ValueError；
    括号不配对不报错（parse_keyword_segments 已按字面文本处理）。
    """
    items: list[tuple[str, str, bool]] = []
    for seg, kw in parse_keyword_segments(text):
        pos = 0
        for m in _ICON_RE.finditer(seg):
            items.extend(("char", ch, kw) for ch in seg[pos:m.start()])
            code = m.group(1).lower()
            if code not in ICON_CODES:
                raise ValueError(f"描述文本图标代码未知: '#{m.group(1)}'")
            items.append(("icon", code, kw))
            pos = m.end()
        items.extend(("char", ch, kw) for ch in seg[pos:])
    return items


def _plain(items: list[tuple[str, str, bool]]) -> str:
    """item 列表 → 纯文本（图标项不计）。"""
    return "".join(v for k, v, _ in items if k == "char")


def _icon_image(code: str, lib: AssetLibrary, icon_variant: str | None,
                inline_faction_style: int = 1) -> Image.Image:
    """图标原图按 alpha≥128 碰撞轮廓紧致裁剪（抗锯齿淡边缘不算墨迹，仿牌框阈值
    预处理）后，alpha_composite 透明扩展为容纳内容的最紧方形 box（保真源 alpha、
    内容居中，内嵌前预处理：图标占位恒为正方形）；派系图标按条目选择 1/2/3 样式。"""
    stem = ICON_CODES[code]
    if stem.startswith("faction_"):
        if (isinstance(inline_faction_style, bool)
                or inline_faction_style not in (1, 2, 3)):
            raise ValueError("inline_faction_style 必须是 1、2 或 3")
        stem = f"{stem}_{inline_faction_style}"
    img = lib.icon(stem)
    bbox = img.getchannel("A").point(lambda v: 255 if v >= 128 else 0).getbbox()
    if bbox:
        img = img.crop(bbox)
    side = max(img.width, img.height)
    if img.width != img.height:
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.alpha_composite(img, ((side - img.width) // 2, (side - img.height) // 2))
        img = square
    return img


def _icon_size(code: str, height: int, lib: AssetLibrary,
               icon_variant: str | None, scale: float = 1.0,
               inline_faction_style: int = 1) -> tuple[int, int]:
    """图标缩放目标尺寸：高=字号×scale（icon_scale 布局字段，缺省 1.0）；
    源图已预处理为方形，宽=高。"""
    h = max(1, round(height * scale))
    return h, h


def _icon_widths(items: list[tuple[str, str, bool]], font: ImageFont.FreeTypeFont,
                 lib: AssetLibrary, icon_variant: str | None,
                 scale: float = 1.0, inline_faction_style: int = 1) -> dict[str, int]:
    return {v: _icon_size(v, font.size, lib, icon_variant, scale, inline_faction_style)[0]
            for k, v, _ in items if k == "icon"}


_ICON_GAP_EM = 0.125  # 图标与同行相邻文字之间的八分之一宽空格（em 计）


@lru_cache(maxsize=4096)
def _text_ink_bbox(font: ImageFont.FreeTypeFont, text: str):
    return font.getmask(text).getbbox()


def _line_metrics(line: list[tuple[str, str, bool]], font: ImageFont.FreeTypeFont,
                  icon_w: dict[str, int]) -> tuple[float, float]:
    """整行可见内容的水平紧边界，坐标相对于排版原点。

    字符段仍按 getlength 推进以保留字距与段内位置，但行首/行尾字框空白不计入
    可见宽度；图标按缩放后的方形占位计入，文字-图标间隙规则不变。
    """
    spans = []
    x, run, prev = 0.0, "", None
    gap = font.size * _ICON_GAP_EM

    def flush():
        nonlocal x, run
        if run:
            bbox = _text_ink_bbox(font, run)
            if bbox:
                spans.append((x + bbox[0], x + bbox[2]))
            x += font.getlength(run)
            run = ""

    for kind, v, _ in line:
        if kind == "icon":
            flush()
            if prev == "char":
                x += gap
            spans.append((x, x + icon_w[v]))
            x += icon_w[v]
        else:
            if prev == "icon":
                x += gap
            run += v
        prev = kind
    flush()
    if not spans:
        return 0.0, 0.0
    return min(left for left, _ in spans), max(right for _, right in spans)


def _line_width(line: list[tuple[str, str, bool]], font: ImageFont.FreeTypeFont,
                icon_w: dict[str, int]) -> float:
    left, right = _line_metrics(line, font, icon_w)
    return right - left


_NO_LINE_START = set("，。！？；：、,.!?;:%）】》〉」』〕〗〙﹚﹜﹞”’)]}…")
_NO_LINE_END = set("≥≤<>±=+−-×÷（【《〈「『〔〖〘([{")


def _carry_last_unit(current, item):
    """把行尾最后一个可见单元及其后的闭合标点一起借到下一行。"""
    cut = len(current)
    while cut and current[cut - 1][0] == "char" and current[cut - 1][1] in _NO_LINE_START:
        cut -= 1
    if cut:
        cut -= 1
    if cut == 0:
        return None
    return current[:cut], current[cut:] + [item]


def _carry_for_punctuation(current, item):
    if not (item[0] == "char" and item[1] in _NO_LINE_START):
        return None
    return _carry_last_unit(current, item)


def _carry_for_aesthetic(current, item):
    """按高亮完整、符号不留行尾、图标不作行首的优先级尝试借字。"""
    closing = item[0] == "char" and item[1] in _NO_LINE_START
    if current[-1][2] and (item[2] or closing):
        cut = len(current)
        while cut and current[cut - 1][2]:
            cut -= 1
        if cut:
            return current[:cut], current[cut:] + [item]
        return None
    if current[-1][0] == "char" and current[-1][1] in _NO_LINE_END:
        if len(current) > 1:
            return current[:-1], current[-1:] + [item]
        return None
    if item[0] == "icon" and current[-1][0] == "char":
        carried = _carry_last_unit(current, item)
        if carried is not None:
            remaining, moved = carried
            if not (remaining and remaining[-1][2] and moved[0][2]):
                return remaining, moved
    return None


def _break_penalties(lines):
    """自动行边界的美观罚项，元组顺序即优先级；lines 为 item 行列表。"""
    split_highlights = sum(
        bool(left[-1][2] and right[0][2])
        for left, right in zip(lines, lines[1:]) if left and right
    )
    symbol_ends = sum(
        bool(line and line[-1][0] == "char" and line[-1][1] in _NO_LINE_END)
        for line in lines[:-1]
    )
    icon_starts = sum(bool(line and line[0][0] == "icon") for line in lines[1:])
    return split_highlights, symbol_ends, icon_starts


def _normalize_newlines(text: str) -> str:
    """连续 \n 合并为一个换行（显式 \n 是强制断行，但不产生空行）。"""
    return re.sub(r"\n+", "\n", text)


TEXT_LAYOUT_MODES = ("smart", "wrap", "off")
_LEADING_KEYWORDS = frozenset({
    "贯通", "连击", "吸血", "暴击", "不屈", "远程", "直击", "先攻",
    "追猎", "必杀", "屏障", "帷幕", "迅捷", "昂扬", "瞬发", "唯一",
    "不消耗鬼火", "气绝时可用", "仅气绝时可用",
})
_CONDITION_LABELS = ("条件：", "增强：", "响应：", "觉醒：")
_AUTO_BREAK_MIN_FILL = 0.35


def _split_paragraphs(items):
    """按显式换行与内部断点拆段；separators[i] 是第 i 段之后的断点类型。"""
    paragraphs = [[]]
    separators = []
    for item in items:
        if item[0] == "break" or (item[0] == "char" and item[1] == "\n"):
            separators.append(item[1] if item[0] == "break" else "explicit")
            paragraphs.append([])
        else:
            paragraphs[-1].append(item)
    return paragraphs, separators


def _separate_leading_keywords(items):
    """仅处理开头完整、纯能力的句号短句；返回本次渲染用 items 与首行标记。"""
    period = next((i for i, item in enumerate(items)
                   if item[0] == "char" and item[1] == "。"), None)
    if period is None or any(item[0] != "char" or item[1] == "\n"
                             for item in items[:period]):
        return items, False
    visible = "".join(item[1] for item in items[:period])
    if not all(part in _LEADING_KEYWORDS for part in re.split(r"[，、,]", visible)):
        return items, False
    head = list(items[:period])  # 只隐藏首行末尾句号，不改原始输入
    rest = list(items[period + 1:])
    if rest and not (rest[0][0] == "char" and rest[0][1] == "\n"):
        rest.insert(0, ("break", "keyword", False))
    return head + rest, True


def _conditional_breakpoints(items):
    points = []
    for i in range(1, len(items)):
        previous = items[i - 1]
        if previous[0] == "break" or (previous[0] == "char" and previous[1] == "\n"):
            continue
        for label in _CONDITION_LABELS:
            end = i + len(label)
            if all(item[0] == "char" for item in items[i:end]) and "".join(
                    item[1] for item in items[i:end]) == label:
                points.append(i)
                break
        if len(points) == 4:
            break
    return points


def _smart_candidates(items):
    """返回 (候选 items, 条件断行数, 是否关键字首行, 原始候选序号)。"""
    items, keyword_first = _separate_leading_keywords(items)
    points = _conditional_breakpoints(items)
    candidates = []
    for mask in range(1 << len(points)):
        selected = {point for bit, point in enumerate(points) if mask & (1 << bit)}
        candidate = []
        for i, item in enumerate(items):
            if i in selected:
                candidate.append(("break", "auto", False))
            candidate.append(item)
        candidates.append((candidate, mask.bit_count(), keyword_first, mask))
    return candidates


def _line_height(font: ImageFont.FreeTypeFont, gap: float = _LINE_GAP) -> float:
    box = font.getbbox("国Ag")
    return box[3] - box[1] + gap


def _layout_at_size(items: list[tuple[str, str, bool]], font: ImageFont.FreeTypeFont,
                    region: dict, wrap: bool,
                    row_runs: dict | None = None, dy: float = 0,
                    lib: AssetLibrary | None = None, icon_variant: str | None = None,
                    inline_faction_style: int = 1, aesthetic: bool = False):
    """按给定字号在矩形区内排版，成功返回 [(行 item 列表, cx, cy)]，失败返回 None。

    文本块（行数 × 行高）在区域内水平逐行居中、竖直整体居中：
    先定字号与行数，再把文本块中心对齐居中锚点。居中锚点 =
    区域中心 + `center_offset`（缺省 [0,0]，per-type 键）- 临时上移 dy
    （_fit 的自适应尝试用，见 _fit）；区域边界与行宽不变。
    行可用宽度按掩膜墨迹（row_runs）逐行收窄，间距字段 obstacle_gap（缺省 4）。
    内部 auto 断点另要求上一行至少占可用宽度 35%；keyword/显式断行不受此限。
    """
    cx, cy = region["center"]
    ox, oy = region.get("center_offset", [0, 0])
    acx, acy = cx + ox, cy + oy - dy  # 居中锚点（dy=自适应临时上移量）
    half_w, half_h = region["width"] / 2, region["height"] / 2
    y_top, y_bottom = cy - half_h, cy + half_h
    lh = _line_height(font, region.get("_line_gap", _LINE_GAP))
    gap = region.get("obstacle_gap", 4)
    icon_scale = region.get("icon_scale", 1.0)  # 内嵌图标相对文字大小（高=字号×scale）
    icon_w = (_icon_widths(items, font, lib, icon_variant, icon_scale, inline_faction_style)
              if lib is not None else {})

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
        half = _line_width(t, font, icon_w) / 2
        return min(max(acx, span[0] + half), span[1] - half)

    if not wrap:
        span = span_at(acy)
        if span is None or _line_width(items, font, icon_w) > span[1] - span[0]:
            return None
        return [(items, centered_cx(items, acy), acy)]

    paragraphs, separators = _split_paragraphs(items)

    def wrap_from(y: float, improve: bool = False):
        """从行中心 y 起贪心换行，返回行 item 列表；排不下（出底界/被封死）返回 None。"""
        lines: list[list] = []
        current: list = []
        for pi, paragraph in enumerate(paragraphs):
            for item in paragraph:
                trial = current + [item]
                span = span_at(y)
                width = (span[1] - span[0]) if span else 0.0
                if current and _line_width(trial, font, icon_w) > width:
                    if span is None:  # 障碍封死本行：排版失败，交由字号递减/强排兜底
                        return None
                    carried = _carry_for_aesthetic(current, item) if improve else None
                    if carried is None:
                        carried = _carry_for_punctuation(current, item)
                    remaining, current = carried if carried is not None else (current, [item])
                    lines.append(remaining)
                    y += lh
                    if y + lh / 2 > y_bottom:
                        return None
                    if carried is not None:
                        new_span = span_at(y)
                        if (new_span is None or _line_width(current, font, icon_w)
                                > new_span[1] - new_span[0]):
                            return None
                else:
                    current = trial
            if pi < len(paragraphs) - 1 and separators[pi] == "auto":
                span = span_at(y)
                if (span is None or not current
                        or _line_width(current, font, icon_w)
                        < _AUTO_BREAK_MIN_FILL * (span[1] - span[0])):
                    return None
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
        if aesthetic and any(_break_penalties(recentered)):
            improved = wrap_from(y0, improve=True)
            if (improved is not None and len(improved) <= len(recentered)
                    and _break_penalties(improved) < _break_penalties(recentered)):
                recentered = improved
        if len(recentered) == n:
            return [(t, centered_cx(t, y0 + i * lh),
                     y0 + i * lh) for i, t in enumerate(recentered)]
        line_texts = recentered
    return None


def _candidate_score(lines, font, region, lib, icon_variant, inline_faction_style,
                     semantic_breaks, keyword_first, candidate_index):
    """同字号/锚点下：语义断行完整、少行、断行美观优先，再比较行宽均衡。"""
    scored = lines[1:] if keyword_first and len(lines) > 1 else lines
    all_items = [item for line, _, _ in scored for item in line]
    icon_scale = region.get("icon_scale", 1.0)
    icon_w = _icon_widths(all_items, font, lib, icon_variant, icon_scale,
                          inline_faction_style)
    widths = [_line_width(line, font, icon_w) for line, _, _ in scored]
    mean = sum(widths) / len(widths) if widths else 0.0
    imbalance = sum((width - mean) ** 2 for width in widths)
    penalties = _break_penalties([line for line, _, _ in lines])
    return -semantic_breaks, len(lines), *penalties, imbalance, candidate_index


def _fit(items: list[tuple[str, str, bool]], region: dict, lib: AssetLibrary,
         row_runs: dict | None, icon_variant: str | None = None,
         inline_faction_style: int = 1, text_layout: str = "wrap"):
    """最大字号优先；同字号先比语义候选。短文本孤行可缩小至多 2px 来减少行数。"""
    candidates = (_smart_candidates(items) if text_layout == "smart"
                  else [(items, 0, False, 0)])
    max_size, min_size = region["font_range"]
    acx = region["center"][0] + region.get("center_offset", [0, 0])[0]

    def best_at_size(size):
        font = lib.font(region["font"], size)
        max_dy = int(_line_height(font, region.get("_line_gap", _LINE_GAP)) / 2)
        for dy in range(0, max_dy + 1):
            choices = []
            for candidate, semantic_breaks, keyword_first, index in candidates:
                lines = _layout_at_size(candidate, font, region, region["wrap"], row_runs,
                                        dy=dy, lib=lib, icon_variant=icon_variant,
                                        inline_faction_style=inline_faction_style,
                                        aesthetic=text_layout == "smart")
                if lines is not None and all(abs(cx - acx) < 1e-6 for _, cx, _ in lines):
                    score = _candidate_score(
                        lines, font, region, lib, icon_variant, inline_faction_style,
                        semantic_breaks, keyword_first, index)
                    choices.append((score, lines))
            if choices:
                return font, min(choices, key=lambda choice: choice[0])[1]
        return None

    def has_short_last_line(font, lines):
        if not 2 <= len(lines) <= 3:
            return False
        line, _, cy = lines[-1]
        icon_w = _icon_widths(line, font, lib, icon_variant,
                              region.get("icon_scale", 1.0), inline_faction_style)
        cx = region["center"][0]
        span = (cx - region["width"] / 2, cx + region["width"] / 2)
        if row_runs:
            span = clamp_span_by_mask(
                span, cy, _line_height(font, region.get("_line_gap", _LINE_GAP)) / 2,
                row_runs, region.get("obstacle_gap", 4))
        available = span[1] - span[0] if span is not None else 0
        return (available > 0 and _line_width(line, font, icon_w)
                < _AUTO_BREAK_MIN_FILL * available)

    for size in range(max_size, min_size - 1, -1):
        fitted = best_at_size(size)
        if fitted is None:
            continue
        font, lines = fitted
        if text_layout == "smart" and has_short_last_line(font, lines):
            for smaller in range(size - 1, max(min_size, size - 2) - 1, -1):
                compact = best_at_size(smaller)
                if compact is not None and len(compact[1]) < len(lines):
                    return compact
        return fitted
    return None


def _explicit_layout(items, region, lib):
    """off：最大字号、仅显式分行；保留逐行水平居中与文本块竖直居中。"""
    font = lib.font(region["font"], region["font_range"][0])
    paragraphs, _ = _split_paragraphs(items)
    cx, cy = region["center"]
    ox, oy = region.get("center_offset", [0, 0])
    acx, acy = cx + ox, cy + oy
    lh = _line_height(font, region.get("_line_gap", _LINE_GAP))
    y0 = acy - len(paragraphs) * lh / 2 + lh / 2
    return font, [(line, acx, y0 + i * lh) for i, line in enumerate(paragraphs)]


def fit_in_region(text: str, region: dict, lib: AssetLibrary,
                  obstacle_mask: Image.Image | None = None,
                  icon_variant: str | None = None, text_layout: str = "wrap"):
    """按 text_layout 排版，返回 (font, [(行文本, cx, cy)])；适配失败返回 None。

    缺省 wrap 保持通用旧行为；smart 增加卡牌语义候选；off 仅显式分行且不缩字号。
    [[关键字]] 与 #xx 图标标记在排版前剥离（宽度按可见内容计），返回纯文本行。
    """
    if text_layout not in TEXT_LAYOUT_MODES:
        raise ValueError(f"未知 text_layout 模式: {text_layout!r}")
    text = _normalize_newlines(text)
    items = parse_items(text)
    if text_layout == "off":
        fitted = _explicit_layout(items, region, lib)
    else:
        row_runs = mask_row_runs(obstacle_mask) if obstacle_mask is not None else None
        fitted = _fit(items, region, lib, row_runs, icon_variant,
                      text_layout=text_layout)
    if fitted is None:
        return None
    font, lines = fitted
    return font, [(_plain(line), cx, cy) for line, cx, cy in lines]


def draw_region(canvas: Image.Image, lib: AssetLibrary, text: str,
                region: dict, obstacle_mask: Image.Image | None = None,
                fill=TEXT_FILL, keyword_fill=None,
                icon_variant: str | None = None,
                inline_faction_style: int = 1, text_layout: str = "wrap") -> Image.Image:
    """排版并绘制文本。[[关键字]] 段用 keyword_fill 异色绘制（None 时与正文同色）；
    #xx 代码绘制为行内小图标；text_layout 三态口径同 fit_in_region。"""
    if text_layout not in TEXT_LAYOUT_MODES:
        raise ValueError(f"未知 text_layout 模式: {text_layout!r}")
    text = _normalize_newlines(text)
    items = parse_items(text)
    if text_layout == "off":
        fitted = _explicit_layout(items, region, lib)
    else:
        row_runs = mask_row_runs(obstacle_mask) if obstacle_mask is not None else None
        fitted = _fit(items, region, lib, row_runs, icon_variant, inline_faction_style,
                      text_layout)
    if fitted is None:
        font = lib.font(region["font"], region["font_range"][1])
        lines = _layout_at_size(items, font, region, region["wrap"], row_runs,
                                lib=lib, icon_variant=icon_variant,
                                inline_faction_style=inline_faction_style)
        if lines is None:  # 强排兜底：nowrap 超宽，或 wrap 最小字号仍排不下（含障碍封死）
            lines = [(items, region["center"][0], region["center"][1])]
        fitted = (font, lines)
    font, lines = fitted
    out = canvas.copy()
    icon_scale = region.get("icon_scale", 1.0)
    for line, cx, cy in lines:
        _draw_styled_line(out, line, cx, cy, font, fill, keyword_fill, lib,
                          icon_variant, icon_scale, inline_faction_style)
    return out


def _draw_styled_line(out: Image.Image, line: list[tuple[str, str, bool]],
                      cx: float, cy: float, font: ImageFont.FreeTypeFont,
                      fill, keyword_fill, lib: AssetLibrary,
                      icon_variant: str | None, icon_scale: float = 1.0,
                      inline_faction_style: int = 1) -> None:
    """所有行按可见墨迹的水平紧边界居中，字符段用 anchor=lm 绘制；
    关键字段分段异色，图标项就地缩放粘贴（高=字号×icon_scale，竖直中心对齐行中心）。"""
    if not line:
        return
    has_kw = keyword_fill is not None and any(kw for _, _, kw in line)
    has_icon = any(k == "icon" for k, _, _ in line)
    icon_w = (_icon_widths(line, font, lib, icon_variant, icon_scale, inline_faction_style)
              if has_icon else {})
    left, right = _line_metrics(line, font, icon_w)
    x = cx - (left + right) / 2
    draw = ImageDraw.Draw(out)
    if not has_kw and not has_icon:
        draw.text((x, cy), _plain(line), font=font, anchor="lm", fill=fill)
        return
    run, run_kw = "", line[0][2]
    gap = font.size * _ICON_GAP_EM
    prev = None

    def flush():
        nonlocal x, run
        if run:
            draw.text((x, cy), run, font=font, anchor="lm",
                      fill=keyword_fill if run_kw else fill)
            x += font.getlength(run)
            run = ""

    for kind, v, kw in line:
        if kw != run_kw:
            flush()
            run_kw = kw
        if kind == "icon":
            flush()
            if prev == "char":
                x += gap
            w, h = _icon_size(v, font.size, lib, icon_variant, icon_scale,
                              inline_faction_style)
            icon = _icon_image(v, lib, icon_variant, inline_faction_style).resize(
                (w, h), Image.LANCZOS)
            out.paste(icon, (round(x), round(cy - h / 2)), icon)
            x += w
        else:
            if prev == "icon":
                x += gap
            run += v
        prev = kind
    flush()
