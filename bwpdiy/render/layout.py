"""布局配置加载：assets/layout.json 优先，缺省回退包内 default_layout.json。

布局 schema 见 docs/terminology.md「布局配置」。
"""

import json
from pathlib import Path

_DEFAULT = Path(__file__).with_name("default_layout.json")


def load_layouts(assets_dir: Path) -> dict:
    """加载完整布局表（6 类型）。assets_dir/layout.json 优先，缺失回退包内默认。"""
    path = Path(assets_dir) / "layout.json"
    if not path.is_file():
        path = _DEFAULT
    return json.loads(path.read_text(encoding="utf-8"))


def get_type_layout(layouts: dict, card_type: str) -> dict:
    """取单类型布局 {"elements": ..., "text_regions": ...}。"""
    if card_type not in layouts:
        raise ValueError(f"布局缺失: {card_type}")
    return layouts[card_type]
