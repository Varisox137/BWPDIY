"""通用贴图工具。"""

from PIL import Image


def paste_centered(canvas: Image.Image, img: Image.Image,
                   center: tuple[int, int],
                   size: tuple[int, int] | None = None,
                   composite: bool = False) -> Image.Image:
    """把 img 缩放至 size 后按中心点 center 贴到 canvas 上（居中对齐），返回新图。

    composite=True 用 alpha_composite 语义（源 alpha 保真）；缺省 Image.paste 把
    alpha 当普通通道混合（透明层上源 alpha 被平方）——实卡绘制沿用缺省行为，
    composite 仅供文本避让掩膜采集等需要源 alpha 保真的场景。
    """
    if size is None:
        size = img.size
    resized = img.resize(size, Image.Resampling.LANCZOS).convert("RGBA")
    box = (center[0] - size[0] // 2, center[1] - size[1] // 2)
    out = canvas.copy()
    if composite:
        out.alpha_composite(resized, box)
    else:
        out.paste(resized, box, resized)
    return out
