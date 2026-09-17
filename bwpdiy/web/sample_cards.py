"""布局配置工具的预览样卡（六类型真实卡牌）。

卡名/式神名/描述/数值抄自 BWPro 原版卡牌数据文档 card_data_raw.md（唯一事实来源），
描述中的 [关键词]/{效果} 标记为文档记号，游戏内不显示，抄录时去除。
卡图统一用 tests/fixtures/sample_art.png（仅作布局预览底图）。
"""

from pathlib import Path

_ART = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "sample_art.png"

SAMPLE_CARDS: dict[str, dict] = {
    # 100307 山风 苍叶 3/4（20200624）
    "式神": {"type": "式神", "name": "山风", "faction": "苍叶", "power": 3, "health": 4,
            "description": "倒计时3：发起一次攻击，本次战斗获得不屈。"},
    # 铃鹿御前 08 义道 SSR 3 战斗 -1/+2（20200520）
    "战斗": {"type": "战斗", "name": "义道", "level": 3, "rarity": "SSR", "shikigami": "铃鹿御前",
            "power+": -1, "shield+": 2,
            "description": "贯通，连击。对有破甲的式神造成双倍伤害。"},
    # 山风 08 觉醒·山风 SSR 3 法术/觉醒 +1/+1（20200624）
    "法术": {"type": "法术", "name": "觉醒·山风", "level": 3, "rarity": "SSR", "evolve": True,
            "shikigami": "山风", "power+": 1, "health+": 1,
            "description": "觉醒：倒计时3：发起一次攻击，本次战斗免疫战斗伤害。"
                          "你的牌对山风以外的未气绝己方式神造成的减少倒计时效果对山风造成等量效果。"
                          "（山风气绝时有效）"},
    # 辉夜姬 08 竹取物语 SSR 3 形态 5/5（20200624）
    "形态": {"type": "形态", "name": "竹取物语", "level": 3, "rarity": "SSR", "shikigami": "辉夜姬",
            "power": 5, "health": 5,
            "description": "每个回合结束时，随机召唤一个辉夜姬的幻境。"
                          "若辉夜姬的幻境耐久>=20，每当辉夜姬受到伤害时，"
                          "改为扣除辉夜姬幻境等量的耐久（最多降低5耐久）。"},
    # 辉夜姬 01 燕子安贝 R 1 幻境 5（20200624）
    "幻境": {"type": "幻境", "name": "燕子安贝", "level": 1, "rarity": "R", "shikigami": "辉夜姬",
            "durability": 5,
            "description": "自己回合结束时，使所有己方角色各恢复1点生命，使所有其他己方幻境各获得1耐久。"
                          "若此牌耐久>=10，敌方回合结束时，再触发上述效果一次。"},
    # 山风 21 鸮羽共鸣 SSR 1 协战（未加入）
    "协战": {"type": "协战", "name": "鸮羽共鸣", "level": 1, "rarity": "SSR",
            "footer": "山风×薰-协战",
            "description": "选择使用一项：山风-庇羽；薰-鸮鸣"},
}

for _card in SAMPLE_CARDS.values():
    _card["_base_dir"] = str(_ART.parent)
    _card["artwork"] = {"images": [{"path": _ART.name}]}
