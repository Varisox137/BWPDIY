"""卡面渲染管线总装。

合成顺序（自底向上，术语见 docs/terminology.md）：
底层卡图 artwork（fit 至 512 画布，按外轮廓裁剪：框 alpha≥128 区+被包围
卡图窗构成的外轮廓向内腐蚀 2px，框缘半透明带下不再有卡图、杜绝洇色）→
牌框 frame 叠加在上（素材为紧致裁剪图，等比缩放至高 512、左右居中贴回 512 画布）→
框内静态部分（卡名/稀有度双标/脚注点文本）→ 框上叠加（等级标/派系标/stat 角标图标）→
描述文本（避让掩膜取 stat 图标+数值全量墨迹的碰撞轮廓）→
stat 数值层（符号+数字，压在描述文本之上）→
最终导出按整卡 tightest alpha bbox 裁剪后等比缩放至高 512（上下顶格、
左右居中留白）贴回 512×512；crop=False 布局预览模式返回 512 全画布。
布局元素由 assets/layout.json 驱动，探出框缘的元素不受影响。
框品：card["frame_variant"]（缺省 norm），协战恒 norm。
"""

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from bwpdiy.render.artwork import ARTWORK_MAX_PIXELS, fit_artwork

__all__ = ["ARTWORK_MAX_PIXELS", "TYPE_FRAME_CODE", "render_card"]
from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.badges import TYPE_FRAME_CODE, render_element, stat_rendered
from bwpdiy.render.layout import get_type_layout, load_layouts
from bwpdiy.render.text import FRAME_KEYWORD_FILL, FRAME_TEXT_FILL, draw_region

CARD_SIZE = (512, 512)

# 卡图裁剪轮廓：牌框 alpha≥128 的实心区向内腐蚀 2px 作为卡图可绘制区——
# 框缘半透明带（alpha<128 与最外 2px）之下没有卡图，杜绝卡图洇出框缘。
FRAME_CONTOUR_ALPHA = 128
FRAME_CONTOUR_ERODE = 2  # px

# 文本避让掩膜：角标等障碍元素的碰撞轮廓按 alpha≥阈值考察（仿牌框阈值预处理，
# 不用原始 alpha box——抗锯齿淡边缘不算墨迹，避免文本无谓避让）。
OBSTACLE_ALPHA = 128


