"""卡面渲染管线总装。

合成顺序（自底向上，术语见 docs/terminology.md）：
底层卡图 artwork（fit 至 512 画布，按外轮廓裁剪：框 alpha≥128 区+被包围
卡图窗构成的外轮廓向内腐蚀 2px，框缘半透明带下不再有卡图、杜绝洇色）→
牌框 frame 叠加在上（素材为紧致裁剪图，等比缩放至高 512、左右居中贴回 512 画布）→
框内静态部分（卡名/稀有度双标/脚注点文本）→ 框上叠加（等级标/派系标/stat 角标图标）→
描述文本（避让掩膜取 stat 图标+数值全量墨迹的碰撞轮廓）→
stat 数值层（符号+数字，压在描述文本之上）→
最终导出按整卡 tightest alpha bbox 裁剪后**原尺寸直接返回**（高 512 顶格、
宽按内容，无 512 画布留白）；crop=False 返回 512 全画布（管线内部分层断言用）。
布局元素由 assets/layout.json 驱动，探出框缘的元素不受影响。
框品：card["frame_variant"]（缺省 norm），协战恒 norm。
"""

import copy
import json
from collections import OrderedDict
from pathlib import Path
import threading

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from bwpdiy.render.artwork import (
    ARTWORK_MAX_PIXELS, artwork_ref, fit_artwork_cached, load_card_artwork)

__all__ = ["ARTWORK_MAX_PIXELS", "TYPE_FRAME_CODE", "render_card"]
from bwpdiy.render.assets import get_library
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


def _normalize_frame(frame: Image.Image, info: dict | None = None) -> Image.Image:
    """牌框归一化到 512×512 画布：等比缩放至高 512（上下顶格），左右居中。

    牌框素材为手工修整的紧致裁剪图，各框尺寸不一；布局坐标以归一化牌框左缘
    为原点（卡面空间），传入 info dict 时回填 anchor=(左, 上) 居中偏移，
    供卡面空间 → 512 画布坐标平移（anchor[1] 恒 0——框恒顶格）。
    """
    if frame.size == CARD_SIZE:
        if info is not None:
            info["anchor"] = (0, 0)
        return frame
    scale = CARD_SIZE[1] / frame.height
    if frame.width * scale > CARD_SIZE[0]:  # 宽溢出兜底：按宽适配（正常框不会触发）
        scale = CARD_SIZE[0] / frame.width
    nw = max(1, round(frame.width * scale))
    nh = max(1, round(frame.height * scale))
    frame = frame.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    pos = ((CARD_SIZE[0] - nw) // 2, (CARD_SIZE[1] - nh) // 2)
    if info is not None:
        info["anchor"] = pos
    canvas.paste(frame, pos, frame)
    return canvas


def _to_canvas_coords(type_layout: dict, anchor_x: int) -> dict:
    """布局坐标（卡面空间，x 原点 = 归一化牌框左缘）→ 512 合成画布坐标。

    仅平移绝对 x：elements.*.pos / elements.*.fragile_pos 与
    text_regions.*.center；偏移/尺寸类字段（num_offset/center_offset/width 等）
    不动。返回深拷贝，不改调用方数据。
    """
    tl = copy.deepcopy(type_layout)
    for elem in (tl.get("elements") or {}).values():
        if isinstance(elem, dict):
            for key in ("pos", "fragile_pos"):
                p = elem.get(key)
                if isinstance(p, list) and len(p) == 2 and isinstance(p[0], (int, float)):
                    p[0] += anchor_x
    for region in (tl.get("text_regions") or {}).values():
        if isinstance(region, dict):
            c = region.get("center")
            if isinstance(c, list) and len(c) == 2 and isinstance(c[0], (int, float)):
                c[0] += anchor_x
    return tl


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


STATIC_OVERLAY_CACHE_MAX_ENTRIES = 8
_STATIC_OVERLAY_CACHE = OrderedDict()
_STATIC_OVERLAY_LOCK = threading.RLock()


def _static_overlay_key(assets_dir: Path, type_layout: dict, card: dict):
    if "_duo" in card:
        return None
    static_card = {k: v for k, v in card.items() if k not in ("artwork", "layout")}
    try:
        layout_key = json.dumps(type_layout, sort_keys=True, ensure_ascii=False,
                                separators=(",", ":"), allow_nan=False)
        card_key = json.dumps(static_card, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return None
    return str(Path(assets_dir).resolve()), layout_key, card_key


class _RecordingDraw:
    def __init__(self, image: Image.Image, tape: list, mode: str | None):
        self._tape = tape
        self._draw = ImageDraw.Draw(image, mode)

    def __getattr__(self, name):
        return getattr(self._draw, name)

    def text(self, xy, text, *args, **kwargs):
        self._draw.text(xy, text, *args, **kwargs)
        self._tape.append(("text", xy, text, args, kwargs))


class _RecordingCanvas:
    def __init__(self, image: Image.Image, tape: list):
        self._image = image
        self._tape = tape

    def __getattr__(self, name):
        return getattr(self._image, name)

    def copy(self):
        return _RecordingCanvas(self._image.copy(), self._tape)

    def getdraw(self, mode=None):
        return _RecordingDraw(self._image, self._tape, mode)

    def paste(self, im, box=None, mask=None):
        self._image.paste(im, box, mask)
        self._tape.append(("paste", im, box, mask))

    def alpha_composite(self, im, dest=(0, 0), source=(0, 0)):
        self._image.alpha_composite(im, dest, source)
        self._tape.append(("alpha_composite", im, dest, source))


def _draw_static(canvas, type_layout: dict, card: dict, lib, variant: str):
    elements = type_layout["elements"]
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
                             keyword_fill=kw_fill, icon_variant=variant)
    # 数值层最后画：描述文本避让数值（掩膜含数值墨迹），数值压在文本之上
    for elem_name, elem in stat_elems:
        canvas = render_element(canvas, lib, elem_name, elem, card, ctx,
                                stat_part="number")
    return canvas


def _build_static_layers(type_layout: dict, card: dict, lib, variant: str) -> list:
    tape = []
    canvas = _RecordingCanvas(Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0)), tape)
    _draw_static(canvas, type_layout, card, lib, variant)
    return tape


