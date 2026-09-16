"""美术资源加载与缓存。"""

from pathlib import Path

from PIL import Image, ImageFont

FONT_FILES = {
    "name": "田氏颜体大字库（卡牌名字体）.ttf",
    "desc": "方正北魏楷书（卡牌描述字体）.ttf",
}


class AssetLibrary:
    """按命名约定加载 assets/ 资源，带内存缓存。

    图片以 RGBA 返回（蒙版为 L）；调用方只读使用（paste/resize 不修改原图）。
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self._cache: dict[tuple, object] = {}

    def _img(self, rel: str, mode: str = "RGBA") -> Image.Image:
        key = ("img", rel)
        if key not in self._cache:
            path = self.root / rel
            if not path.is_file():
                raise FileNotFoundError(f"美术资源缺失: {path}")
            self._cache[key] = Image.open(path).convert(mode)
        return self._cache[key]

    def frame(self, type_code: str, variant: str = "norm", splitter: str = "low") -> Image.Image:
        return self._img(f"frames/frame_{type_code}_{variant}_{splitter}.png")

    def mask(self, type_code: str, splitter: str = "low") -> Image.Image:
        return self._img(f"masks/mask_{type_code}_{splitter}.png", mode="L")

    def level_base(self) -> Image.Image:
        return self._img("levels/base.png")

    def level_star(self) -> Image.Image:
        return self._img("levels/star.png")

    def level_num(self, color: str, n: int) -> Image.Image:
        return self._img(f"levels/{color}_{n}.png")

    def rarity(self, rarity: str) -> Image.Image:
        return self._img(f"rarity/{rarity}.png")

    def faction(self, color: str, style: int = 1) -> Image.Image:
        suffix = "" if color == "blue" and style == 1 else f"_{style}"
        return self._img(f"factions/{color}{suffix}.png")

    def icon(self, name: str, size: str = "l") -> Image.Image:
        return self._img(f"icons/{name}_{size}.png")

    def font(self, kind: str, size: int) -> ImageFont.FreeTypeFont:
        assert kind in FONT_FILES, f"未知字体种类: {kind}"
        key = ("font", kind, size)
        if key not in self._cache:
            path = self.root / "fonts" / FONT_FILES[kind]
            if not path.is_file():
                raise FileNotFoundError(f"字体缺失: {path}")
            self._cache[key] = ImageFont.truetype(str(path), size)
        return self._cache[key]
