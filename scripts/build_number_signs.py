from pathlib import Path

from PIL import Image

from bwpdiy.render.badges import STAT_COLORS, _tint

NUMBERS = Path(__file__).resolve().parent.parent / "assets" / "numbers"


def make_sign(color: str, name: str, size: tuple[int, int]) -> None:
    source = Image.open(NUMBERS / f"white_{name}.png").convert("RGBA")
    if source.size != size:
        canvas = Image.new("RGBA", size)
        canvas.alpha_composite(source, ((size[0] - source.width) // 2,
                                        (size[1] - source.height) // 2))
        source = canvas
    endpoint_color = "yellow" if color == "orange" else color
    _tint(source, *STAT_COLORS[endpoint_color]).save(NUMBERS / f"{color}_{name}.png")


def main() -> None:
    make_sign("orange", "minus", (21, 64))
    make_sign("purple", "plus", (27, 64))
    make_sign("purple", "minus", (21, 64))


if __name__ == "__main__":
    main()
