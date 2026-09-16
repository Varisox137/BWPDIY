"""文本层：卡名与描述文本的自动排版（从大到小试字号、自动换行、逐行居中）。"""

from PIL import Image, ImageDraw, ImageFont

from bwpdiy.render import layout
from bwpdiy.render.assets import AssetLibrary


def layout_lines(text: str, font: ImageFont.FreeTypeFont,
                 max_width: int) -> list[str]:
    """逐字符贪心换行；\\n 强制换行。"""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for ch in paragraph:
            if current and font.getlength(current + ch) > max_width:
                lines.append(current)
                current = ch
            else:
                current += ch
        lines.append(current)
    return lines


def _fit(box: tuple[int, int, int, int], kind: str,
         font_range: tuple[int, int], lib: AssetLibrary,
         wrap: bool, text: str):
    """从大到小试字号，返回 (font, lines)。wrap=False 时不换行（卡名）。"""
    x0, y0, x1, y1 = box
    max_w, max_h = x1 - x0, y1 - y0
    max_size, min_size = font_range
    for size in range(max_size, min_size - 1, -1):
        font = lib.font(kind, size)
        lines = layout_lines(text, font, max_w) if wrap else [text]
        line_h = font.getbbox("国Ag")[3] - font.getbbox("国Ag")[1] + 4
        if wrap and line_h * len(lines) > max_h:
            continue
        if not wrap and font.getlength(text) > max_w:
            continue
        return font, lines
    font = lib.font(kind, min_size)
    lines = layout_lines(text, font, max_w) if wrap else [text]
    return font, lines


def _draw_lines(canvas: Image.Image, box, font, lines, fill) -> Image.Image:
    out = canvas.copy()
    draw = ImageDraw.Draw(out)
    x0, y0, x1, y1 = box
    line_h = font.getbbox("国Ag")[3] - font.getbbox("国Ag")[1] + 4
    total_h = line_h * len(lines)
    y = y0 + (y1 - y0 - total_h) / 2
    for line in lines:
        draw.text(((x0 + x1) / 2, y + line_h / 2), line, font=font,
                  anchor="mm", fill=fill)
        y += line_h
    return out


def draw_name(canvas: Image.Image, lib: AssetLibrary, name: str) -> Image.Image:
    font, lines = _fit(layout.NAME_BOX, "name", layout.NAME_FONT_RANGE,
                       lib, wrap=False, text=name)
    return _draw_lines(canvas, layout.NAME_BOX, font, lines, layout.TEXT_FILL)


def draw_description(canvas: Image.Image, lib: AssetLibrary,
                     text: str) -> Image.Image:
    font, lines = _fit(layout.DESC_BOX, "desc", layout.DESC_FONT_RANGE,
                       lib, wrap=True, text=text)
    return _draw_lines(canvas, layout.DESC_BOX, font, lines, layout.TEXT_FILL)
