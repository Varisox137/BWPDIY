"""元素渲染：按布局元素定义渲染 等级标/稀有度双标/派系标/数值标/点文本。"""

from PIL import Image, ImageDraw

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.common import paste_centered
from bwpdiy.render.text import FRAME_TEXT_FILL

# 卡牌类型 → 牌框/角标资源代码（web/app.py 经 pipeline 转引此表，勿改名）
TYPE_FRAME_CODE = {
    "式神": "form",   # 式神卡外观形状同形态牌
    "形态": "form",
    "战斗": "combat",
    "法术": "spell",
    "幻境": "field",
    "协战": "reinforce",
}

FACTION_COLOR = {
    "红莲": "red",
    "苍叶": "green",
    "青岚": "blue",
    "紫岩": "purple",
    # 无相：无派系标，跳过
}

# 战斗牌护甲负值换破甲贴图：stats/combat_fragile_{1,2}.png，默认深红变体 2
FRAGILE_VARIANT = 2

# stat 字段 → stats/ 贴图文件 stem（stats/{stem}.png；力量/生命全类型共用同一资源）
_FIELD_BADGE = {
    "power+": "power", "power": "power",
    "health+": "health", "health": "health",
    "shield+": "combat_shield",
    "durability": "field_intensity",
}


def _frame_variant(card: dict) -> str:
    """框品：协战恒 norm（无其他框品资源），其余读 card["frame_variant"]。"""
    if card.get("type") == "协战":
        return "norm"
    return card.get("frame_variant", "norm")


def _paste_element(canvas: Image.Image, img: Image.Image,
                   pos: tuple[float, float],
                   size: tuple[int, int],
                   composite: bool = False) -> Image.Image:
    """元素贴图统一口径：裁 alpha bbox 后等比 contain 进 size 框（size=内容可见尺寸）。"""
    bbox = img.getchannel("A").getbbox()
    if bbox:
        img = img.crop(bbox)
    scale = min(size[0] / img.width, size[1] / img.height)
    fit = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    return paste_centered(canvas, img, pos, fit, composite=composite)


# 数值变色（游戏内采样 examples/colored_num_ref.png + 用户调校）：白=常态，红=debuff/受伤
# （大红顶色、向下过渡橙红），绿=buff（近似均匀青绿），紫=中毒（竖直渐变上深下亮）
STAT_COLORS = {
    "red": ((224, 44, 22), (245, 116, 48)),
    "green": ((8, 213, 173), (35, 197, 170)),
    "purple": ((105, 12, 120), (223, 97, 235)),
}


def _vertical_gradient(size: tuple[int, int], top: tuple[int, int, int],
                       bottom: tuple[int, int, int]) -> Image.Image:
    """竖直线性渐变 RGB 图（顶→底）。"""
    w, h = size
    grad = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        grad.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
    return grad.resize((w, h))


def _tint(img: Image.Image, top: tuple[int, int, int],
          bottom: tuple[int, int, int]) -> Image.Image:
    """亮色填充重着色为竖直渐变、深色描边原样保留（亮度软掩膜过渡）。"""
    lum = img.convert("L").point(lambda v: min(255, max(0, (v - 60) * 3)))
    grad = _vertical_gradient(img.size, top, bottom)
    out = Image.composite(grad, img.convert("RGB"), lum).convert("RGBA")
    out.putalpha(img.getchannel("A"))
    return out


_tint_sign = _tint  # 符号贴图与白字数字同一口径：填充换渐变、描边保留


