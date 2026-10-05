"""美术资源加载与缓存。"""

from pathlib import Path

from PIL import Image, ImageFont

FONT_FILES = {
    "name": "田氏颜体大字库2.0.ttf",
    "desc": "方正北魏楷书.ttf",
}


class AssetLibrary:
    """按命名约定加载 assets/ 资源，带内存缓存。

    图片以 RGBA 返回；调用方只读使用（paste/resize 不修改原图）。
    卡图缓存（artwork）设条目上限（LRU 近似，按插入序淘汰）：滚轮旋转每档
    一个角度键，不设上限会把大幅旋转图堆满内存；帧/字体等静态资源不限。
    """

    ARTWORK_CACHE_CAP = 6

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

    def level_num(self, n: int, color: str = "yellow") -> Image.Image:
        return self._img(f"levels/level_{n}_{color}.png")

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

    def stat_badge(self, stem: str) -> Image.Image:
        return self._img(f"stats/{stem}.png")

    def sign(self, name: str) -> Image.Image:
        return self._img(f"signs/{name}.png")

    def faction(self, color: str, style: int = 1) -> Image.Image:
        return self._img(f"factions/{color}_{style}.png")

    def icon(self, name: str) -> Image.Image:
        return self._img(f"icons/{name}.png")

    def duo(self, name: str) -> Image.Image:
        return self._img(f"duo/{name}.png")

    def mech(self, name: str) -> Image.Image:
        return self._img(f"mech/{name}.png")

    def artwork(self, path: Path, rotate: float = 0) -> tuple[tuple[int, int], Image.Image]:
        """用户卡图：按（路径, mtime, 旋转角）缓存；加载即绕中心旋转并扩展画布，
        后续缩放/偏移（fit_artwork）对缓存图进行，锚点始终为图片中心。
        返回 (原图尺寸, 旋转后图)：原图尺寸供 fit_artwork 作 cover 基准，
        保证旋转不改变内容视觉尺度。"""
        from bwpdiy.render.artwork import ARTWORK_MAX_PIXELS, rotate_artwork
        path = Path(path)
        key = ("artwork", str(path), path.stat().st_mtime, rotate)
        if key not in self._cache:
            img = Image.open(path)
            if img.width * img.height > ARTWORK_MAX_PIXELS:
                raise ValueError(f"卡图过大: {img.width}×{img.height} 超像素上限")
            orig_size = img.size
            self._cache[key] = (orig_size, rotate_artwork(img.convert("RGBA"), rotate))
            art_keys = [k for k in self._cache if k[0] == "artwork"]
            for old in art_keys[: max(0, len(art_keys) - self.ARTWORK_CACHE_CAP)]:
                del self._cache[old]
        return self._cache[key]

    def font(self, kind: str, size: int) -> ImageFont.FreeTypeFont:
        assert kind in FONT_FILES, f"未知字体种类: {kind}"
        key = ("font", kind, size)
        if key not in self._cache:
            path = self.root / "fonts" / FONT_FILES[kind]
            if not path.is_file():
                raise FileNotFoundError(f"字体缺失: {path}")
            self._cache[key] = ImageFont.truetype(str(path), size)
        return self._cache[key]


_LIBRARIES: dict[Path, AssetLibrary] = {}


def get_library(root: Path) -> AssetLibrary:
    """按资源根目录共享 AssetLibrary 实例（帧/字体/卡图缓存跨渲染复用）。

    编辑器的实时预览每次渲染都走这里，避免每请求重建库导致帧/字体重新
    读盘、卡图旋转缓存失效（预览延迟的主要来源）。资源根内容变化（素材
    替换）需重启进程生效。
    """
    key = Path(root).resolve()
    if key not in _LIBRARIES:
        _LIBRARIES[key] = AssetLibrary(key)
    return _LIBRARIES[key]
