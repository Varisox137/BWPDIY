"""元素渲染：按布局元素定义渲染 等级标/稀有度双标/派系标/数值标/点文本。"""

from PIL import Image, ImageDraw

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.common import paste_centered
from bwpdiy.render.text import TEXT_FILL

FACTION_COLOR = {
    "红莲": "red",
    "苍叶": "green",
    "青岚": "blue",
    "紫岩": "purple",
    # 无相：无派系标，跳过
}


def stat_obstacle(elem: dict) -> tuple[float, float, float, float]:
    """stat 元素的障碍矩形（文本避让用，公式见 Global Constraints）。"""
    x, y = elem["pos"]
    half = elem["icon_size"] / 2
    return (x - half, y - half,
            x + half + abs(elem["num_offset"][0]) + elem["font_size"] * 1.5,
            y + half)


def _paste_element(canvas: Image.Image, img: Image.Image,
                   pos: tuple[float, float],
                   size: tuple[int, int]) -> Image.Image:
    """元素贴图统一口径：裁 alpha bbox 后等比 contain 进 size 框（size=内容可见尺寸）。"""
    bbox = img.getchannel("A").getbbox()
    if bbox:
        img = img.crop(bbox)
    scale = min(size[0] / img.width, size[1] / img.height)
    fit = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    return paste_centered(canvas, img, pos, fit)


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


# 官方卡图正负号明显窄于数字（约半宽）；田氏颜体 +/- 是全宽字形，水平压缩补偿
_SIGN_X_SCALE = 0.55


def render_element(canvas: Image.Image, lib: AssetLibrary, name: str,
                   elem: dict, card: dict, ctx: dict | None = None) -> Image.Image:
    """渲染单个布局元素；渲染条件不满足时原样返回 canvas。"""
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
        return _paste_element(out, lib.level_num("yellow", card["level"]),
                              elem["pos"], (elem["num_size"], elem["num_size"]))
    if kind == "rarity_flank":
        rarity = card.get("rarity", "R")  # 缺省默认 R
        cx, y = elem["pos"]
        name_width = (ctx or {}).get("name_width", 0)
        offset = round(name_width / 2 + elem["gap"] + elem["size"] / 2)
        mark = lib.rarity(rarity)
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
        field = elem["field"]
        if field not in card:
            return canvas
        value = card[field]
        icon = elem["icon"]
        if value < 0 and elem.get("icon_neg"):
            icon = elem["icon_neg"]  # 负值换贴图（护甲→破甲）
        out = _paste_element(canvas, lib.icon(icon, "l"), elem["pos"],
                             (elem["icon_size"], elem["icon_size"]))
        pos = elem["pos"]
        num_pos = (pos[0] + elem["num_offset"][0], pos[1] + elem["num_offset"][1])
        font = lib.font("name", elem["font_size"])
        out = out.copy()
        draw = ImageDraw.Draw(out)
        text = f"{value:+d}" if elem.get("signed") else str(value)
        if elem.get("signed"):
            # 符号与数字分别绘制：同一字体中 +/- 墨迹中心与数字不一致，
            # 整串 mm 锚点会导致视觉错位；数字锚定 num_pos（与不带号逐像素一致），
            # 符号离屏渲染取真墨迹、水平压至半宽后按墨迹中心对齐贴入
            sign, digits = text[0], text[1:]
            draw.text(num_pos, digits, font=font, anchor="mm",
                      fill=(255, 255, 255, 255),
                      stroke_width=2, stroke_fill=(0, 0, 0, 220))
            digit_ink = _render_ink(digits, font)
            sign_ink = _render_ink(sign, font)
            if digit_ink is not None and sign_ink is not None:
                db = digit_ink[1]
                sign_img = sign_ink[0]
                sign_img = sign_img.resize(
                    (max(1, round(sign_img.width * _SIGN_X_SCALE)), sign_img.height),
                    Image.LANCZOS)
                sx = round(num_pos[0] + db[0] - 2 - sign_img.width)
                sy = round(num_pos[1] + (db[1] + db[3]) / 2 - sign_img.height / 2)
                out.alpha_composite(sign_img, (sx, sy))
            return out
        draw.text(num_pos, text, font=font, anchor="mm",
                  fill=(255, 255, 255, 255),
                  stroke_width=2, stroke_fill=(0, 0, 0, 220))
        return out
    if kind == "text":
        # 点文本（卡名/脚注）：以 pos 为中心水平居中单行，不换行不做多边形排版
        text = card.get(name)
        if not text:
            return canvas
        out = canvas.copy()
        draw = ImageDraw.Draw(out)
        draw.text(tuple(elem["pos"]), str(text),
                  font=lib.font(elem.get("font", "name"), elem["font_size"]),
                  anchor="mm", fill=TEXT_FILL)
        return out
    raise ValueError(f"未知元素 kind: {kind}")
