"""对局式神小卡的独立纯 PIL 渲染器。"""

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from bwpdiy.render.artwork import artwork_ref, fit_artwork, load_card_artwork
from bwpdiy.render.assets import AssetLibrary, get_library
from bwpdiy.render.badges import _paste_element, _render_digits

ENTITY_SIZE = (64, 96)
LEVEL_COLORS = {"yellow", "cyan", "purple", "red", "blue", "brown"}

_DEFAULT_LAYOUT = {
    "elements": {
        "level": {
            "kind": "level_badge", "pos": [32, 88], "base_size": 18,
            "num_size": 14, "num_offset": [0, 0],
        },
        "power": {
            "kind": "stat", "field": "power", "pos": [10, 82],
            "icon_size": 16, "num_offset": [0, 10], "font_size": 14,
            "stroke_width": 1,
        },
        "health": {
            "kind": "stat", "field": "health", "pos": [54, 82],
            "icon_size": 16, "num_offset": [0, 10], "font_size": 14,
            "stroke_width": 1,
        },
        "combat_power": {
            "kind": "stat", "field": "combat_power", "pos": [10, 62],
            "icon_size": 14, "num_offset": [0, 9], "font_size": 12,
            "stroke_width": 1,
        },
        "shield": {
            "kind": "stat", "field": "shield", "pos": [54, 62],
            "icon_size": 14, "num_offset": [0, 9], "font_size": 12,
            "stroke_width": 1,
        },
    },
}


def entity_eligible(card: dict) -> bool:
    return card.get("type") in {"式神", "形态"} or card.get("evolve") is True


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_entity_state(state: dict) -> dict:
    if not isinstance(state, dict):
        raise ValueError("对局状态必须是映射")
    normalized = {
        "level": state.get("level", 1),
        "level_color": state.get("level_color", "yellow"),
        "power": state.get("power", 0),
        "health": state.get("health", 0),
        "combat_power": state.get("combat_power", 0),
        "shield": state.get("shield", 0),
        "art_scale": state.get("art_scale", 1.0),
    }
    for field in ("power", "health", "combat_power", "shield", "level"):
        if not _is_int(normalized[field]):
            raise ValueError(f"{field} 必须是整数")
    if normalized["power"] < 0 or normalized["health"] < 0:
        raise ValueError("power/health 必须是非负整数")
    if normalized["level"] not in (1, 2, 3):
        raise ValueError("level 必须是 1、2 或 3")
    color = normalized["level_color"]
    if not isinstance(color, str) or color not in LEVEL_COLORS:
        raise ValueError("level_color 非法")
    scale = normalized["art_scale"]
    if isinstance(scale, bool) or not isinstance(scale, (int, float)):
        raise ValueError("art_scale 必须是有限正数")
    try:
        scale = float(scale)
    except OverflowError:
        raise ValueError("art_scale 必须是有限正数") from None
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("art_scale 必须是有限正数")
    normalized["art_scale"] = scale
    return normalized


def _card_state(card: dict, state: dict) -> dict:
    normalized = validate_entity_state(state)
    level = card.get("level")
    if "level" not in state:
        normalized["level"] = level if _is_int(level) and level in (1, 2, 3) else 1
    color = card.get("level_color")
    if "level_color" not in state:
        normalized["level_color"] = (
            color if isinstance(color, str) and color in LEVEL_COLORS else "yellow")
    return normalized


def _render_level(canvas: Image.Image, lib: AssetLibrary, elem: dict,
                  state: dict) -> Image.Image:
    if not elem.get("enabled", True):
        return canvas
    pos = elem["pos"]
    out = _paste_element(canvas, lib.level_base(), pos,
                         (elem["base_size"], elem["base_size"]))
    nx, ny = elem.get("num_offset", [0, 0])
    return _paste_element(
        out, lib.level_num(state["level"], state["level_color"]),
        (pos[0] + nx, pos[1] + ny), (elem["num_size"], elem["num_size"]))


def _stat_icon(lib: AssetLibrary, field: str, value: int) -> Image.Image:
    if field == "combat_power":
        return lib.icon("combat_power" if value > 0 else "weak")
    if field == "shield":
        return lib.stat_badge("combat_shield" if value > 0 else "combat_fragile_2")
    return lib.stat_badge(field)


def _render_stat(canvas: Image.Image, lib: AssetLibrary, elem: dict,
                 state: dict) -> Image.Image:
    if not elem.get("enabled", True):
        return canvas
    field = elem["field"]
    value = state[field]
    if field in ("combat_power", "shield") and value == 0:
        return canvas
    pos = elem["pos"]
    out = _paste_element(canvas, _stat_icon(lib, field, value), pos,
                         (elem["icon_size"], elem["icon_size"]))
    digits = _render_digits(str(abs(value)), lib.font("name", elem["font_size"]),
                            elem.get("stroke_width", 1))
    if digits is None:
        return out
    nx, ny = elem.get("num_offset", [0, 0])
    center_x = pos[0] + nx
    center_y = pos[1] + ny
    out = out.copy()
    out.alpha_composite(digits, (round(center_x - digits.width / 2),
                                 round(center_y - digits.height / 2)))
    return out


def _render_frame(art: Image.Image) -> Image.Image:
    canvas = Image.new("RGBA", ENTITY_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((1, 1, 62, 94), radius=8,
                           fill=(18, 23, 31, 238))
    mask = Image.new("L", ENTITY_SIZE, 0)
    ImageDraw.Draw(mask).rounded_rectangle((4, 4, 59, 91), radius=6, fill=255)
    layer = Image.new("RGBA", ENTITY_SIZE, (0, 0, 0, 0))
    layer.alpha_composite(art, (4, 4))
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    canvas = Image.alpha_composite(canvas, layer)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((1, 1, 62, 94), radius=8,
                           outline=(198, 164, 93, 255), width=1)
    draw.rounded_rectangle((2, 2, 61, 93), radius=7,
                           outline=(55, 39, 25, 255), width=1)
    draw.rounded_rectangle((4, 4, 59, 91), radius=6,
                           outline=(235, 214, 153, 220), width=1)
    return canvas


def render_entity(card: dict, state: dict, assets_dir: Path,
                  layout: dict | None = None, crop: bool = True,
                  info: dict | None = None) -> Image.Image:
    if not entity_eligible(card):
        raise ValueError("该卡牌类型不支持对局式神渲染")
    state = _card_state(card, state)
    lib = get_library(assets_dir)
    ref = artwork_ref(card)
    original, rotated = load_card_artwork(card, lib)
    inner_size = (56, 88)
    scale_xy = inner_size[0] / 512
    art = fit_artwork(rotated, inner_size,
                      ref["offset_x"] * scale_xy, ref["offset_y"] * scale_xy,
                      state["art_scale"], cover_base=original)
    canvas = _render_frame(art)
    elements = (layout if layout is not None else _DEFAULT_LAYOUT)["elements"]
    if "level" in elements:
        canvas = _render_level(canvas, lib, elements["level"], state)
    for field in ("power", "health", "combat_power", "shield"):
        if field in elements:
            canvas = _render_stat(canvas, lib, elements[field], state)
    if not crop:
        return canvas
    bbox = canvas.getchannel("A").point(lambda value: 255 if value > 10 else 0).getbbox()
    if info is not None:
        info["crop_origin"] = bbox[:2] if bbox else (0, 0)
    return canvas.crop(bbox) if bbox else canvas


__all__ = ["entity_eligible", "render_entity", "validate_entity_state"]
