"""美术资源加载与缓存。"""

from pathlib import Path

from PIL import Image, ImageFont

FONT_FILES = {
    "name": "田氏颜体大字库.ttf",
    "desc": "方正北魏楷书.ttf",
}


class AssetLibrary:
    """按命名约定加载 assets/ 资源，带内存缓存。

    图片以 RGBA 返回；调用方只读使用（paste/resize 不修改原图）。
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

    def frame(self, type_code: str, variant: str = "norm") -> Image.Image:
        return self._img(f"frames/{type_code}_{variant}.png")

    def level_base(self) -> Image.Image:
        return self._img("levels/base.png")

    def level_star(self) -> Image.Image:
        return self._img("levels/evolve_star.png")

    def level_num(self, n: int) -> Image.Image:
        return self._img(f"levels/level_{n}_yellow.png")

    def rarity(self, rarity: str, variant: str = "norm") -> Image.Image:
        """稀有度花标：variant="reinforce" 用协战版；其余 {R}_{variant} 缺失回退 {R}；
        N 只有 N.png。"""
        if rarity == "N":
            return self._img("rarity/N.png")
        if variant == "reinforce":
            return self._img(f"rarity/reinforce_{rarity}.png")
        rel = f"rarity/{rarity}_{variant}.png"
        if not (self.root / rel).is_file():
            rel = f"rarity/{rarity}.png"
        return self._img(rel)

    def stat_badge(self, type_code: str, field: str) -> Image.Image:
        return self._img(f"stats/{type_code}_{field}.png")

    def sign(self, name: str) -> Image.Image:
        return self._img(f"signs/{name}.png")

    def faction(self, color: str, style: int = 1) -> Image.Image:
        return self._img(f"factions/{color}_{style}.png")

    def icon(self, name: str) -> Image.Image:
        return self._img(f"icons/{name}.png")

    def font(self, kind: str, size: int) -> ImageFont.FreeTypeFont:
        assert kind in FONT_FILES, f"未知字体种类: {kind}"
        key = ("font", kind, size)
        if key not in self._cache:
            path = self.root / "fonts" / FONT_FILES[kind]
            if not path.is_file():
                raise FileNotFoundError(f"字体缺失: {path}")
            self._cache[key] = ImageFont.truetype(str(path), size)
        return self._cache[key]
