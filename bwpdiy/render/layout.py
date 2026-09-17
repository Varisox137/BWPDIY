"""布局配置加载：assets/layout.json 优先，缺省回退包内 default_layout.json。

布局 schema 见 docs/terminology.md「布局配置」。
"""

import json
import warnings
from collections import Counter
from pathlib import Path

_DEFAULT = Path(__file__).with_name("default_layout.json")

# 可按类型不同的键（位置/内容类）；其余数值字段为尺寸类，跨类型必须一致
_PER_TYPE_KEYS = {"pos", "kind", "field", "icon", "icon_neg", "signed", "style",
                  "font", "wrap", "polygon"}


def _freeze(value):
    """列表/数值统一成可哈希值（num_offset/font_range 等列表型尺寸字段参与比较）。"""
    if isinstance(value, list):
        return tuple(value)
    return value


def _normalize_size_fields(layouts: dict) -> None:
    """同名元素/文本区的尺寸类字段跨类型归一：多数值优先，平票取先出现类型，不一致告警。"""
    groups: dict[str, dict[str, list]] = {}  # 元素名 -> 字段 -> [(类型, 冻结值)]
    for section in ("elements", "text_regions"):
        for card_type, type_layout in layouts.items():
            if not isinstance(type_layout, dict):
                continue
            for name, item in (type_layout.get(section) or {}).items():
                if not isinstance(item, dict):
                    continue
                for key, value in item.items():
                    if key in _PER_TYPE_KEYS or not isinstance(value, (int, float, list)):
                        continue
                    slot = groups.setdefault(f"{section}.{name}", {}).setdefault(key, [])
                    slot.append((card_type, _freeze(value)))
    for group_name, fields in groups.items():
        for key, entries in fields.items():
            counts = Counter(v for _, v in entries)
            if len(counts) <= 1:
                continue
            top = counts.most_common()
            best = top[0][1]
            winners = [v for v, c in top if c == best]
            # 平票取布局表中先出现类型的值
            chosen = next(v for _, v in entries if v in winners)
            warnings.warn(
                f"布局尺寸类字段跨类型不一致已归一: {group_name}.{key} "
                f"取值 {sorted(winners)!r} → {chosen!r}", stacklevel=2)
            for card_type, type_layout in layouts.items():
                item = (type_layout.get(group_name.split(".")[0]) or {}).get(
                    group_name.split(".", 1)[1])
                if item is not None and key in item:
                    item[key] = list(chosen) if isinstance(item[key], list) else chosen


def load_layouts(assets_dir: Path) -> dict:
    """加载完整布局表（6 类型）。assets_dir/layout.json 优先，缺失回退包内默认。"""
    path = Path(assets_dir) / "layout.json"
    if not path.is_file():
        path = _DEFAULT
    layouts = json.loads(path.read_text(encoding="utf-8"))
    _normalize_size_fields(layouts)
    return layouts


def get_type_layout(layouts: dict, card_type: str) -> dict:
    """取单类型布局 {"elements": ..., "text_regions": ...}。"""
    if card_type not in layouts:
        raise ValueError(f"布局缺失: {card_type}")
    return layouts[card_type]
