"""目标尺寸的参数校验与几何缩放；不对渲染成品做二次重采样。"""

import copy
import math

MAX_RENDER_SIDE = 8192
MAX_RENDER_PIXELS = 64_000_000

_PAIR_KEYS = {
    "pos", "fragile_pos", "center", "center_offset", "num_offset",
    "sign_offset", "group_offset", "fragile_num_offset", "fragile_sign_offset",
    "frame_offset", "frame_offset_2", "faction_offset", "badge_pos", "star_offset",
}
_SCALAR_KEYS = {
    "base_size", "num_size", "star_size", "size", "icon_size",
    "fragile_icon_size", "font_size", "stroke_width", "sign_size",
    "sign_size_plus", "sign_size_minus", "gap", "margin", "slot2_dy",
    "back_size", "frame_size", "faction_size", "highlight_dy_1",
    "highlight_dy_2", "width", "height", "obstacle_gap", "text_dy", "text_x",
    "line_gap", "digit_gap", "sign_gap",
}
_INTEGER_KEYS = {
    "base_size", "num_size", "star_size", "size", "icon_size",
    "fragile_icon_size", "font_size", "stroke_width", "sign_size",
    "sign_size_plus", "sign_size_minus", "back_size", "frame_size", "faction_size",
}


def _dimension(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} 必须是正整数")
    if value > MAX_RENDER_SIDE:
        raise ValueError(f"{name} 超过边长上限 {MAX_RENDER_SIDE}")
    return value


def resolve_target_size(default_size: tuple[int, int], width: int | None,
                        height: int | None) -> tuple[int, int] | None:
    """按默认紧致输出比例求目标尺寸；双参数允许整数取整造成的 1px 误差。"""
    if width is None and height is None:
        return None
    default_w, default_h = default_size
    if default_w <= 0 or default_h <= 0:
        raise ValueError("默认渲染尺寸非法")
    if width is not None:
        _dimension(width, "宽度")
    if height is not None:
        _dimension(height, "高度")
    if width is None:
        width = max(1, round(height * default_w / default_h))
    if height is None:
        height = max(1, round(width * default_h / default_w))
    if abs(width * default_h - height * default_w) > max(default_w, default_h):
        raise ValueError(f"宽度/高度比例不一致，应保持默认比例 {default_w}:{default_h}")
    if width * height > MAX_RENDER_PIXELS:
        raise ValueError(f"目标尺寸超过像素上限 {MAX_RENDER_PIXELS}")
    return width, height


def scale_layout(layout: dict, factor: float) -> dict:
    """仅缩放布局几何值；比例、枚举、开关与资源选择保持原样。"""
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError("渲染缩放比例必须是有限正数")

    def visit(value, key=None):
        if isinstance(value, dict):
            return {k: visit(v, k) for k, v in value.items()}
        if isinstance(value, list):
            if key in _PAIR_KEYS and len(value) == 2:
                return [v * factor for v in value]
            if key == "font_range" and len(value) == 2:
                return [max(1, round(v * factor)) for v in value]
            return [visit(v, key) for v in value]
        if key in _SCALAR_KEYS and isinstance(value, (int, float)) and not isinstance(value, bool):
            scaled = value * factor
            return max(1, round(scaled)) if key in _INTEGER_KEYS else scaled
        return value

    return visit(copy.deepcopy(layout))


def fit_target_canvas(image, target_size: tuple[int, int]):
    """只裁剪或补透明边到精确尺寸，不重采样像素。"""
    return image.crop((0, 0, target_size[0], target_size[1]))


__all__ = ["MAX_RENDER_PIXELS", "MAX_RENDER_SIDE", "fit_target_canvas",
           "resolve_target_size", "scale_layout"]
