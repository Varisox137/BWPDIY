from PIL import Image

from bwpdiy.render.geometry import clamp_span_by_mask, mask_row_runs


def ink_mask(rects, size=(512, 512)):
    """L 掩膜：rects 为 (x0, y0, x1, y1) 半开区间实心墨迹。"""
    mask = Image.new("L", size, 0)
    for r in rects:
        mask.paste(255, r)
    return mask


def test_mask_row_runs():
    runs = mask_row_runs(ink_mask([(10, 20, 30, 25)]))
    assert set(runs) == set(range(20, 25))
    assert runs[20] == [(10, 30)]


def test_mask_row_runs_multiple_segments():
    runs = mask_row_runs(ink_mask([(10, 20, 30, 25), (100, 22, 120, 40)]))
    assert runs[22] == [(10, 30), (100, 120)]
    assert runs[30] == [(100, 120)]


def test_clamp_span_by_mask_sides():
    span = (100.0, 300.0)
    # 左侧墨迹：抬左界到墨迹右缘 + gap（缺省 4）
    left_runs = mask_row_runs(ink_mask([(110, 140, 150, 170)]))
    assert clamp_span_by_mask(span, 155, 12, left_runs) == (154.0, 300.0)
    # 右侧墨迹：压右界到墨迹左缘 - gap
    right_runs = mask_row_runs(ink_mask([(250, 140, 290, 170)]))
    assert clamp_span_by_mask(span, 155, 12, right_runs) == (100.0, 246.0)
    # 双侧挤压到无宽度：None
    both = mask_row_runs(ink_mask([(110, 140, 190, 170), (180, 140, 290, 170)]))
    assert clamp_span_by_mask((150.0, 200.0), 155, 12, both) is None


def test_clamp_span_by_mask_vertical_gap():
    # y 带（含 gap 竖直外扩）与墨迹行不相交：不受影响
    runs = mask_row_runs(ink_mask([(110, 140, 150, 170)]))
    span = (100.0, 300.0)
    assert clamp_span_by_mask(span, 100, 12, runs) == span
    # 墨迹在 y 带下方但竖直距离 ≤ gap：同样收窄（保证墨迹间距 ≥ gap）
    assert clamp_span_by_mask(span, 125, 12, runs) == (154.0, 300.0)


def test_clamp_span_by_mask_custom_gap():
    runs = mask_row_runs(ink_mask([(110, 140, 150, 170)]))
    assert clamp_span_by_mask((100.0, 300.0), 155, 12, runs, gap=10) == (160.0, 300.0)
