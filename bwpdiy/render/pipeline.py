"""卡面渲染管线总装。

合成顺序（自底向上，术语见 docs/terminology.md）：
卡图 artwork（fit 至 512 画布）→ 牌框 frame（在上，卡图区透明无需蒙版）→
轮廓裁剪（删去牌框实际形状之外的所有像素，框缘包围的卡图窗不受影响）→
布局元素（等级标/稀有度双标/派系标/数值标/卡名/脚注点文本，由 assets/layout.json
驱动，探出框缘的元素在轮廓裁剪之后绘制、不受影响）→ 描述文本 →
最终导出按整卡 tightest alpha bbox 裁剪后等比缩放至高 512（上下顶格、
左右居中留白）贴回 512×512；crop=False 布局预览模式返回 512 全画布。
框品：card["frame_variant"]（缺省 norm），协战恒 norm。
"""

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from bwpdiy.render.artwork import fit_artwork
from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.badges import TYPE_FRAME_CODE, render_element, stat_rendered
from bwpdiy.render.layout import get_type_layout, load_layouts
from bwpdiy.render.text import FRAME_TEXT_FILL, draw_region

CARD_SIZE = (512, 512)

# 牌框 alpha 清理阈值：alpha < 此值的像素视为杂点删去（PSD 导出在框缘外
# 留有低透明度散点，会挂住卡图造成出框残留）；同时影响轮廓裁剪的框形判定。
# 192 为激进档（用户定稿，后续可能手修牌框资源）：削掉边缘 1-2px 抗锯齿，
# 实测不伤内部装饰（差异全部位为边缘抗锯齿线）。
FRAME_ALPHA_THRESHOLD = 192


def _clean_frame(frame: Image.Image) -> Image.Image:
    """牌框 alpha 清理：alpha < FRAME_ALPHA_THRESHOLD 的像素删去（PSD 导出在框缘
    外/卡图窗内留有低透明度散点，会挂住卡图造成出框残留）。返回副本，不改原图。"""
    if FRAME_ALPHA_THRESHOLD <= 0:
        return frame
    frame = frame.copy()
    frame.putalpha(frame.getchannel("A").point(
        lambda v: 0 if v < FRAME_ALPHA_THRESHOLD else v))
    return frame


def _outside_frame_mask(frame: Image.Image) -> Image.Image:
    """L 掩膜（255=牌框实际形状之外）：框 alpha==0 且与画布边缘连通的区域。

    卡图窗虽 alpha==0 但被框缘完整包围、与画布边缘不连通，不受影响；
    框缘抗锯齿半透明像素（alpha>0）视为框体保留。
    """
    mask = frame.getchannel("A").point(lambda v: 255 if v == 0 else 0)
    w, h = mask.size
    px = mask.load()
    seeds = ([(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
             + [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)])
    for s in seeds:
        if px[s[0], s[1]] == 255:
            ImageDraw.floodfill(mask, s, 128, thresh=0)
    return mask.point(lambda v: 255 if v == 128 else 0)


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
    """渲染单张完整卡面：512×512 RGBA，卡面内容上下顶格、左右居中留白（竖版）。

    crop=False 时跳过导出适配，返回 512 全画布合成结果（布局预览等需要
    坐标对齐的场景用）。
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

    frame = _clean_frame(lib.frame(code, variant))
    ref = _artwork_ref(card)
    art_path = Path(ref["path"])
    if not art_path.is_absolute():
        art_path = Path(card.get("_base_dir", ".")) / art_path
    if not art_path.is_file():
        raise FileNotFoundError(f"卡图缺失: {art_path}")
    art = Image.open(art_path).convert("RGBA")
    art = fit_artwork(art, CARD_SIZE, ref["offset_x"], ref["offset_y"], ref["scale"])
    canvas = Image.alpha_composite(art, frame)  # 牌框在上：卡图区透明，无需蒙版
    # 轮廓裁剪：删去牌框实际形状之外的所有像素（矩形 bbox 裁剪会残留框形外卡图）
    outside = _outside_frame_mask(frame)
    if outside.getbbox() is not None:
        keep = outside.point(lambda v: 0 if v == 255 else 255)
        canvas.putalpha(ImageChops.multiply(canvas.getchannel("A"), keep))

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
    # 导出：tightest alpha bbox 裁剪 → 等比缩放至高 512（上下顶格、左右居中留白）贴回 512×512
    if not crop:
        return canvas
    bbox = canvas.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    if not bbox:
        return canvas
    body = canvas.crop(bbox)
    scale = CARD_SIZE[1] / body.height
    if body.width * scale > CARD_SIZE[0]:  # 宽溢出则退为按宽适配（上下留白）
        scale = CARD_SIZE[0] / body.width
    nw = max(1, round(body.width * scale))
    nh = max(1, round(body.height * scale))
    body = body.resize((nw, nh), Image.LANCZOS)
    out = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    out.paste(body, ((CARD_SIZE[0] - nw) // 2, (CARD_SIZE[1] - nh) // 2))
    return out
