from PIL import Image

from bwpdiy.render.artwork import fit_artwork, rotate_artwork


def make_art(w=800, h=600):
    return Image.new("RGBA", (w, h), (200, 100, 50, 255))


def test_fit_cover_and_size():
    out = fit_artwork(make_art(), (512, 512))
    assert out.size == (512, 512)
    # cover：800x600 → 缩放 512/600，宽 683 ≥ 512


def test_fit_scale_enlarges():
    # scale 放大后裁剪窗口左移空间变大，不报错且尺寸不变
    out = fit_artwork(make_art(), (512, 512), scale=1.5)
    assert out.size == (512, 512)


def test_fit_offset_shifts_window():
    # 用左右两半不同颜色的图验证 offset 平移裁剪窗口
    img = Image.new("RGBA", (1024, 512), (255, 0, 0, 255))
    for x in range(512, 1024):
        for y in range(512):
            img.putpixel((x, y), (0, 0, 255, 255))
    left = fit_artwork(img, (512, 512), offset_x=-256)
    right = fit_artwork(img, (512, 512), offset_x=256)
    assert left.getpixel((10, 256)) == (255, 0, 0, 255)
    assert right.getpixel((502, 256)) == (0, 0, 255, 255)


def test_fit_offset_clamped():
    out = fit_artwork(make_art(600, 600), (512, 512), offset_x=99999)
    assert out.size == (512, 512)  # 钳制不抛异常


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
