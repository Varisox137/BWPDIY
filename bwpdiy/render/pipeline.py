"""卡面渲染管线总装。

合成顺序（自底向上，术语见 docs/terminology.md）：
牌框 frame → 卡图 artwork（蒙版裁切）→ 等级标 → 稀有度标 → 派系标 →
数值标 → 卡名 → 描述文本。
一期固定：版型 low、框品 norm、等级数字 brown。
"""

from pathlib import Path

from PIL import Image

from bwpdiy.render import layout
from bwpdiy.render.artwork import apply_mask, fit_artwork
from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.badges import (add_faction, add_level_badge, add_rarity,
                                  add_stats)
from bwpdiy.render.text import draw_description, draw_name

CARD_SIZE = (512, 512)

TYPE_FRAME_CODE = {
    "式神": "xt",   # 式神卡外观形状同形态牌
    "形态": "xt",
    "战斗": "zd",
    "法术": "fs",
    "幻境": "hj",
    "协战": "xz",
}

FACTION_COLOR = {
    "红莲": "red",
    "苍叶": "green",
    "青岚": "blue",
    "紫岩": "purple",
    # 无相：无派系标，跳过
}

_STAT_KEYS = ("power", "health", "power+", "shield+", "durability")


def _artwork_ref(card: dict) -> dict:
    images = card.get("artwork", {}).get("images") or [{}]
    ref = dict(images[0])
    ref.setdefault("path", f"{card.get('id', card['name'])}.png")
    ref.setdefault("offset_x", 0)
    ref.setdefault("offset_y", 0)
    ref.setdefault("scale", 1.0)
    return ref


def render_card(card: dict, assets_dir: Path) -> Image.Image:
    """渲染单张完整卡面：512×512 画布合成后按 alpha bbox 裁剪返回（竖版 RGBA）。

    缺资源/缺字段抛明确异常（FileNotFoundError/KeyError/ValueError），调用方兜底。
    """
    card_type = card["type"]
    if card_type not in TYPE_FRAME_CODE:
        raise ValueError(f"未知卡牌类型: {card_type}")
    code = TYPE_FRAME_CODE[card_type]
    lib = AssetLibrary(assets_dir)

    frame = lib.frame(code)  # 一期固定 norm/low
    ref = _artwork_ref(card)
    art_path = Path(ref["path"])
    if not art_path.is_absolute():
        art_path = Path(card.get("_base_dir", ".")) / art_path
    if not art_path.is_file():
        raise FileNotFoundError(f"卡图缺失: {art_path}")
    art = Image.open(art_path).convert("RGBA")
    art = fit_artwork(art, CARD_SIZE, ref["offset_x"], ref["offset_y"], ref["scale"])
    art = apply_mask(art, lib.mask(code))
    canvas = Image.alpha_composite(frame, art)

    if card.get("level") is not None:
        canvas = add_level_badge(canvas, lib, card["level"],
                                 evolve=card.get("evolve", False))
    if card.get("rarity"):
        canvas = add_rarity(canvas, lib, card["rarity"])
    faction = card.get("faction")
    if faction and faction in FACTION_COLOR:
        canvas = add_faction(canvas, lib, FACTION_COLOR[faction])
    stats = [(k, card[k]) for k in _STAT_KEYS if k in card]
    if stats:
        canvas = add_stats(canvas, lib, stats)

    canvas = draw_name(canvas, lib, card["name"])
    if card.get("description"):
        canvas = draw_description(canvas, lib, card["description"])
    # 裁剪掉整画布四周的透明边（bbox 取自合成图 alpha，等级标等溢出元素自然包含）
    bbox = canvas.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    return canvas.crop(bbox) if bbox else canvas
