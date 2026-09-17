"""几何：文本排版的障碍避让（行 span 按障碍矩形收窄）。"""


def clamp_span_by_obstacles(span: tuple[float, float], y: float, half_h: float,
                            obstacles: list[tuple[float, float, float, float]],
                            gap: float = 4.0) -> tuple[float, float] | None:
    """行 y 带 [y-half_h, y+half_h] 与障碍矩形相交时按侧收窄 span；无宽度返回 None。"""
    left, right = span
    center = (left + right) / 2
    for x0, y0, x1, y1 in obstacles:
        if y1 < y - half_h or y0 > y + half_h:
            continue
        if (x0 + x1) / 2 < center:
            left = max(left, x1 + gap)
        else:
            right = min(right, x0 - gap)
    if right - left <= 0:
        return None
    return left, right
