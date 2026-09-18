from PIL import Image

from bwpdiy.render.artwork import fit_artwork


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