def _replay_static_layers(canvas: Image.Image, layers: list) -> Image.Image:
    for command in layers:
        kind = command[0]
        if kind == "paste":
            _, source, box, mask = command
            canvas.paste(source, box, mask)
        elif kind == "alpha_composite":
            _, source, dest, source_box = command
            canvas.alpha_composite(source, dest, source_box)
        else:
            _, xy, text, args, kwargs = command
            ImageDraw.Draw(canvas).text(xy, text, *args, **kwargs)
    return canvas


def _get_static_layers(assets_dir: Path, type_layout: dict, card: dict,
                       lib, variant: str) -> list | None:
    key = _static_overlay_key(assets_dir, type_layout, card)
    if key is None:
        return None
    if STATIC_OVERLAY_CACHE_MAX_ENTRIES > 0:
        with _STATIC_OVERLAY_LOCK:
            layers = _STATIC_OVERLAY_CACHE.get(key)
            if layers is not None:
                _STATIC_OVERLAY_CACHE.move_to_end(key)
                return layers
    layers = _build_static_layers(type_layout, card, lib, variant)
    if STATIC_OVERLAY_CACHE_MAX_ENTRIES > 0:
        with _STATIC_OVERLAY_LOCK:
            _STATIC_OVERLAY_CACHE[key] = layers
            _STATIC_OVERLAY_CACHE.move_to_end(key)
            while len(_STATIC_OVERLAY_CACHE) > STATIC_OVERLAY_CACHE_MAX_ENTRIES:
                _STATIC_OVERLAY_CACHE.popitem(last=False)
    return layers


