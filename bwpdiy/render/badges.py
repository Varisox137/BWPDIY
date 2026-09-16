"""元素渲染：按布局元素定义渲染 等级标/稀有度双标/派系标/数值标。"""

from PIL import Image, ImageDraw

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.common import paste_centered

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


def render_element(canvas: Image.Image, lib: AssetLibrary, name: str,
                   elem: dict, card: dict, ctx: dict | None = None) -> Image.Image:
    """渲染单个布局元素；渲染条件不满足时原样返回 canvas。"""
    kind = elem["kind"]
    if kind == "level_badge":
        if card.get("level") is None:
            return canvas
        out = paste_centered(canvas, lib.level_base(), elem["pos"],
                             (elem["base_size"], elem["base_size"]))
        if card.get("evolve", False):
            out = paste_centered(out, lib.level_star(), elem["pos"],
                                 (elem["star_size"], elem["star_size"]))
        return paste_centered(out, lib.level_num("yellow", card["level"]),
                              elem["pos"], (elem["num_size"], elem["num_size"]))
    if kind == "rarity_flank":
        rarity = card.get("rarity", "R")  # 缺省默认 R
        cx, y = elem["pos"]
        name_width = (ctx or {}).get("name_width", 0)
        offset = round(name_width / 2 + elem["gap"] + elem["size"] / 2)
        mark = lib.rarity(rarity)
        # 稀有度标素材带透明边，裁至内容 bbox 使 size 即可见尺寸
        bbox = mark.getchannel("A").getbbox()
        if bbox:
            mark = mark.crop(bbox)
        out = paste_centered(canvas, mark, (cx - offset, y),
                             (elem["size"], elem["size"]))
        # 偶数尺寸右标右移 1px：覆盖右缘包含端点，与左标保持等距间隙
        return paste_centered(out, mark, (cx + offset + 1, y),
                              (elem["size"], elem["size"]))
    if kind == "faction":
        color = FACTION_COLOR.get(card.get("faction", ""))
        if color is None:
            return canvas
        return paste_centered(canvas, lib.faction(color, elem.get("style", 2)),
                              elem["pos"], (elem["size"], elem["size"]))
    if kind == "stat":
        field = elem["field"]
        if field not in card:
            return canvas
        value = card[field]
        icon = elem["icon"]
        if value < 0 and elem.get("icon_neg"):
            icon = elem["icon_neg"]  # 负值换贴图（护甲→破甲）
        out = paste_centered(canvas, lib.icon(icon, "l"), elem["pos"],
                             (elem["icon_size"], elem["icon_size"]))
        text = f"{value:+d}" if elem.get("signed") else str(value)
        pos = elem["pos"]
        num_pos = (pos[0] + elem["num_offset"][0], pos[1] + elem["num_offset"][1])
        out = out.copy()
        draw = ImageDraw.Draw(out)
        draw.text(num_pos, text, font=lib.font("name", elem["font_size"]),
                  anchor="mm", fill=(255, 255, 255, 255),
                  stroke_width=2, stroke_fill=(0, 0, 0, 220))
        return out
    raise ValueError(f"未知元素 kind: {kind}")
