import pytest
from PIL import Image

import bwpdiy.render.artwork as artwork
from bwpdiy.render.artwork import fit_artwork, rotate_artwork


def make_art(w=800, h=600):
    return Image.new("RGBA", (w, h), (200, 100, 50, 255))


def test_artwork_ref_empty_id_falls_back_to_card_name():
    assert artwork.artwork_ref({"id": "", "name": "甲"})["path"] == "甲.png"


def test_fit_cover_and_size():
    out = fit_artwork(make_art(), (512, 512))
    assert out.size == (512, 512)
    # cover：800x600 → 缩放 512/600，宽 683 ≥ 512


def test_fit_scale_enlarges():
    # scale 放大后裁剪窗口左移空间变大，不报错且尺寸不变
    out = fit_artwork(make_art(), (512, 512), scale=1.5)
    assert out.size == (512, 512)


def test_fit_rejects_oversized_resize_before_allocation(monkeypatch):
    def forbidden_resize(self, *args, **kwargs):
        pytest.fail("超限卡图不得进入 resize")

    monkeypatch.setattr(Image.Image, "resize", forbidden_resize)
    with pytest.raises(ValueError, match="超像素上限"):
        fit_artwork(make_art(2, 2), (64, 96), scale=1e100)


def test_fit_allows_exact_output_pixel_limit(monkeypatch):
    import bwpdiy.render.artwork as artwork

    monkeypatch.setattr(artwork, "ARTWORK_MAX_PIXELS", 4)
    out = fit_artwork(make_art(1, 1), (2, 2))
    assert out.size == (2, 2)


def test_fit_offset_shifts_window():
    """用左右两半不同颜色的图验证 offset 平移：正值 = 图像向右移（v1.3.0 起）。"""
    img = Image.new("RGBA", (1024, 512), (255, 0, 0, 255))
    for x in range(512, 1024):
        for y in range(512):
            img.putpixel((x, y), (0, 0, 255, 255))
    right = fit_artwork(img, (512, 512), offset_x=256)   # 图像右移：左半红入画
    left = fit_artwork(img, (512, 512), offset_x=-256)   # 图像左移：右半蓝入画
    assert right.getpixel((10, 256)) == (255, 0, 0, 255)
    assert left.getpixel((502, 256)) == (0, 0, 255, 255)


def test_fit_offset_free_pan_transparent():
    """offset 不钳制（v1.3.0 修：与画布同宽高的图 offset 被钳死完全无效果）：
    平出画面的区域留透明，超大 offset 整幅透明、不抛异常。"""
    out = fit_artwork(make_art(600, 600), (512, 512), offset_x=99999)
    assert out.size == (512, 512)
    assert out.getpixel((10, 256))[3] == 0  # 图已平出画面


def test_fit_offset_works_for_square_image():
    """方形图 cover 缩放后与画布同尺寸（无平移余量）：offset 仍生效。"""
    img = Image.new("RGBA", (1024, 1024), (255, 0, 0, 255))
    for x in range(512, 1024):
        for y in range(1024):
            img.putpixel((x, y), (0, 0, 255, 255))  # 左半红、右半蓝
    base = fit_artwork(img, (512, 512))
    assert base.getpixel((500, 256))[3] == 255      # 满幅不透明
    moved = fit_artwork(img, (512, 512), offset_x=100)   # 图像右移
    assert moved.getpixel((10, 256))[3] == 0        # 左缘让出透明带
    assert moved.getpixel((500, 256)) == (0, 0, 255, 255)  # 右半蓝仍可见
    back = fit_artwork(img, (512, 512), offset_x=-100)   # 图像左移
    assert back.getpixel((500, 256))[3] == 0        # 右缘让出透明带
    assert back.getpixel((10, 256)) == (255, 0, 0, 255)  # 左半红仍可见


def test_fit_rgb_input_pads_transparent():
    """RGB 输入越界区域同样填透明（内部先转 RGBA，不会填不透明黑）。"""
    out = fit_artwork(Image.new("RGB", (512, 512), (255, 0, 0)), (512, 512), offset_x=100)
    assert out.getpixel((10, 256))[3] == 0  # 图像右移：左缘透明


# ---------- 旋转（v1.2.1） ----------

def test_rotate_zero_noop():
    img = make_art(400, 200)
    assert rotate_artwork(img, 0) is img  # 不旋转不复制
    assert rotate_artwork(img, 360) is img


def test_rotate_90_expands_canvas():
    """90° 旋转交换宽高（画布扩展至容纳结果）。"""
    out = rotate_artwork(make_art(400, 200), 90)
    assert out.size == (200, 400)


