from bwpdiy.render.geometry import clamp_span_by_obstacles


def test_clamp_span_by_obstacles():
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
