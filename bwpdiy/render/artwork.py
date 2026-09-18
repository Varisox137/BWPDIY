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
                scale: float = 1.0) -> Image.Image:
    """等比缩放至覆盖 target_size 后乘 scale，按 中心+offset 裁剪为 target_size。

    offset 单位为输出像素（右/下为正），越界钳制到可裁剪范围。
    """
    tw, th = target_size
    w, h = img.size
    cover = max(tw / w, th / h) * scale
    nw, nh = max(round(w * cover), 1), max(round(h * cover), 1)
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - tw) / 2 + offset_x
    top = (nh - th) / 2 + offset_y
    left = min(max(round(left), 0), max(nw - tw, 0))
    top = min(max(round(top), 0), max(nh - th, 0))
    return resized.crop((left, top, left + tw, top + th)).convert("RGBA")