def _render_ink(text: str, font, stroke_width: int = 2):
    """离屏渲染文本（白字黑描边），返回 (裁到墨迹的 RGBA 图, 相对 mm 锚点的真墨迹 bbox)。

    不能用 textbbox 的预测口径：田氏颜体 `-` 字形轮廓含不产墨的延伸点，
    预测 bbox 底边虚报（报 y20..36 实际墨迹 y20..24），按预测中心对齐必错位。
    """
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    predicted = probe.textbbox((0, 0), text, font=font, anchor="mm",
                               stroke_width=stroke_width)
    pad = 8
    ox = -predicted[0] + pad
    oy = -predicted[1] + pad
    img = Image.new("RGBA", (predicted[2] - predicted[0] + pad * 2,
                             predicted[3] - predicted[1] + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.text((ox, oy), text, font=font, anchor="mm",
              fill=(255, 255, 255, 255), stroke_width=stroke_width,
              stroke_fill=(0, 0, 0, 220))
    bbox = img.getchannel("A").getbbox()
    if bbox is None:
        return None
    img = img.crop(bbox)
    return img, (bbox[0] - ox, bbox[1] - oy, bbox[2] - ox, bbox[3] - oy)


_DIGIT_GAP = 3  # 相邻数字墨迹的最小水平间距 px


def _row_ink_extents(img: Image.Image) -> list[tuple[int, int] | None]:
    """每行墨迹的 (左缘 x, 右缘 x)；无墨迹行为 None。"""
    a = img.getchannel("A").load()
    w, h = img.size
    rows = []
    for y in range(h):
        lo = None
        for x in range(w):
            if a[x, y] > 0:
                lo = x
                break
        if lo is None:
            rows.append(None)
            continue
        hi = lo
        for x in range(w - 1, lo, -1):
            if a[x, y] > 0:
                hi = x
                break
        rows.append((lo, hi))
    return rows


def _render_digits(text: str, font, stroke_width: int,
                   color: str | None = None) -> Image.Image | None:
    """数字串渲染：逐字离屏渲染后横向拼接，变色在拼接后整体施加（渐变以整串墨迹计）。

    竖直：各字墨迹中点在同一水平线（不同字高取中点对齐）。
    水平：不按字形 box 等距排（「41」这类窄字会嫌稀），按相邻字墨迹的
    最小水平距离 = _DIGIT_GAP 约束排放（逐行区间求最大可行左移量）。
    """
    parts = []
    for ch in text:
        ink = _render_ink(ch, font, stroke_width)
        if ink is None:
            return None
        parts.append(ink[0])
    if len(parts) == 1:
        img = parts[0]
        return _tint(img, *STAT_COLORS[color]) if color is not None else img
    h = max(p.height for p in parts)
    offs = [(h - p.height) // 2 for p in parts]
    acc = Image.new("RGBA", (parts[0].width, h), (0, 0, 0, 0))
    acc.alpha_composite(parts[0], (0, offs[0]))
    acc_ext = _row_ink_extents(acc)
    for p, off_y in zip(parts[1:], offs[1:]):
        p_ext = _row_ink_extents(p)
        x = None
        for y in range(h):
            py = y - off_y
            if 0 <= py < p.height and acc_ext[y] and p_ext[py]:
                req = acc_ext[y][1] + _DIGIT_GAP - p_ext[py][0]
                x = req if x is None else max(x, req)
        if x is None:
            x = acc.width + _DIGIT_GAP  # 逐行无重叠（理论上不会发生）：退回 box 等距
        x = max(0, x)
        w_new = max(acc.width, x + p.width)
        grown = Image.new("RGBA", (w_new, h), (0, 0, 0, 0))
        grown.alpha_composite(acc, (0, 0))
        grown.alpha_composite(p, (x, off_y))
        acc = grown
        acc_ext = _row_ink_extents(acc)
    return _tint(acc, *STAT_COLORS[color]) if color is not None else acc


# stat 适用矩阵（用户裁定唯一口径，渲染/文本避让/GUI 输入同表）：
# (type, field) -> "signed"（带 ± 号，0 不绘制：战斗、法术觉醒）/ "plain"（无符号，0 照常绘制）
# 表外组合即使 card 带该字段也不绘制；协战/非觉醒法术无任何 stat
_STAT_MATRIX = {
    ("式神", "power"): "plain", ("式神", "health"): "plain",
    ("战斗", "power+"): "signed", ("战斗", "shield+"): "signed",
    ("法术", "power+"): "signed", ("法术", "health+"): "signed",  # 仅 evolve=true
    ("形态", "power"): "plain", ("形态", "health"): "plain",
    ("幻境", "durability"): "plain",
}


def _stat_mode(elem: dict, card: dict) -> str | None:
    """(type, field) 在适用矩阵中的符号模式；表外/非觉醒法术返回 None。"""
    ctype = card.get("type")
    if ctype == "法术" and not card.get("evolve", False):
        return None
    return _STAT_MATRIX.get((ctype, elem["field"]))


def stat_rendered(elem: dict, card: dict) -> bool:
    """stat 元素是否实际渲染（按适用矩阵：表外组合/字段缺失跳过，signed 模式 0 值跳过）。"""
    mode = _stat_mode(elem, card)
    if mode is None or elem["field"] not in card:
        return False
    return not (card[elem["field"]] == 0 and mode == "signed")


def _render_sign(lib: AssetLibrary, name: str, size: int) -> Image.Image:
    """正负号贴图：裁 alpha bbox 后等比 contain 进 size 见方框（与元素贴图同口径）。"""
    img = lib.sign(name)
    bbox = img.getchannel("A").getbbox()
    if bbox:
        img = img.crop(bbox)
    scale = min(size / img.width, size / img.height)
    return img.resize((max(1, round(img.width * scale)),
                       max(1, round(img.height * scale))),
                      Image.Resampling.LANCZOS)


def render_element(canvas: Image.Image, lib: AssetLibrary, name: str,
                   elem: dict, card: dict, ctx: dict | None = None,
                   composite: bool = False, stat_part: str | None = None) -> Image.Image:
    """渲染单个布局元素；渲染条件不满足时原样返回 canvas。

    composite=True 时 stat 图标走 alpha_composite 贴图（源 alpha 保真）：
    仅供 pipeline 的文本避让掩膜采集；实卡绘制用缺省 paste 行为。
    stat_part：stat 元素分层绘制——"icon" 只画角标图标、"number" 只画符号+数字、
    None 两者都画（缺省）。pipeline 按 框上叠加图标层 / 描述后数值层 分两遍调用。
    """
    kind = elem["kind"]
    if not elem.get("enabled", True):
        return canvas  # per-type 开关（当前用于 level_badge 整体停用）
    if kind == "level_badge":
        if card.get("level") is None:
            return canvas
        pos = elem["pos"]
        out = _paste_element(canvas, lib.level_base(), pos,
                             (elem["base_size"], elem["base_size"]))
        if card.get("evolve", False):
            sx, sy = elem.get("star_offset", [0, 0])  # 觉醒星相对底座偏移
            out = _paste_element(out, lib.level_star(), (pos[0] + sx, pos[1] + sy),
                                 (elem["star_size"], elem["star_size"]))
        nx, ny = elem.get("num_offset", [0, 0])  # 勾玉相对底座偏移
        return _paste_element(out, lib.level_num(card["level"],
                                                 card.get("level_color", "yellow")),
                              (pos[0] + nx, pos[1] + ny),
                              (elem["num_size"], elem["num_size"]))
    if kind == "rarity_flank":
        rarity = card.get("rarity")  # 缺省 = 无稀有度（衍生牌口径），不绘制双标
        if rarity not in ("N", "R", "SR", "SSR"):
            return canvas
        cx, y = elem["pos"]
        name_width = (ctx or {}).get("name_width", 0)
        # gap=默认半间距（短名静态固定 pos±gap）；仅卡名超宽时按与卡名缘固定 margin 外移
        offset = round(max(elem["gap"], name_width / 2 + elem.get("margin", 8)))
        variant = "reinforce" if card.get("type") == "协战" else _frame_variant(card)
        mark = lib.rarity(rarity, variant)
        out = _paste_element(canvas, mark, (cx - offset, y),
                             (elem["size"], elem["size"]))
        # 偶数尺寸右标右移 1px：与左标保持关于 cx 的像素级镜像
        return _paste_element(out, mark, (cx + offset + 1, y),
                              (elem["size"], elem["size"]))
    if kind == "faction":
        color = FACTION_COLOR.get(card.get("faction", ""))
        if color is None:
            return canvas
        # 派系样式：卡面 faction_style（1-3）优先，缺省用布局元素的 style（默认 2）
        style = card.get("faction_style", elem.get("style", 2))
        return _paste_element(canvas, lib.faction(color, style),
                              elem["pos"], (elem["size"], elem["size"]))
    if kind == "stat":
        if not stat_rendered(elem, card):
            return canvas
        value = card[elem["field"]]
        field = elem["field"]
        # 破甲（战斗负护甲）四键分离：坐标/图标大小/数字偏移/符号偏移读 fragile_* 键，
        # 缺省回退基础键；字号/描边/符号尺寸/group_offset 与护甲共享，不为破甲单设
        fragile = (card["type"] == "战斗" and field == "shield+" and value < 0)
        if fragile:
            # 破甲贴图变体可配（fragile_variant 1/2，缺省 2）
            stem = f"combat_fragile_{elem.get('fragile_variant', FRAGILE_VARIANT)}"
            pos = tuple(elem.get("fragile_pos", elem["pos"]))
            icon_size = elem.get("fragile_icon_size", elem["icon_size"])
            num_offset = elem.get("fragile_num_offset", elem["num_offset"])
            sign_offset = elem.get("fragile_sign_offset", elem.get("sign_offset", [0, 0]))
        else:
            stem = _FIELD_BADGE[field]
            pos = tuple(elem["pos"])
            icon_size = elem["icon_size"]
            num_offset = elem["num_offset"]
            sign_offset = elem.get("sign_offset", [0, 0])
        if stat_part != "number":
            out = _paste_element(canvas, lib.stat_badge(stem), pos,
                                 (icon_size, icon_size),
                                 composite=composite)
        else:
            out = canvas  # 数值层不带图标（图标层已画）
        if stat_part == "icon":
            return out
        # group_offset：符号+数字整体相对角标的额外偏移（per-type 键，四类带符号
        # 数值可各自微调；缺省 [0,0]），叠加在跨类型通用的 num_offset 之上
        gx, gy = elem.get("group_offset", [0, 0])
        num_pos = (pos[0] + num_offset[0] + gx,
                   pos[1] + num_offset[1] + gy)
        font = lib.font("name", elem["font_size"])
        stroke_width = elem.get("stroke_width", 2)
        signed = _stat_mode(elem, card) == "signed"
        color = card.get(f"{field}_color")  # 数值变色：red/green/purple，缺省白
        digits = str(abs(value)) if signed else str(value)
        # 符号贴图（如有）+ 数字作为一个整体块，块的视觉中心对齐 num_pos；
        # sign_offset 为符号相对数字块的微调偏移
        digit_img = _render_digits(digits, font, stroke_width, color)
        if digit_img is None:
            return out
        sign_img = None
        if signed:
            # 加号/减号尺寸分开可调（sign_size 为旧数据回退）
            sign_name = "plus" if value >= 0 else "minus"
            sign_size = elem.get(f"sign_size_{sign_name}",
                                 elem.get("sign_size", round(elem["font_size"] * 0.5)))
            sign_img = _render_sign(lib, sign_name, sign_size)
            if color is not None:
                sign_img = _tint_sign(sign_img, *STAT_COLORS[color])
        sign_w = sign_img.width if sign_img is not None else 0
        gap = 2 if sign_img is not None else 0
        left = round(num_pos[0] - (sign_w + gap + digit_img.width) / 2)
        out = out.copy()
        if sign_img is not None:
            sx, sy = sign_offset
            out.alpha_composite(sign_img,
                                (left + round(sx),
                                 round(num_pos[1] - sign_img.height / 2 + sy)))
        out.alpha_composite(digit_img,
                            (left + sign_w + gap, round(num_pos[1] - digit_img.height / 2)))
        return out
    if kind == "duo_frame":
        # 协战双式神框：卡面 duo_frame: true 且类型为协战时绘制（默认不绘制）；
        # 头像数据 card["_duo"] 由 web 层按所属式神注入（内部键，不进 schema）
        if card.get("type") != "协战" or not card.get("duo_frame"):
            return canvas
        from bwpdiy.render.duo import render_duo_frame
        return render_duo_frame(canvas, lib, elem, card)
    if kind == "text":
        # 点文本（卡名/脚注）：以 pos 为中心水平居中单行，不换行不做多边形排版
        text = card.get(name)
        if not text:
            return canvas
        fills = FRAME_TEXT_FILL.get(_frame_variant(card), FRAME_TEXT_FILL["norm"])
        out = canvas.copy()
        draw = ImageDraw.Draw(out)
        draw.text(tuple(elem["pos"]), str(text),
                  font=lib.font(elem.get("font", "name"), elem["font_size"]),
                  anchor="mm", fill=fills.get(name, fills["desc"]))
        return out
    raise ValueError(f"未知元素 kind: {kind}")
