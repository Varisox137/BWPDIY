"""布局配置加载：用户布局优先，缺省回退包内 default_layout.json。

开发版用户文件为 assets/layout.json，正式版为 $HOME/.bwpdiy/layout.json。
布局 schema 见 docs/terminology.md「布局配置」。
"""

import copy
import json
from pathlib import Path

from bwpdiy.resources import layout_config_path

_DEFAULT = Path(__file__).with_name("default_layout.json")
FRAME_LAYOUT_TYPES = ("式神", "战斗", "法术", "形态", "幻境")
FRAME_LAYOUT_VARIANTS = ("blue", "black", "red")


def _scale_legacy_entity(value, key=None, element_name=None):
    if isinstance(value, dict):
        return {
            name: _scale_legacy_entity(
                item, name, name if key == "elements" else element_name)
            for name, item in value.items()
        }
    if isinstance(value, list):
        scaled = [_scale_legacy_entity(item, element_name=element_name) for item in value]
        if key == "num_offset" and len(value) == 2 and not isinstance(value[1], bool):
            if element_name in ("power", "health") and value[1] == 10:
                scaled[1] = 6
            elif element_name in ("combat_power", "shield") and value[1] == 9:
                scaled[1] = 5
        return scaled
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    return value * 1.5


def _fill_entity_defaults(entity: dict, default: dict) -> None:
    for key, value in default.items():
        if key not in entity:
            entity[key] = copy.deepcopy(value)
        elif isinstance(value, dict) and isinstance(entity[key], dict):
            _fill_entity_defaults(entity[key], value)


def _base_layout(type_layout: dict) -> dict:
    return {key: value for key, value in type_layout.items() if key != "frame_variants"}


def _materialize_frame_variants(layouts: dict) -> None:
    """把非常规框的稀疏覆盖补成编辑器使用的完整工作布局。"""
    for card_type in FRAME_LAYOUT_TYPES:
        type_layout = layouts.get(card_type)
        if not isinstance(type_layout, dict):
            continue
        configured = type_layout.get("frame_variants")
        if not isinstance(configured, dict):
            configured = {}
        base = _base_layout(type_layout)
        type_layout["frame_variants"] = {
            variant: merge_card_layout(base, configured.get(variant))
            for variant in FRAME_LAYOUT_VARIANTS
        }


def load_layouts(assets_dir: Path) -> dict:
    """加载运行环境的用户布局，缺失回退包内默认；独立段缺省时同样补齐。"""
    path = layout_config_path(Path(assets_dir))
    if not path.is_file():
        path = _DEFAULT
    layouts = json.loads(path.read_text(encoding="utf-8"))
    default = json.loads(_DEFAULT.read_text(encoding="utf-8"))
    for name in ("对局式神", "机制"):
        if name not in layouts and name in default:
            layouts[name] = copy.deepcopy(default[name])
    entity = layouts.get("对局式神")
    if isinstance(entity, dict):
        if "version" not in entity:
            layouts["对局式神"] = _scale_legacy_entity(entity)
            entity = layouts["对局式神"]
            entity["version"] = 2
        _fill_entity_defaults(entity, default["对局式神"])
    _materialize_frame_variants(layouts)
    return layouts


def get_type_layout(layouts: dict, card_type: str,
                    frame_variant: str = "norm") -> dict:
    """取类型与框品的有效布局；非常规框合并稀疏覆盖，不携带其他框配置。"""
    if card_type not in layouts:
        raise ValueError(f"布局缺失: {card_type}")
    type_layout = layouts[card_type]
    base = _base_layout(type_layout)
    if frame_variant == "norm" or card_type == "协战":
        return base
    variants = type_layout.get("frame_variants")
    if not isinstance(variants, dict):
        return base
    return merge_card_layout(base, variants.get(frame_variant))


def merge_card_layout(base: dict, override: dict | None) -> dict:
    """稀疏布局覆盖合并：深拷贝 base，按 section→名称→键两级合并 override。
    用于框品全局覆盖与卡牌 yaml 的单卡 layout 段；base 不被修改，畸形数据安全跳过。
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
