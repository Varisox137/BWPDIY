from bwpdiy.render.geometry import polygon_x_span, polygon_y_range

RECT = [[100, 100], [300, 100], [300, 200], [100, 200]]
TRIANGLE = [[100, 200], [300, 200], [200, 100]]  # 顶点在上的三角


def test_rect_span():
    assert polygon_x_span(RECT, 150) == (100.0, 300.0)


def test_rect_outside():
    assert polygon_x_span(RECT, 50) is None
    assert polygon_x_span(RECT, 250) is None


def test_triangle_span_narrows_upward():
    low = polygon_x_span(TRIANGLE, 175)
    high = polygon_x_span(TRIANGLE, 125)
    assert low and high
    assert (low[1] - low[0]) > (high[1] - high[0])
    assert abs((low[0] + low[1]) / 2 - 200) < 1e-6  # 关于 x=200 对称


def test_y_range():
    assert polygon_y_range(TRIANGLE) == (100, 200)


def test_clamp_span_by_obstacles():
    from bwpdiy.render.geometry import clamp_span_by_obstacles
    span = (100.0, 300.0)
    # 左侧障碍（数值标在左下）：抬左界
    left_obs = [(110.0, 140.0, 150.0, 170.0)]
    assert clamp_span_by_obstacles(span, 150, 12, left_obs) == (154.0, 300.0)
    # 右侧障碍：压右界
    right_obs = [(250.0, 140.0, 290.0, 170.0)]
    assert clamp_span_by_obstacles(span, 150, 12, right_obs) == (100.0, 246.0)
    # y 带不相交：不受影响
    assert clamp_span_by_obstacles(span, 100, 12, left_obs) == span
    # 双侧挤压到无宽度：None
    both = [(110.0, 140.0, 190.0, 170.0), (180.0, 140.0, 290.0, 170.0)]
    assert clamp_span_by_obstacles((150.0, 200.0), 150, 12, both) is None
