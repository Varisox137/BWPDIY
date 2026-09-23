"""布局配置加载：assets/layout.json 优先，缺省回退包内 default_layout.json。

布局 schema 见 docs/terminology.md「布局配置」。
"""

import copy
import json
import warnings
from collections import Counter
from pathlib import Path

_DEFAULT = Path(__file__).with_name("default_layout.json")

# 可按类型不同的键（位置/内容类）；其余数值字段为尺寸类，跨类型必须一致
# group_offset：四类带符号数值的符号数字整体偏移，按类型×角标各自微调，不归一
# fragile_pos：战斗破甲角标坐标（与护甲分离，位置类不归一）
# center_offset：desc 文本区居中锚点偏移（视觉居中基准平移，区域边界不变），per-type
_PER_TYPE_KEYS = {"pos", "center", "kind", "field",
                  "style", "font", "wrap", "group_offset", "fragile_pos",
                  "center_offset"}


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
                    # bool 是 int 子类，须先排除：bool 属内容类字段（如 wrap），
                    # 被误当尺寸类会在新增 bool 字段时错误归一
                    if (key in _PER_TYPE_KEYS or isinstance(value, bool)
                            or not isinstance(value, (int, float, list))):
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
                # key=repr：手改出混合类型值（int 与 list 并存）时 sorted 直接比较会 TypeError
                f"取值 {sorted(winners, key=repr)!r} → {chosen!r}", stacklevel=2)
            for card_type, type_layout in layouts.items():
                item = (type_layout.get(group_name.split(".")[0]) or {}).get(
                    group_name.split(".", 1)[1])
                if item is not None and key in item:
                    if isinstance(item[key], list):  # 写回保持原 list 形态（含标量胜出时包装）
                        item[key] = list(chosen) if isinstance(chosen, (list, tuple)) else [chosen]
                    else:
                        item[key] = chosen


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


def merge_card_layout(base: dict, override: dict | None) -> dict:
    """单卡布局覆盖合并：深拷贝 base（该卡类型的全局布局），按 section→名称→键
    两级合并 override（卡牌 yaml 的 `layout` 稀疏覆盖段）。base 不被修改；
    override 缺 section、项非 dict 等畸形数据跳过（schema 已做形状校验，此处纵深防御）。
    """
    merged = copy.deepcopy(base)
    if not isinstance(override, dict):
        return merged
    for section in ("elements", "text_regions"):
        items = override.get(section)
        if not isinstance(items, dict):
            continue
        target = merged.setdefault(section, {})
        for name, item in items.items():
            if isinstance(item, dict):
                target.setdefault(name, {}).update(item)
    return merged