def render_card(card: dict, assets_dir: Path, layout: dict | None = None,
                crop: bool = True, info: dict | None = None) -> Image.Image:
    """渲染单张完整卡面。

    crop=True（默认，导出/预览）：按整卡 tightest alpha bbox 裁剪后原尺寸
    直接返回（RGBA，高 512 顶格、宽按内容，无 512 画布留白）；传入 info dict
    时回填 crop_origin（卡面空间坐标，与布局坐标同系）与 anchor_x（卡面空间
    x 原点在本框品 512 画布中的位置），供布局页覆盖层换算。
    布局坐标为卡面空间：x 原点 = 归一化牌框左缘（随框品宽度动态计算，
    元素与牌框胶着、换框品不跑位；探出框左缘的元素 x 为负），y 原点 = 画布顶。
    crop=False：跳过导出裁剪，返回 512 全画布合成结果（管线内部分层断言用）。
    缺资源/缺字段抛明确异常（FileNotFoundError/KeyError/ValueError），调用方兜底。
    """
    card_type = card["type"]
    if card_type not in TYPE_FRAME_CODE:
        raise ValueError(f"未知卡牌类型: {card_type}")
    code = TYPE_FRAME_CODE[card_type]
    variant = card.get("frame_variant", "norm")
    if card_type == "协战":
        variant = "norm"  # 协战框仅 norm 一种框品
    lib = get_library(assets_dir)

    finfo: dict = {}
    frame = _normalize_frame(lib.frame(code, variant), finfo)
    anchor_x = finfo["anchor"][0]  # 卡面空间 x 原点（本框品归一化牌框左缘）
    type_layout = layout if layout is not None else get_type_layout(load_layouts(Path(assets_dir)), card_type)
    # 布局坐标卡面空间 → 512 画布（锚点随框品：元素与牌框左缘胶着，换框品不跑位）
    type_layout = _to_canvas_coords(type_layout, anchor_x)
    card = dict(card)
    # 脚注兜底：式神名-类型[/子类型]；协战为 式神1×式神2-协战（缺任一式神只标 协战）；
    # 中立牌（无所属式神）只标 类型[/子类型]（式神卡自身无所属式神字段，回退卡名）
    if not card.get("footer"):
        if card_type == "协战":
            s1, s2 = card.get("shikigami1"), card.get("shikigami2")
            card["footer"] = f"{s1}×{s2}-协战" if s1 and s2 else "协战"
        else:
            shikigami = card.get("shikigami") or (card["name"] if card_type == "式神" else None)
            card["footer"] = f"{shikigami}-{card_type}" if shikigami else card_type
            if card.get("special_type"):
                card["footer"] += f"/{card['special_type']}"

    ref = artwork_ref(card)
    orig_size, art = load_card_artwork(card, lib)
    art = fit_artwork_cached(art, CARD_SIZE, ref["offset_x"], ref["offset_y"],
                             ref["scale"], cover_base=orig_size)
    # 卡图按轮廓预裁剪（框实心区内缩 2px），框缘半透明带下无卡图、不洇色
    art.putalpha(ImageChops.multiply(art.getchannel("A"), _art_clip_contour(frame)))
    canvas = Image.alpha_composite(art, frame)  # 牌框在上：卡图区透明，无需蒙版
    layers = _get_static_layers(assets_dir, type_layout, card, lib, variant)
    if layers is None:
        canvas = _draw_static(canvas, type_layout, card, lib, variant)
    else:
        canvas = _replay_static_layers(canvas, layers)
    # 导出：按整卡 tightest alpha bbox 裁剪后原尺寸直接返回（无 512 画布留白）
    if not crop:
        return canvas
    bbox = canvas.getchannel("A").point(lambda v: 255 if v > 10 else 0).getbbox()
    if info is not None:  # 裁剪原点报卡面空间（与布局坐标同系，探出框左缘元素可为负）
        info["anchor_x"] = anchor_x
        info["crop_origin"] = ((bbox[0] - anchor_x, bbox[1]) if bbox
                               else (-anchor_x, 0))
    return canvas.crop(bbox) if bbox else canvas
