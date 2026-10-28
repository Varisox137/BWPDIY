"""对局式神小卡的独立纯 PIL 渲染器。"""

import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

from bwpdiy.render.artwork import (
    ARTWORK_MAX_PIXELS, artwork_ref, fit_artwork, load_card_artwork)
from bwpdiy.render.assets import AssetLibrary, get_library
from bwpdiy.render.badges import (
    _DIGIT_GAP, STAT_COLORS, TYPE_FRAME_CODE, _paste_element, _render_digits)
from bwpdiy.render.pipeline import _normalize_frame
from bwpdiy.render.size import fit_target_canvas, resolve_target_size, scale_layout

ENTITY_SIZE = (96, 144)
ENTITY_MAX_COORD = 4096
ENTITY_MAX_ELEMENT_SIZE = 1024
ENTITY_MAX_FONT_SIZE = 256
ENTITY_MAX_STROKE_WIDTH = 32
ENTITY_MAX_STAT_DIGITS = 12
ENTITY_MAX_ART_WINDOW_SIDE = 8000
ENTITY_MAX_WORK_SIDE = 4096
ENTITY_MAX_WORK_PIXELS = 16_000_000
ENTITY_ART_Y_BIAS = -0.04  # 下角标使视觉重心偏下，卡图默认上移窗口高度的 4%
LEVEL_COLORS = {"yellow", "cyan", "purple", "red", "blue", "brown"}

