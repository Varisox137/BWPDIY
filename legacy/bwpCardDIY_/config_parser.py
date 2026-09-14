import json
from typing import Dict, Any

class ConfigValidationError(Exception):
    pass

def validate_base_config(config: Dict[str, Any]):
    general_fields={
        'type': ['式神', '战斗', '法术', '形态', '幻境', '协战',],
        'frame_type': ['常规', '墨染', '琉璃', '百炼',],
        'name': str,
        'description': str,
        'image_path': str,
    }
    type_fields={
        '式神': {
            'faction': ['红莲', '苍叶', '青岚', '紫岩', '无相'],
            'power': int,
            'health': int,
        },
        '卡牌': {
            'level': int,
            'evolve': bool,
            'rarity': ['N', 'R', 'SR', 'SSR'],
            'shikigami': str,
            'special_type': str,
        },
        '战斗': {
            'power': int,
            'shield': int,
        },
        '法术觉醒': {
            'power': int,
            'health': int,
        },
        '形态': {
            'power': int,
            'health': int,
        },
        '幻境': {
            'durability': int,
        },
        '协战': {
            # 无独有参数，协战牌可有各自不同的等级、卡牌类型，协战牌的所属式神为两个式神
        }
    }

    for field, spec in general_fields.items():
        if field not in config:
            raise ConfigValidationError(f'缺少必要字段: {field}')

        if isinstance(spec, list):
            if config[field] not in spec:
                raise ConfigValidationError(f'字段{field}值不合法')
        elif not isinstance(config[field], spec):
            raise ConfigValidationError(f'字段{field}类型错误')

def load_config(config_path: str) -> Dict[str, Any]:
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config=json.load(f)
        validate_base_config(config)
        return config
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise ConfigValidationError(f'配置文件加载失败: {str(e)}')
