"""几何：文本排版的障碍避让（行 span 按掩膜墨迹区间收窄）。

避让口径：stat 角标的真实绘制墨迹（alpha 掩膜）而非组件矩形 bbox。
墨迹区间向 x 两侧外扩 gap、行 y 带向竖直两侧外扩 gap 后参与收窄，
保证描述墨迹与角标墨迹相距 ≥ gap。
"""

import math


def mask_row_runs(mask, alpha_min: int = 10) -> dict[int, list[tuple[int, int]]]:
    """L 掩膜逐行求墨迹 x 区间（alpha > alpha_min），返回 {行号: [(x0, x1), ...]}（x1 不含）。"""
    bbox = mask.getbbox()
    if bbox is None:
        return {}
    x_lo, y_lo, x_hi, y_hi = bbox
    px = mask.load()
    runs: dict[int, list[tuple[int, int]]] = {}
    for y in range(y_lo, y_hi):
        row = []
        x = x_lo
        while x < x_hi:
            if px[x, y] > alpha_min:
                x0 = x
                while x < x_hi and px[x, y] > alpha_min:
                    x += 1
                row.append((x0, x))
            else:
                x += 1
        if row:
            runs[y] = row
    return runs


def clamp_span_by_mask(span: tuple[float, float], y: float, half_h: float,
                       row_runs: dict[int, list[tuple[int, int]]],
                       gap: float = 4.0) -> tuple[float, float] | None:
    """行 y 带 [y-half_h, y+half_h] 竖直外扩 gap 后与掩膜墨迹相交时按侧收窄 span。

    墨迹 x 区间向两侧外扩 gap；区间按中心分侧（左侧抬左界、右侧压右界）。
    收窄后无宽度返回 None。row_runs 为 mask_row_runs 产出。
    """
    left, right = span
    center = (left + right) / 2
    y0 = math.floor(y - half_h - gap)
    y1 = math.ceil(y + half_h + gap)
    for row in range(y0, y1 + 1):
        for x0, x1 in row_runs.get(row, ()):
            if (x0 + x1) / 2 < center:
                left = max(left, x1 + gap)
            else:
                right = min(right, x0 - gap)
    if right - left <= 0:
        return None
    return left, right
