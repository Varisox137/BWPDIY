"""图标层：等级标 / 稀有度标 / 派系标 / 数值标。"""

from PIL import Image, ImageDraw

from bwpdiy.render import layout
from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.common import paste_centered

# 数值标位置：键名 → 锚点；（键名以 + 结尾表示加成，显示带正负号）
_STAT_POSITIONS = {
    "power": layout.STAT_LEFT_POS,
    "health": layout.STAT_RIGHT_POS,
    "power+": layout.STAT_LEFT_POS,
    "shield+": layout.STAT_RIGHT_POS,
    "durability": layout.STAT_CENTER_POS,
}


def add_level_badge(canvas: Image.Image, lib: AssetLibrary, level: int,
                    evolve: bool = False, color: str = "brown") -> Image.Image:
    """等级标三层叠加：底座 → 觉醒星（仅觉醒）→ 等级数字。"""
    out = paste_centered(canvas, lib.level_base(), layout.LEVEL_POS, layout.LEVEL_BASE_SIZE)
    if evolve:
        out = paste_centered(out, lib.level_star(), layout.LEVEL_POS, layout.LEVEL_STAR_SIZE)
    return paste_centered(out, lib.level_num(color, level), layout.LEVEL_POS, layout.LEVEL_NUM_SIZE)


def add_rarity(canvas: Image.Image, lib: AssetLibrary, rarity: str) -> Image.Image:
    return paste_centered(canvas, lib.rarity(rarity), layout.RARITY_POS, layout.RARITY_SIZE)


def add_faction(canvas: Image.Image, lib: AssetLibrary, faction_color: str) -> Image.Image:
    return paste_centered(canvas, lib.faction(faction_color), layout.FACTION_POS, layout.FACTION_SIZE)


def add_stats(canvas: Image.Image, lib: AssetLibrary,
              stats: list[tuple[str, int]]) -> Image.Image:
    """数值标：白字黑边。键名以 + 结尾的显示正负号（+1 / -1），其余显示绝对值。"""
    out = canvas.copy()
    draw = ImageDraw.Draw(out)
    font = lib.font("name", layout.STAT_FONT_SIZE)
    for key, value in stats:
        pos = _STAT_POSITIONS[key]
        text = f"{value:+d}" if key.endswith("+") else str(value)
        draw.text(pos, text, font=font, anchor="mm",
                  fill=(255, 255, 255, 255), stroke_width=2,
                  stroke_fill=(0, 0, 0, 220))
    return out
