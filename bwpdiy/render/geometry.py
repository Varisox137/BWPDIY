"""多边形几何：水平扫描线求交（文本区排版用）。"""


def polygon_x_span(polygon: list[list[float]], y: float) -> tuple[float, float] | None:
    """水平线 y 与多边形交点的 x 区间；无交（或仅切于顶点）返回 None。

    采用标准扫描线规则：边 (y1<=y<y2) 计入，避免顶点重复计数。
    """
    xs: list[float] = []
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if y1 == y2:
            continue
        if min(y1, y2) <= y < max(y1, y2):
            xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    if len(xs) < 2:
        return None
    xs.sort()
    return xs[0], xs[-1]


def polygon_y_range(polygon: list[list[float]]) -> tuple[float, float]:
    ys = [p[1] for p in polygon]
    return min(ys), max(ys)


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
