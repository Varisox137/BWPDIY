"""卡图（artwork）变换。"""

from PIL import Image

# 卡图像素上限（防解压炸弹：用户供图全量解码后才缩放/旋转）
ARTWORK_MAX_PIXELS = 64_000_000  # 8000×8000


def rotate_artwork(img: Image.Image, rotate: float) -> Image.Image:
    """绕图片中心旋转（正值=顺时针），画布扩展至容纳旋转结果（锚点恒为中心）。"""
    if rotate % 360:
        # PIL rotate 正值为逆时针，取负使用户语义为顺时针
        img = img.rotate(-rotate, expand=True, resample=Image.BICUBIC)
    return img


def fit_artwork(img: Image.Image, target_size: tuple[int, int],
                offset_x: float = 0, offset_y: float = 0,
                scale: float = 1.0,
                cover_base: tuple[int, int] | None = None) -> Image.Image:
    """等比缩放至覆盖 target_size 后乘 scale，按 中心+offset 裁剪为 target_size。

    offset 单位为输出像素：图像相对画布的位置，x/y 增大 = 图像向右/下移
    （v1.3.0 起；此前为取景窗语义、方向相反）。offset 不钳制：与画布同宽高的图
    （cover 无平移余量）也能自由挪动，平出画面的区域留透明（配合 scale 放大避免露底）。
    cover_base：cover 系数的基准尺寸（缺省=img.size）。旋转扩画布的场景传旋转前
    原图尺寸，保证内容视觉尺度不随旋转角漂移（缩放/裁剪仍作用于 img 本身）。
    """
    tw, th = target_size
    bw, bh = cover_base or img.size
    w, h = img.size
    cover = max(tw / bw, th / bh) * scale
    nw, nh = max(round(w * cover), 1), max(round(h * cover), 1)
    resized = img.convert("RGBA").resize((nw, nh), Image.Resampling.LANCZOS)
    # RGBA 下 crop 越界区域填透明（RGB 会填不透明黑），故先转 RGBA；
    # offset 为图像位置：图像右/下移 = 取景窗左/上移
    left = round((nw - tw) / 2 - offset_x)
    top = round((nh - th) / 2 - offset_y)
    return resized.crop((left, top, left + tw, top + th))
