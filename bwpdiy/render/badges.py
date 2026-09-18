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

# stat 字段 → stats/ 贴图文件名段（{code}_{field}.png）
_FIELD_BADGE = {
    "power+": "power", "power": "power",
    "health+": "health", "health": "health",
    "shield+": "shield",
    "durability": "intensity",
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
    return img.crop(bbox), (bbox[0] - ox, bbox[1] - oy, bbox[2] - ox, bbox[3] - oy)


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
                   composite: bool = False) -> Image.Image:
    """渲染单个布局元素；渲染条件不满足时原样返回 canvas。

    composite=True 时 stat 图标走 alpha_composite 贴图（源 alpha 保真）：
    仅供 pipeline 的文本避让掩膜采集；实卡绘制用缺省 paste 行为。
    """
    kind = elem["kind"]
    if not elem.get("enabled", True):
        return canvas  # per-type 开关（当前用于 level_badge 整体停用）
    if kind == "level_badge":
        if card.get("level") is None:
            return canvas
        out = _paste_element(canvas, lib.level_base(), elem["pos"],
                             (elem["base_size"], elem["base_size"]))
        if card.get("evolve", False):
            out = _paste_element(out, lib.level_star(), elem["pos"],
                                 (elem["star_size"], elem["star_size"]))
        return _paste_element(out, lib.level_num(card["level"]),
                              elem["pos"], (elem["num_size"], elem["num_size"]))
    if kind == "rarity_flank":
        rarity = card.get("rarity", "R")  # 缺省默认 R
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
        return _paste_element(canvas, lib.faction(color, elem.get("style", 2)),
                              elem["pos"], (elem["size"], elem["size"]))
    if kind == "stat":
        if not stat_rendered(elem, card):
            return canvas
        value = card[elem["field"]]
        code = TYPE_FRAME_CODE[card["type"]]
        badge_field = _FIELD_BADGE[elem["field"]]
        if value < 0 and code == "combat" and elem["field"] == "shield+":
            badge_field = f"fragile_{FRAGILE_VARIANT}"  # 负护甲→破甲，按当前值自动选择
        out = _paste_element(canvas, lib.stat_badge(code, badge_field), elem["pos"],
                             (elem["icon_size"], elem["icon_size"]),
                             composite=composite)
        pos = elem["pos"]
        num_pos = (pos[0] + elem["num_offset"][0], pos[1] + elem["num_offset"][1])
        font = lib.font("name", elem["font_size"])
        stroke_width = elem.get("stroke_width", 2)
        signed = _stat_mode(elem, card) == "signed"
        digits = str(abs(value)) if signed else str(value)
        # 符号贴图（如有）+ 数字作为一个整体块，块的视觉中心对齐 num_pos；
        # sign_offset 为符号相对数字块的微调偏移
        digit_ink = _render_ink(digits, font, stroke_width)
        if digit_ink is None:
            return out
        digit_img = digit_ink[0]
        sign_img = None
        if signed:
            sign_img = _render_sign(lib, "plus" if value >= 0 else "minus",
                                    elem.get("sign_size", round(elem["font_size"] * 0.5)))
        sign_w = sign_img.width if sign_img is not None else 0
        gap = 2 if sign_img is not None else 0
        left = round(num_pos[0] - (sign_w + gap + digit_img.width) / 2)
        out = out.copy()
        if sign_img is not None:
            sx, sy = elem.get("sign_offset", [0, 0])
            out.alpha_composite(sign_img,
                                (left + round(sx),
                                 round(num_pos[1] - sign_img.height / 2 + sy)))
        out.alpha_composite(digit_img,
                            (left + sign_w + gap, round(num_pos[1] - digit_img.height / 2)))
        return out
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
