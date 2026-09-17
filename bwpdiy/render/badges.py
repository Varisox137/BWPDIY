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


def render_element(canvas: Image.Image, lib: AssetLibrary, name: str,
                   elem: dict, card: dict, ctx: dict | None = None) -> Image.Image:
    """渲染单个布局元素；渲染条件不满足时原样返回 canvas。"""
    kind = elem["kind"]
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
            # 整串 mm 锚点会导致视觉错位；数字锚定 num_pos，符号按墨迹中心对齐
            sign, digits = text[0], text[1:]
            draw.text(num_pos, digits, font=font, anchor="mm",
                      fill=(255, 255, 255, 255),
                      stroke_width=2, stroke_fill=(0, 0, 0, 220))
            db = draw.textbbox(num_pos, digits, font=font, anchor="mm", stroke_width=2)
            sb = draw.textbbox((0, 0), sign, font=font, anchor="mm", stroke_width=2)
            sign_pos = (db[0] - 2 - sb[2], (db[1] + db[3]) / 2 - (sb[1] + sb[3]) / 2)
            draw.text(sign_pos, sign, font=font, anchor="mm",
                      fill=(255, 255, 255, 255),
                      stroke_width=2, stroke_fill=(0, 0, 0, 220))
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
