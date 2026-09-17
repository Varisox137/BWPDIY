"""卡面渲染管线总装。

合成顺序（自底向上，术语见 docs/terminology.md）：
牌框 frame → 卡图 artwork（蒙版裁切）→ 布局元素（等级标/稀有度双标/派系标/
数值标，由 assets/layout.json 驱动）→ 卡名 → 描述文本 → 页脚。
一期固定：版型 low、框品 norm、等级数字 yellow。
"""

from pathlib import Path

from PIL import Image

from bwpdiy.render.artwork import apply_mask, fit_artwork
from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.badges import render_element, stat_obstacle
from bwpdiy.render.layout import get_type_layout, load_layouts
from bwpdiy.render.text import draw_region, fit_in_region

CARD_SIZE = (512, 512)

TYPE_FRAME_CODE = {
    "式神": "xt",   # 式神卡外观形状同形态牌
    "形态": "xt",
    "战斗": "zd",
    "法术": "fs",
    "幻境": "hj",
    "协战": "xz",
}


def _artwork_ref(card: dict) -> dict:
    images = card.get("artwork", {}).get("images") or [{}]
    ref = dict(images[0])
    ref.setdefault("path", f"{card.get('id', card['name'])}.png")
    ref.setdefault("offset_x", 0)
    ref.setdefault("offset_y", 0)
    ref.setdefault("scale", 1.0)
    return ref


def render_card(card: dict, assets_dir: Path, layout: dict | None = None,
                crop: bool = True) -> Image.Image:
    """渲染单张完整卡面：512×512 画布合成后按 alpha bbox 裁剪返回（竖版 RGBA）。

    crop=False 时跳过裁剪返回完整 512×512（布局预览等需要坐标对齐的场景用）。
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

    type_layout = layout if layout is not None else get_type_layout(load_layouts(Path(assets_dir)), card_type)
    regions = type_layout["text_regions"]
    # 先测卡名宽度（rarity_flank 外移量依据；排不下按 0）
    name_fit = fit_in_region(card["name"], regions["name"], lib)
    ctx = {"name_width": name_fit[0].getlength(card["name"]) if name_fit else 0}
    for elem_name, elem in type_layout["elements"].items():
        canvas = render_element(canvas, lib, elem_name, elem, card, ctx)
    canvas = draw_region(canvas, lib, card["name"], regions["name"])
    if card.get("description") and "desc" in regions:
        obstacles = [stat_obstacle(e) for e in type_layout["elements"].values()
                     if e["kind"] == "stat" and e["field"] in card]
        canvas = draw_region(canvas, lib, card["description"], regions["desc"],
                             obstacles=obstacles)
    if "footer" in regions:
        footer = card.get("footer")
        if not footer:
            footer = f"{card.get('shikigami', card['name'])}-{card_type}"
            if card.get("special_type"):
                footer += f"/{card['special_type']}"
        canvas = draw_region(canvas, lib, footer, regions["footer"])
    # 裁剪掉整画布四周的透明边（bbox 取自合成图 alpha，等级标等溢出元素自然包含）
    if not crop:
        return canvas
    bbox = canvas.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    return canvas.crop(bbox) if bbox else canvas