_DEFAULT_LAYOUT = {
    "version": 2,
    "art_window": {
        "center": [48, 72], "width": 84, "height": 132,
        "frame_center": True, "offset_y": 0,
    },
    "elements": {
        "level": {
            "kind": "level_badge", "pos": [48, 137], "base_size": 27,
            "num_size": 21, "num_offset": [0, 0],
        },
        "power": {
            "kind": "stat", "field": "power", "pos": [15, 130],
            "icon_size": 32, "num_offset": [-1, 1], "font_size": 24,
            "stroke_width": 2,
        },
        "health": {
            "kind": "stat", "field": "health", "pos": [84, 130],
            "icon_size": 34, "num_offset": [1, 2], "font_size": 24,
            "stroke_width": 2,
        },
        "combat_power": {
            "kind": "stat", "field": "combat_power", "pos": [13, 101],
            "icon_size": 34, "num_offset": [0, 0], "font_size": 22,
            "stroke_width": 2,
        },
        "shield": {
            "kind": "stat", "field": "shield", "pos": [83, 100],
            "icon_size": 29, "num_offset": [0, 1], "font_size": 22,
            "stroke_width": 2,
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


def _bounded_number(value, maximum: int, positive: bool = False) -> bool:
    return (_finite_number(value) and abs(value) <= maximum
            and (not positive or value > 0))


def _bounded_pair(value) -> bool:
    return (isinstance(value, (list, tuple)) and len(value) == 2
            and all(_bounded_number(item, ENTITY_MAX_COORD) for item in value))


def validate_entity_art_window(window: dict) -> None:
    if not isinstance(window, dict):
        raise ValueError("卡图窗必须是对象")
    if not _bounded_pair(window.get("center")):
        raise ValueError("卡图窗 center 必须是两个有限且限幅的数值")
    width, height = window.get("width"), window.get("height")
    if not all(_finite_number(value) and value > 0 for value in (width, height)):
        raise ValueError("卡图窗宽高必须是有限正数")
    if width * height > ARTWORK_MAX_PIXELS:
        raise ValueError("卡图窗面积超像素上限")
    inner_width, inner_height = max(1, round(width)), max(1, round(height))
    if inner_width * inner_height > ARTWORK_MAX_PIXELS:
        raise ValueError("卡图窗面积超像素上限")
    if max(width, height) > ENTITY_MAX_ART_WINDOW_SIDE:
        raise ValueError("卡图窗宽高超尺寸上限")
    if not isinstance(window.get("frame_center"), bool):
        raise ValueError("卡图窗 frame_center 必须是布尔值")
    if not _bounded_number(window.get("offset_y"), ENTITY_MAX_COORD):
        raise ValueError("卡图窗 offset_y 必须是有限且限幅的数值")


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
    for field in ("power", "health", "combat_power", "shield"):
        normalized[f"{field}_color"] = state.get(f"{field}_color")
    for field in ("power", "health", "combat_power", "shield", "level"):
        if not _is_int(normalized[field]):
            raise ValueError(f"{field} 必须是整数")
    if normalized["power"] < 0 or normalized["health"] < 0:
        raise ValueError("power/health 必须是非负整数")
    max_value = 10 ** ENTITY_MAX_STAT_DIGITS - 1
    for field in ("power", "health", "combat_power", "shield"):
        if abs(normalized[field]) > max_value:
            raise ValueError(f"{field} 数值位数不得超过 {ENTITY_MAX_STAT_DIGITS} 位")
        color = normalized[f"{field}_color"]
        if color is not None and (not isinstance(color, str) or color not in STAT_COLORS):
            raise ValueError(f"{field}_color 非法")
    if normalized["level"] not in (0, 1, 2, 3):
        raise ValueError("level 必须是 0、1、2 或 3")
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
        normalized["level"] = level if _is_int(level) and level in (0, 1, 2, 3) else 1
    color = card.get("level_color")
    if "level_color" not in state:
        normalized["level_color"] = (
            color if isinstance(color, str) and color in LEVEL_COLORS else "yellow")
    for field in ("power", "health", "combat_power", "shield"):
        key = f"{field}_color"
        color = card.get(key)
        if key not in state and isinstance(color, str) and color in STAT_COLORS:
            normalized[key] = color
    return normalized


def _render_level(canvas: Image.Image, lib: AssetLibrary, elem: dict,
                  state: dict) -> Image.Image:
    if state["level"] == 0 or not elem.get("enabled", True):
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


def _validate_entity_elements(elements: dict, state: dict) -> None:
    if not isinstance(elements, dict):
        raise ValueError("对局式神元素表必须是对象")
    level = elements.get("level")
    if level is not None:
        if not isinstance(level, dict):
            raise ValueError("等级标元素必须是对象")
        if level.get("enabled", True):
            if not _bounded_pair(level.get("pos")):
                raise ValueError("等级标 pos 必须是两个有限且限幅的数值")
            if not _bounded_pair(level.get("num_offset", [0, 0])):
                raise ValueError("等级标 num_offset 必须是两个有限且限幅的数值")
            for key in ("base_size", "num_size"):
                if not _bounded_number(level.get(key), ENTITY_MAX_ELEMENT_SIZE, True):
                    raise ValueError(f"等级标 {key} 必须是有限且限幅的正数")
    for field in ("power", "health", "combat_power", "shield"):
        elem = elements.get(field)
        if elem is None:
            continue
        if not isinstance(elem, dict):
            raise ValueError(f"{field} 元素必须是对象")
        if not elem.get("enabled", True):
            continue
        if field in ("combat_power", "shield") and state[field] == 0:
            continue
        for key in ("pos", "num_offset"):
            if not _bounded_pair(elem.get(key, [0, 0] if key == "num_offset" else None)):
                raise ValueError(f"{field} {key} 必须是两个有限且限幅的数值")
        if not _bounded_number(elem.get("icon_size"), ENTITY_MAX_ELEMENT_SIZE, True):
            raise ValueError(f"{field} icon_size 必须是有限且限幅的正数")
        font_size = elem.get("font_size")
        if not _is_int(font_size) or not 0 < font_size <= ENTITY_MAX_FONT_SIZE:
            raise ValueError(f"{field} font_size 必须是有限且限幅的正整数")
        stroke_width = elem.get("stroke_width", 1)
        if not _bounded_number(stroke_width, ENTITY_MAX_STROKE_WIDTH) or stroke_width < 0:
            raise ValueError(f"{field} stroke_width 必须是有限且限幅的非负数")


def _render_stat(canvas: Image.Image, lib: AssetLibrary, elem: dict,
                 state: dict, digits: Image.Image | None) -> Image.Image:
    if not elem.get("enabled", True):
        return canvas
    field = elem["field"]
    value = state[field]
    if field in ("combat_power", "shield") and value == 0:
        return canvas
    pos = elem["pos"]
    out = _paste_element(canvas, _stat_icon(lib, field, value), pos,
                         (elem["icon_size"], elem["icon_size"]))
    if digits is None:
        return out
    nx, ny = elem.get("num_offset", [0, 0])
    center_x = pos[0] + nx
    center_y = pos[1] + ny
    out = out.copy()
    out.alpha_composite(digits, (round(center_x - digits.width / 2),
                                 round(center_y - digits.height / 2)))
    return out


def _entity_work_bounds(lib: AssetLibrary, elements: dict,
                        state: dict) -> tuple[tuple[int, int, int, int], dict]:
    _validate_entity_elements(elements, state)
    rects = [(0, 0, *ENTITY_SIZE)]
    prepared_digits = {}

    def add_centered(pos, size):
        x, y = pos
        width, height = size
        rects.append((x - width / 2, y - height / 2,
                      x + width / 2, y + height / 2))

    def checked_bounds():
        bounds = (math.floor(min(rect[0] for rect in rects)),
                  math.floor(min(rect[1] for rect in rects)),
                  math.ceil(max(rect[2] for rect in rects)),
                  math.ceil(max(rect[3] for rect in rects)))
        width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        if width > ENTITY_MAX_WORK_SIDE or height > ENTITY_MAX_WORK_SIDE:
            raise ValueError("对局式神工作画布宽高超尺寸上限")
        if width * height > ENTITY_MAX_WORK_PIXELS:
            raise ValueError("对局式神工作画布面积超像素上限")
        return bounds

    level = elements.get("level")
    if state["level"] != 0 and level is not None and level.get("enabled", True):
        pos = level["pos"]
        add_centered(pos, (level["base_size"], level["base_size"]))
        nx, ny = level.get("num_offset", [0, 0])
        add_centered((pos[0] + nx, pos[1] + ny),
                     (level["num_size"], level["num_size"]))
    for field in ("power", "health", "combat_power", "shield"):
        elem = elements.get(field)
        if elem is None or not elem.get("enabled", True):
            continue
        if field in ("combat_power", "shield") and state[field] == 0:
            continue
        add_centered(elem["pos"], (elem["icon_size"], elem["icon_size"]))
    checked_bounds()
    for field in ("power", "health", "combat_power", "shield"):
        elem = elements.get(field)
        if elem is None or not elem.get("enabled", True):
            continue
        value = state[field]
        if field in ("combat_power", "shield") and value == 0:
            continue
        digits = _render_digits(str(abs(value)), lib.font("name", elem["font_size"]),
                                round(elem.get("stroke_width", 1)), state[f"{field}_color"],
                                elem.get("_digit_gap", _DIGIT_GAP))
        prepared_digits[field] = digits
        if digits is None:
            continue
        pos = elem["pos"]
        nx, ny = elem.get("num_offset", [0, 0])
        x = round(pos[0] + nx - digits.width / 2)
        y = round(pos[1] + ny - digits.height / 2)
        rects.append((x, y, x + digits.width, y + digits.height))
    return checked_bounds(), prepared_digits


def _render_frame(art: Image.Image, origin: tuple[int, int],
                  factor: float = 1.0) -> Image.Image:
    size = (max(1, round(ENTITY_SIZE[0] * factor)),
            max(1, round(ENTITY_SIZE[1] * factor)))
    v = lambda value: round(value * factor)
    line = max(1, v(1))
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((v(1), v(1), v(94), v(142)), radius=v(8),
                           fill=(18, 23, 31, 238))
    x, y = origin
    inner_box = (x, y, x + art.width - 1, y + art.height - 1)
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(inner_box, radius=v(6), fill=255)
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    layer.alpha_composite(art, origin)
    layer.putalpha(ImageChops.multiply(layer.getchannel("A"), mask))
    canvas = Image.alpha_composite(canvas, layer)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((v(1), v(1), v(94), v(142)), radius=v(8),
                           outline=(198, 164, 93, 255), width=line)
    draw.rounded_rectangle((v(2), v(2), v(93), v(141)), radius=v(7),
                           outline=(55, 39, 25, 255), width=line)
    draw.rounded_rectangle(inner_box, radius=v(6),
                           outline=(235, 214, 153, 220), width=line)
    return canvas


def render_entity(card: dict, state: dict, assets_dir: Path,
                  layout: dict | None = None, crop: bool = True,
                  info: dict | None = None, width: int | None = None,
                  height: int | None = None, _measure_only: bool = False) -> Image.Image:
    """渲染对局小卡；width/height 按默认紧致比例原生重绘全部元素。"""
    target_size = None
    factor = 1.0
    if (width is not None or height is not None) and not _measure_only:
        probe = render_entity(card, state, assets_dir, layout, _measure_only=True)
        target_size = resolve_target_size(probe.size, width, height)
        factor = target_size[0] / probe.width
    if not entity_eligible(card):
        raise ValueError("该卡牌类型不支持对局式神渲染")
    state = _card_state(card, state)
    entity_layout = layout if layout is not None else _DEFAULT_LAYOUT
    if not isinstance(entity_layout, dict):
        raise ValueError("对局式神布局必须是对象")
    if factor != 1:
        entity_layout = scale_layout(entity_layout, factor)
        for elem in (entity_layout.get("elements") or {}).values():
            if elem.get("kind") == "stat":
                elem["_digit_gap"] = _DIGIT_GAP * factor
    window = entity_layout.get("art_window", _DEFAULT_LAYOUT["art_window"])
    validate_entity_art_window(window)
    elements = entity_layout.get("elements")
    lib = get_library(assets_dir)
    (left, top, right, bottom), prepared_digits = _entity_work_bounds(
        lib, elements, state)
    ref = artwork_ref(card)
    window_width, window_height = window["width"], window["height"]
    inner_size = (max(1, round(window_width)), max(1, round(window_height)))
    ratio = window_width / 512
    offset_y = ref["offset_y"] * ratio + window["offset_y"] + window_height * ENTITY_ART_Y_BIAS
    if window["frame_center"]:
        code = TYPE_FRAME_CODE[card["type"]]
        source_frame = _normalize_frame(lib.frame(code, card.get("frame_variant", "norm")))
        _, frame_cy = frame_art_window_center(source_frame)
        offset_y += (256 - frame_cy) * ratio
    if _measure_only:
        art = Image.new("RGBA", inner_size, (0, 0, 0, 0))
    else:
        original, rotated = load_card_artwork(card, lib)
        art = fit_artwork(rotated, inner_size, ref["offset_x"] * ratio,
                          offset_y, state["art_scale"], cover_base=original)
    center_x, center_y = window["center"]
    origin = (round(center_x - window_width / 2), round(center_y - window_height / 2))
    canvas = _render_frame(art, origin, factor)
    frame = canvas
    canvas = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
    canvas.alpha_composite(frame, (-left, -top))

    def shifted(elem):
        return {**elem, "pos": [elem["pos"][0] - left, elem["pos"][1] - top]}

    if "level" in elements:
        canvas = _render_level(canvas, lib, shifted(elements["level"]), state)
    for field in ("power", "health", "combat_power", "shield"):
        if field in elements:
            canvas = _render_stat(canvas, lib, shifted(elements[field]), state,
                                  prepared_digits.get(field))
    if not crop:
        return canvas
    bbox = canvas.getchannel("A").point(lambda value: 255 if value > 10 else 0).getbbox()
    if info is not None:
        info["crop_origin"] = ((left + bbox[0], top + bbox[1])
                               if bbox else (0, 0))
    out = canvas.crop(bbox) if bbox else canvas
    return fit_target_canvas(out, target_size) if target_size is not None else out


__all__ = ["entity_eligible", "frame_art_window_center", "render_entity",
           "validate_entity_state"]
