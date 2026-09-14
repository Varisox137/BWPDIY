"""卡面渲染管线（M1 起逐步实现）。

合成顺序（自底向上，术语见 docs/terminology.md）：
卡图 artwork → 蒙版 mask → 牌框 frame（版型 low/high，框品 norm）→
等级标 level_badge（base → evolve_star → level_num）→
稀有度标 / 派系标 / 数值标 → 卡名 → 描述文本。
"""

from pathlib import Path

from PIL import Image

CARD_SIZE = (307, 546)


def render_card(card: dict, assets_dir: Path) -> Image.Image:
    """渲染单张完整卡面，返回 PIL Image（CARD_SIZE）。

    card: 校验后的卡牌 dict（引擎段 + artwork 渲染段）。
    assets_dir: 美术资源目录（frames/masks/icons/factions/levels/rarity/fonts）。
    缺资源/缺字段时抛出带明确信息的异常，由调用方兜底。
    """
    raise NotImplementedError("M1 待实现")
