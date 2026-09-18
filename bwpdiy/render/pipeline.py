"""卡面渲染管线总装。

合成顺序（自底向上，术语见 docs/terminology.md）：
卡图 artwork（fit 至 512 画布）→ 牌框 frame（在上，卡图区透明无需蒙版）→
裁到框 alpha bbox（去框外卡图）→ 布局元素（等级标/稀有度双标/派系标/
数值标/卡名/脚注点文本，由 assets/layout.json 驱动）→ 描述文本 →
最终导出按整卡合成结果 alpha bbox 裁剪（探出框缘的元素包含在内；
crop=False 布局预览模式返回 512 全画布）。
框品：card["frame_variant"]（缺省 norm），协战恒 norm。
"""

from pathlib import Path

from PIL import Image

from bwpdiy.render.artwork import fit_artwork
from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.badges import TYPE_FRAME_CODE, render_element, stat_rendered
from bwpdiy.render.layout import get_type_layout, load_layouts
from bwpdiy.render.text import FRAME_TEXT_FILL, draw_region

CARD_SIZE = (512, 512)


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
    variant = card.get("frame_variant", "norm")
    if card_type == "协战":
        variant = "norm"  # 协战框仅 norm 一种框品
    lib = AssetLibrary(assets_dir)

    frame = lib.frame(code, variant)
    ref = _artwork_ref(card)
    art_path = Path(ref["path"])
    if not art_path.is_absolute():
        art_path = Path(card.get("_base_dir", ".")) / art_path
    if not art_path.is_file():
        raise FileNotFoundError(f"卡图缺失: {art_path}")
    art = Image.open(art_path).convert("RGBA")
    art = fit_artwork(art, CARD_SIZE, ref["offset_x"], ref["offset_y"], ref["scale"])
    canvas = Image.alpha_composite(art, frame)  # 牌框在上：卡图区透明，无需蒙版
    # 裁到框 alpha bbox（去框外卡图），贴回 512 画布原位（布局坐标不变）
    fbbox = frame.getchannel("A").getbbox()
    if fbbox and fbbox != (0, 0, *CARD_SIZE):
        body = canvas.crop(fbbox)
        canvas = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
        canvas.paste(body, fbbox[:2])

    type_layout = layout if layout is not None else get_type_layout(load_layouts(Path(assets_dir)), card_type)
    elements = type_layout["elements"]
    card = dict(card)
    # 脚注兜底：式神名-类型[/子类型]（footer 点元素直接读 card["footer"]）
    if not card.get("footer"):
        card["footer"] = f"{card.get('shikigami', card['name'])}-{card_type}"
        if card.get("special_type"):
            card["footer"] += f"/{card['special_type']}"
    # 先测卡名宽度（rarity_flank 外移量依据；name 点元素缺失按 0）
    name_width = 0
    name_elem = elements.get("name")
    if name_elem and name_elem.get("kind") == "text":
        name_font = lib.font(name_elem.get("font", "name"), name_elem["font_size"])
        name_width = name_font.getlength(card["name"])
    ctx = {"name_width": name_width}
    for elem_name, elem in elements.items():
        canvas = render_element(canvas, lib, elem_name, elem, card, ctx)
    regions = type_layout["text_regions"]
    if card.get("description") and "desc" in regions:
        # 文本避让掩膜：实际渲染的 stat 元素在透明层再渲染一份，取 alpha 真墨迹
        stat_elems = [e for e in elements.values()
                      if e["kind"] == "stat" and e.get("enabled", True)
                      and stat_rendered(e, card)]
        obstacle_mask = None
        if stat_elems:
            layer = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
            for i, e in enumerate(stat_elems):
                # composite=True：掩膜采集走 alpha_composite，图标源 alpha 保真
                # （默认 paste 在透明层上平方 alpha，抗锯齿淡边缘会被掩膜阈值丢弃）
                layer = render_element(layer, lib, f"stat_{i}", e, card, ctx,
                                       composite=True)
            obstacle_mask = layer.getchannel("A")
        desc_fill = FRAME_TEXT_FILL.get(variant, FRAME_TEXT_FILL["norm"])["desc"]
        canvas = draw_region(canvas, lib, card["description"], regions["desc"],
                             obstacle_mask=obstacle_mask, fill=desc_fill)
    # 裁剪掉整画布四周的透明边（bbox 取自合成图 alpha，探出框缘的元素自然包含）
    if not crop:
        return canvas
    bbox = canvas.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    return canvas.crop(bbox) if bbox else canvas
