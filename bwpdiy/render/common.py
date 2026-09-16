"""通用贴图工具。"""

from PIL import Image


def paste_centered(canvas: Image.Image, img: Image.Image,
                   center: tuple[int, int],
                   size: tuple[int, int] | None = None) -> Image.Image:
    """把 img 缩放至 size 后按中心点 center 贴到 canvas 上（居中对齐），返回新图。"""
    if size is None:
        size = img.size
    resized = img.resize(size, Image.Resampling.LANCZOS).convert("RGBA")
    out = canvas.copy()
    out.paste(resized, (center[0] - size[0] // 2, center[1] - size[1] // 2), resized)
    return out
