"""对局式神小卡的独立纯 PIL 渲染器。"""

import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from bwpdiy.render.artwork import (
    ARTWORK_MAX_PIXELS, artwork_ref, fit_artwork, load_card_artwork)
from bwpdiy.render.assets import AssetLibrary, get_library
from bwpdiy.render.badges import TYPE_FRAME_CODE, _paste_element, _render_digits
from bwpdiy.render.pipeline import _normalize_frame

ENTITY_SIZE = (96, 144)
LEVEL_COLORS = {"yellow", "cyan", "purple", "red", "blue", "brown"}

_DEFAULT_LAYOUT = {
    "version": 2,
    "art_window": {
        "center": [48, 72], "width": 84, "height": 132,
        "frame_center": True, "offset_y": 0,
    },
    "elements": {
        "level": {
            "kind": "level_badge", "pos": [48, 132], "base_size": 27,
            "num_size": 21, "num_offset": [0, 0],
        },
        "power": {
            "kind": "stat", "field": "power", "pos": [15, 123],
            "icon_size": 24, "num_offset": [0, 6], "font_size": 21,
            "stroke_width": 1.5,
        },
        "health": {
            "kind": "stat", "field": "health", "pos": [81, 123],
            "icon_size": 24, "num_offset": [0, 6], "font_size": 21,
            "stroke_width": 1.5,
        },
        "combat_power": {
            "kind": "stat", "field": "combat_power", "pos": [15, 93],
            "icon_size": 21, "num_offset": [0, 5], "font_size": 18,
            "stroke_width": 1.5,
        },
        "shield": {
            "kind": "stat", "field": "shield", "pos": [81, 93],
            "icon_size": 21, "num_offset": [0, 5], "font_size": 18,
            "stroke_width": 1.5,
        },
    },
}


def entity_eligible(card: dict) -> bool:
    return card.get("type") in {"式神", "形态"} or card.get("evolve") is True


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _finite_number(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def validate_entity_art_window(window: dict) -> None:
    if not isinstance(window, dict):
        raise ValueError("卡图窗必须是对象")
    center = window.get("center")
    if (not isinstance(center, (list, tuple)) or len(center) != 2
            or not all(_finite_number(value) for value in center)):
        raise ValueError("卡图窗 center 必须是两个有限数值")
    width, height = window.get("width"), window.get("height")
    if not all(_finite_number(value) and value > 0 for value in (width, height)):
        raise ValueError("卡图窗宽高必须是有限正数")
    if width * height > ARTWORK_MAX_PIXELS:
        raise ValueError("卡图窗面积超像素上限")
    inner_width, inner_height = max(1, round(width)), max(1, round(height))
    if inner_width * inner_height > ARTWORK_MAX_PIXELS:
        raise ValueError("卡图窗面积超像素上限")
    if not isinstance(window.get("frame_center"), bool):
        raise ValueError("卡图窗 frame_center 必须是布尔值")
    if not _finite_number(window.get("offset_y")):
        raise ValueError("卡图窗 offset_y 必须是有限数值")


@lru_cache(maxsize=16)
def _analyze_frame_art_window(width: int, height: int, alpha: bytes) -> tuple[float, float]:
    seen = bytearray(width * height)
    best = None
    for start, value in enumerate(alpha):
        if value >= 128 or seen[start]:
            continue
        stack = [start]
        seen[start] = 1
        area = 0
        left, top, right, bottom = width, height, -1, -1
        enclosed = True
        while stack:
            index = stack.pop()
            y, x = divmod(index, width)
            area += 1
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
            if x == 0 or y == 0 or x == width - 1 or y == height - 1:
                enclosed = False
            for neighbor in (index - 1, index + 1, index - width, index + width):
                if neighbor < 0 or neighbor >= width * height or seen[neighbor]:
                    continue
                ny, nx = divmod(neighbor, width)
                if abs(nx - x) + abs(ny - y) != 1 or alpha[neighbor] >= 128:
                    continue
                seen[neighbor] = 1
                stack.append(neighbor)
        if enclosed and (best is None or area > best[0]):
            best = (area, left, top, right, bottom)
    if best is None:
        raise ValueError("牌框缺少封闭卡图窗")
    _, left, top, right, bottom = best
    return ((left + right + 1) / 2, (top + bottom + 1) / 2)


def frame_art_window_center(frame: Image.Image) -> tuple[float, float]:
    alpha = frame.convert("RGBA").getchannel("A")
    return _analyze_frame_art_window(frame.width, frame.height, alpha.tobytes())


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
                            round(elem.get("stroke_width", 1)))
    if digits is None:
        return out
    nx, ny = elem.get("num_offset", [0, 0])
    center_x = pos[0] + nx
    center_y = pos[1] + ny
    out = out.copy()
    out.alpha_composite(digits, (round(center_x - digits.width / 2),
                                 round(center_y - digits.height / 2)))
    return out


def _render_frame(art: Image.Image, origin: tuple[int, int]) -> Image.Image:
    canvas = Image.new("RGBA", ENTITY_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((1, 1, 94, 142), radius=8,
                           fill=(18, 23, 31, 238))
    x, y = origin
    inner_box = (x, y, x + art.width - 1, y + art.height - 1)
    mask = Image.new("L", ENTITY_SIZE, 0)
    ImageDraw.Draw(mask).rounded_rectangle(inner_box, radius=6, fill=255)
    layer = Image.new("RGBA", ENTITY_SIZE, (0, 0, 0, 0))
    layer.alpha_composite(art, origin)
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    canvas = Image.alpha_composite(canvas, layer)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((1, 1, 94, 142), radius=8,
                           outline=(198, 164, 93, 255), width=1)
    draw.rounded_rectangle((2, 2, 93, 141), radius=7,
                           outline=(55, 39, 25, 255), width=1)
    draw.rounded_rectangle(inner_box, radius=6,
                           outline=(235, 214, 153, 220), width=1)
    return canvas


def render_entity(card: dict, state: dict, assets_dir: Path,
                  layout: dict | None = None, crop: bool = True,
                  info: dict | None = None) -> Image.Image:
    if not entity_eligible(card):
        raise ValueError("该卡牌类型不支持对局式神渲染")
    state = _card_state(card, state)
    entity_layout = layout if layout is not None else _DEFAULT_LAYOUT
    window = entity_layout.get("art_window", _DEFAULT_LAYOUT["art_window"])
    validate_entity_art_window(window)
    lib = get_library(assets_dir)
    ref = artwork_ref(card)
    original, rotated = load_card_artwork(card, lib)
    width, height = window["width"], window["height"]
    inner_size = (max(1, round(width)), max(1, round(height)))
    ratio = width / 512
    offset_y = ref["offset_y"] * ratio + window["offset_y"]
    if window["frame_center"]:
        code = TYPE_FRAME_CODE[card["type"]]
        frame = _normalize_frame(lib.frame(code, card.get("frame_variant", "norm")))
        _, frame_cy = frame_art_window_center(frame)
        offset_y += (256 - frame_cy) * ratio
    art = fit_artwork(rotated, inner_size, ref["offset_x"] * ratio,
                      offset_y, state["art_scale"], cover_base=original)
    center_x, center_y = window["center"]
    origin = (round(center_x - width / 2), round(center_y - height / 2))
    canvas = _render_frame(art, origin)
    elements = entity_layout["elements"]
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


__all__ = ["entity_eligible", "frame_art_window_center", "render_entity",
           "validate_entity_state"]
