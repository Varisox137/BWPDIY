from pathlib import Path

from PIL import Image

from bwpdiy.render.badges import _tint

NUMBERS = Path(__file__).resolve().parent.parent / "assets" / "numbers"


def sample_gradient_endpoints(img: Image.Image) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    img = img.convert("RGBA")
    luminance = img.convert("L")
    rows = []
    for y in range(img.height):
        pixels = [img.getpixel((x, y))[:3] for x in range(img.width)
                  if img.getpixel((x, y))[3] >= 200 and luminance.getpixel((x, y)) > 60]
        if pixels:
            rows.append(tuple(round(sum(pixel[channel] for pixel in pixels) / len(pixels))
                              for channel in range(3)))
    if not rows:
        raise ValueError("数字素材没有可采样的高亮像素")
    return rows[0], rows[-1]


def make_sign(color: str, name: str, size: tuple[int, int]) -> None:
    source = Image.open(NUMBERS / f"white_{name}.png").convert("RGBA")
    if source.size != size:
        canvas = Image.new("RGBA", size)
        canvas.alpha_composite(source, ((size[0] - source.width) // 2,
                                        (size[1] - source.height) // 2))
        source = canvas
    top, bottom = sample_gradient_endpoints(Image.open(NUMBERS / f"{color}_0.png"))
    _tint(source, top, bottom).save(NUMBERS / f"{color}_{name}.png")


def main() -> None:
    make_sign("orange", "minus", (21, 64))
    make_sign("purple", "plus", (27, 64))
    make_sign("purple", "minus", (21, 64))


if __name__ == "__main__":
    main()