def test_rotate_45_expands_to_fit():
    """非直角旋转：画布扩大以容纳对角线，中心锚点不变（内容居中）。"""
    out = rotate_artwork(make_art(400, 200), 45)
    assert out.width > 400 and out.height > 200
    # 中心像素仍为图内容（纯色图旋转后中心必为原色）
    assert out.getpixel((out.width // 2, out.height // 2)) == (200, 100, 50, 255)


def test_rotate_clockwise_semantics():
    """rotate 正值 = 顺时针：顶部红色半条旋转后到右侧。"""
    img = Image.new("RGBA", (200, 200), (0, 0, 255, 255))
    for x in range(200):
        for y in range(100):
            img.putpixel((x, y), (255, 0, 0, 255))  # 上半红、下半蓝
    out = rotate_artwork(img, 90)
    assert out.getpixel((150, 100))[0] > 200  # 右半红
    assert out.getpixel((50, 100))[2] > 200   # 左半蓝


def test_rotate_fit_pipeline():
    """旋转与 fit 组合：旋转后的缓存图再缩放裁剪，输出尺寸不变。"""
    out = fit_artwork(rotate_artwork(make_art(800, 600), 30), (512, 512))
    assert out.size == (512, 512)


def test_rotate_preserves_content_scale():
    """cover_base=旋转前尺寸：旋转后内容视觉尺度与不旋转一致（v1.2.2 修旋转自带缩放）。

    中心 100×100 红块：不旋转时宽=100×(512/200)=256；45° 旋转后为对角线 256√2≈362。
    （旧逻辑按旋转后外接矩形算 cover，45° 时红块只剩约 171，内容明显缩小。）
    """
    img = Image.new("RGBA", (400, 200), (0, 0, 255, 255))
    for x in range(150, 250):
        for y in range(50, 150):
            img.putpixel((x, y), (255, 0, 0, 255))

    def red_bbox_w(im):
        xs = [x for y in range(512) for x in range(512)
              if im.getpixel((x, y))[0] > 200 and im.getpixel((x, y))[3] > 200]
        return max(xs) - min(xs)

    w_plain = red_bbox_w(fit_artwork(img, (512, 512)))
    w_rot = red_bbox_w(fit_artwork(rotate_artwork(img, 45), (512, 512),
                                   cover_base=(400, 200)))
    assert abs(w_plain - 256) <= 4
    assert abs(w_rot - 362) <= 12


# ---------- 缩放中间图缓存 ----------

def test_fit_artwork_cached_reuses_resize(sample_art, monkeypatch):
    artwork._FIT_CACHE.clear()
    with Image.open(sample_art) as opened:
        source = opened.convert("RGBA")
    expected_a = fit_artwork(source, (512, 512), 0, 0, 1)
    expected_b = fit_artwork(source, (512, 512), 20, 0, 1)
    original = Image.Image.resize
    calls = []

    def counted(self, size, resample=None, *args, **kwargs):
        calls.append(size)
        return original(self, size, resample, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "resize", counted)
    a = artwork.fit_artwork_cached(source, (512, 512), 0, 0, 1)
    first_calls = len(calls)
    b = artwork.fit_artwork_cached(source, (512, 512), 20, 0, 1)
    assert a.tobytes() == expected_a.tobytes()
    assert b.tobytes() == expected_b.tobytes()
    assert first_calls > 0
    assert len(calls) == first_calls


def test_fit_artwork_cached_key_includes_source_scale_and_cover_base(monkeypatch):
    artwork._FIT_CACHE.clear()
    red = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
    blue = Image.new("RGBA", (2, 2), (0, 0, 255, 255))
    original = Image.Image.resize
    calls = []

    def counted(self, size, resample=None, *args, **kwargs):
        calls.append((self, size))
        return original(self, size, resample, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "resize", counted)
    for operation in (
            lambda: artwork.fit_artwork_cached(red, (4, 4)),
            lambda: artwork.fit_artwork_cached(blue, (4, 4)),
            lambda: artwork.fit_artwork_cached(red, (4, 4), scale=2),
            lambda: artwork.fit_artwork_cached(red, (4, 4), cover_base=(1, 1))):
        previous_calls = len(calls)
        result = operation()
        assert len(calls) > previous_calls
        assert result.size == (4, 4)
    assert artwork.fit_artwork_cached(red, (4, 4)).getpixel((0, 0)) == (255, 0, 0, 255)
    assert artwork.fit_artwork_cached(blue, (4, 4)).getpixel((0, 0)) == (0, 0, 255, 255)


def test_fit_artwork_cached_holds_source_and_bounds_total_pixels(monkeypatch):
    artwork._FIT_CACHE.clear()
    monkeypatch.setattr(artwork, "ARTWORK_CACHE_MAX_PIXELS", 4)
    sources = [Image.new("RGBA", (1, 1), (i, 0, 0, 255)) for i in range(3)]
    for source in sources:
        artwork.fit_artwork_cached(source, (2, 2))
    assert 0 < len(artwork._FIT_CACHE) <= 1
    assert sum(resized.width * resized.height
               for source, resized in artwork._FIT_CACHE.values()) <= 4
    cached_source = next(iter(artwork._FIT_CACHE.values()))[0]
    assert cached_source is sources[-1]


def test_fit_artwork_cached_resize_runs_outside_lock(monkeypatch):
    import threading

    artwork._FIT_CACHE.clear()

    class RecordingLock:
        def __init__(self):
            self.lock = threading.RLock()
            self.held = False

        def __enter__(self):
            self.lock.acquire()
            self.held = True

        def __exit__(self, *args):
            self.held = False
            self.lock.release()

    lock = RecordingLock()
    monkeypatch.setattr(artwork, "_FIT_LOCK", lock)
    original = Image.Image.resize

    def checked(self, *args, **kwargs):
        assert not lock.held
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Image.Image, "resize", checked)
    artwork.fit_artwork_cached(make_art(2, 2), (4, 4))
