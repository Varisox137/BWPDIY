"""卡图（artwork）变换。"""

from PIL import Image


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