def _normalize_frame(frame: Image.Image) -> Image.Image:
    """牌框归一化到 512×512 画布：等比缩放至高 512（上下顶格），左右居中。

    牌框素材为手工修整的紧致裁剪图，各框尺寸不一；布局坐标以 512 画布为准。
    """
    if frame.size == CARD_SIZE:
        return frame
    scale = CARD_SIZE[1] / frame.height
    if frame.width * scale > CARD_SIZE[0]:  # 宽溢出兜底：按宽适配（正常框不会触发）
        scale = CARD_SIZE[0] / frame.width
    nw = max(1, round(frame.width * scale))
    nh = max(1, round(frame.height * scale))
    frame = frame.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    canvas.paste(frame, ((CARD_SIZE[0] - nw) // 2, (CARD_SIZE[1] - nh) // 2), frame)
    return canvas


def _art_clip_contour(frame: Image.Image) -> Image.Image:
    """L 掩膜（255=卡图可绘制区）：牌框外轮廓向内腐蚀 FRAME_CONTOUR_ERODE px。

    外轮廓 = 框 alpha≥FRAME_CONTOUR_ALPHA 实心区 + 被框缘完整包围的卡图窗
    （对 alpha<阈值区域从画布四边 flood fill，够不到的地方即框形内部）。
    """
    mask = frame.getchannel("A").point(
        lambda v: 255 if v < FRAME_CONTOUR_ALPHA else 0)
    w, h = mask.size
    px = mask.load()
    seeds = ([(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
             + [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)])
    for s in seeds:
        if px[s[0], s[1]] == 255:
            ImageDraw.floodfill(mask, s, 128, thresh=0)
    # 128=框外 → 其余（实心区+卡图窗）为框形内部
    shape = mask.point(lambda v: 0 if v == 128 else 255)
    if FRAME_CONTOUR_ERODE > 0:
        shape = shape.filter(ImageFilter.MinFilter(2 * FRAME_CONTOUR_ERODE + 1))
    return shape


def _artwork_ref(card: dict) -> dict:
    images = card.get("artwork", {}).get("images") or [{}]
    ref = dict(images[0])
    ref.setdefault("path", f"{card.get('id', card['name'])}.png")
    ref.setdefault("offset_x", 0)
    ref.setdefault("offset_y", 0)
    ref.setdefault("scale", 1.0)
    ref.setdefault("rotate", 0)
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

    frame = _normalize_frame(lib.frame(code, variant))
    ref = _artwork_ref(card)
    art_path = Path(ref["path"])
    base_dir = Path(card.get("_base_dir", "."))
    if not art_path.is_absolute():
        art_path = base_dir / art_path
    # 卡图必须位于基准目录内：拒绝目录外绝对路径与 .. 越界
    # （预览接口可被远程触发时，防本机任意图片被读取外泄）
    try:
        art_path.resolve().relative_to(base_dir.resolve())
    except ValueError:
        raise ValueError(f"卡图路径越出基准目录: {ref['path']}") from None
    if not art_path.is_file():
        raise FileNotFoundError(f"卡图缺失: {art_path}")
    # 加载即缓存（键含 mtime 与旋转角）：绕中心旋转并扩展画布，缩放/偏移对缓存图进行
    art = lib.artwork(art_path, ref["rotate"])
    art = fit_artwork(art, CARD_SIZE, ref["offset_x"], ref["offset_y"], ref["scale"])
    # 卡图按轮廓预裁剪（框实心区内缩 2px），框缘半透明带下无卡图、不洇色
    art.putalpha(ImageChops.multiply(art.getchannel("A"), _art_clip_contour(frame)))
    canvas = Image.alpha_composite(art, frame)  # 牌框在上：卡图区透明，无需蒙版

    type_layout = layout if layout is not None else get_type_layout(load_layouts(Path(assets_dir)), card_type)
    elements = type_layout["elements"]
    card = dict(card)
    # 脚注兜底：式神名-类型[/子类型]；中立牌（无所属式神）只标 类型[/子类型]
    # （式神卡自身无所属式神字段，回退卡名）
    if not card.get("footer"):
        shikigami = card.get("shikigami") or (card["name"] if card_type == "式神" else None)
        card["footer"] = f"{shikigami}-{card_type}" if shikigami else card_type
        if card.get("special_type"):
            card["footer"] += f"/{card['special_type']}"
    # 先测卡名宽度（rarity_flank 外移量依据；name 点元素缺失按 0）
    name_width = 0
    name_elem = elements.get("name")
    if name_elem and name_elem.get("kind") == "text":
        name_font = lib.font(name_elem.get("font", "name"), name_elem["font_size"])
        name_width = name_font.getlength(card["name"])
    ctx = {"name_width": name_width}
    # 分层渲染（自底向上）：框内静态（卡名/稀有度双标/脚注点文本）→
    # 框上叠加（等级标/派系标/stat 角标图标）→ 描述文本 → stat 数值（符号+数字）
    _STATIC = ("text", "rarity_flank")
    for elem_name, elem in elements.items():
        if elem["kind"] in _STATIC:
            canvas = render_element(canvas, lib, elem_name, elem, card, ctx)
    stat_elems = []
    for elem_name, elem in elements.items():
        if elem["kind"] in _STATIC:
            continue
        if elem["kind"] == "stat":
            stat_elems.append((elem_name, elem))
            canvas = render_element(canvas, lib, elem_name, elem, card, ctx,
                                    stat_part="icon")
        else:
            canvas = render_element(canvas, lib, elem_name, elem, card, ctx)
    regions = type_layout["text_regions"]
    if card.get("description") and "desc" in regions:
        # 文本避让掩膜：实际渲染的 stat 元素（图标+数值全量）在透明层再渲染一份，
        # 取 alpha≥OBSTACLE_ALPHA 的碰撞轮廓（非原始 box，仿牌框阈值预处理）
        rendered_stats = [e for _, e in stat_elems
                          if e.get("enabled", True) and stat_rendered(e, card)]
        obstacle_mask = None
        if rendered_stats:
            layer = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
            for i, e in enumerate(rendered_stats):
                # composite=True：掩膜采集走 alpha_composite，图标源 alpha 保真
                # （默认 paste 在透明层上平方 alpha，抗锯齿淡边缘会被掩膜阈值丢弃）
                layer = render_element(layer, lib, f"stat_{i}", e, card, ctx,
                                       composite=True)
            obstacle_mask = layer.getchannel("A").point(
                lambda v: 255 if v >= OBSTACLE_ALPHA else 0)
        desc_fill = FRAME_TEXT_FILL.get(variant, FRAME_TEXT_FILL["norm"])["desc"]
        kw_fill = FRAME_KEYWORD_FILL.get(variant, FRAME_KEYWORD_FILL["norm"])
        canvas = draw_region(canvas, lib, card["description"], regions["desc"],
                             obstacle_mask=obstacle_mask, fill=desc_fill,
                             keyword_fill=kw_fill)
    # 数值层最后画：描述文本避让数值（掩膜含数值墨迹），数值压在文本之上
    for elem_name, elem in stat_elems:
        canvas = render_element(canvas, lib, elem_name, elem, card, ctx,
                                stat_part="number")
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
