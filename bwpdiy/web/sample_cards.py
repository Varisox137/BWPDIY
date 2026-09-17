"""布局配置工具的预览样卡（六类型）。"""

from pathlib import Path

_ART = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "sample_art.png"

SAMPLE_CARDS: dict[str, dict] = {
    "式神": {"type": "式神", "name": "绯焰剑士", "faction": "红莲", "power": 3, "health": 4,
            "description": "当绯焰剑士攻击时，若本回合你已使用过战斗牌，本次攻击获得+1力量。"},
    "战斗": {"type": "战斗", "name": "裂地斩", "level": 1, "rarity": "R", "shikigami": "绯焰剑士",
            "power+": 1, "shield+": 1, "description": "获得贯通。"},
    "法术": {"type": "法术", "name": "觉醒·绯焰剑士", "level": 2, "rarity": "SR", "evolve": True,
            "shikigami": "绯焰剑士",
            "description": "觉醒：当绯焰剑士攻击时，若本回合你已使用过战斗牌，本次攻击获得+2力量与贯通；每回合第一次使用战斗牌后，随机对一个敌方式神造成2点伤害。"},
    "形态": {"type": "形态", "name": "炎凰之姿", "level": 3, "rarity": "SSR", "shikigami": "绯焰剑士",
            "power": 2, "health": 2, "description": "己方回合开始时，对所有敌方式神造成1点伤害。绯焰剑士气绝时，此形态不移除。"},
    "幻境": {"type": "幻境", "name": "熔岩幻境", "rarity": "N", "shikigami": "绯焰剑士",
            "durability": 6, "description": "回合结束时，获得1点鬼火。"},
    "协战": {"type": "协战", "name": "双刃协击", "rarity": "R", "shikigami": "绯焰剑士",
            "description": "协战：使本回合下一次攻击获得+1力量。"},
}

for _card in SAMPLE_CARDS.values():
    _card["_base_dir"] = str(_ART.parent)
    _card["artwork"] = {"images": [{"path": _ART.name}]}
