"""卡牌 yaml schema 校验：按类型白名单（保存时执行），错误信息中文并指出字段名。

stat 数值字段口径与 render/badges.py `_STAT_MATRIX` 对齐（store 不 import render，手工同步）：
式神/形态 power+health、幻境 durability 为非负整数（plain）；
战斗 power+/shield+、觉醒法术 power+/health+ 为整数（signed）；表外组合一律非法。

框品 frame_variant（norm/blue/black/red）式神/战斗/法术/形态/幻境可携带（可选，缺省 norm；
式神牌框同形态）；协战恒 norm，携带属白名单之外字段。

协战另可携带可选布尔 duo_frame（双式神框渲染开关，缺省不绘制、不写进 yaml）。

式神另可携带可选 portrait 头像变换段（{offset_x, offset_y, scale, rotate} + 可选布尔
frame 头像框开关，全可缺省；协战双式神框取该式神卡图作头像时套用变换，口径同 artwork）。

标记扩展字段（均可选）：level_color 勾玉颜色（yellow/cyan/purple/red/blue/brown，缺省 yellow，
凡可带 level 的类型皆可携带）；式神另可携带可选 level（1-3，缺省无等级）与
faction_style 派系样式（1/2/3，缺省 2）；各 stat 字段可带 <field>_color 数值变色
（red/green/purple，缺省白）。
"""

from __future__ import annotations

CARD_TYPES = ("式神", "战斗", "法术", "形态", "幻境", "协战")
FACTIONS = ("红莲", "苍叶", "青岚", "紫岩", "无相")
RARITIES = ("N", "R", "SR", "SSR")
LEVELS = (1, 2, 3)
FRAME_VARIANTS = ("norm", "blue", "black", "red")
LEVEL_COLORS = ("yellow", "cyan", "purple", "red", "blue", "brown")
FACTION_STYLES = (1, 2, 3)

_COMMON_FIELDS = ("type", "name", "id", "description")
_SHIKIGAMI_ONLY = ("faction",)
# 式神专属可选渲染段字段：portrait 头像设置（{offset_x, offset_y, scale, rotate} 变换 +
# frame 头像框开关，全可缺省；协战双式神框引用该式神卡图作头像时使用；缺省 0/0/1.0/0/画框）
_SHIKIGAMI_RENDER_FIELDS = ("portrait",)
# 标记扩展字段：勾玉颜色（凡可带等级者皆可）、式神等级/派系样式
_MARK_FIELDS = ("level_color",)
_NON_SHIKIGAMI_FIELDS = ("level", "rarity", "special_type")
# 所属式神按名关联：常规非式神卡单引用 shikigami；协战双引用 shikigami1/shikigami2
_ASSIST_FIELDS = ("shikigami1", "shikigami2")
# 觉醒（evolve）仅战斗/法术/形态/幻境可携带；式神/协战不可
_EVOLVE_TYPES = ("战斗", "法术", "形态", "幻境")
# 协战专属可选布尔：双式神框（缺省不绘制、不写进 yaml）
_REINFORCE_FIELDS = ("duo_frame",)

_STATS_BY_TYPE = {
    "式神": ("power", "health"),
    "战斗": ("power+", "shield+"),
    "法术": ("power+", "health+"),  # 仅 evolve=true
    "形态": ("power", "health"),
    "幻境": ("durability",),
    "协战": (),
}
_SIGNED_STATS = ("power+", "shield+", "health+")
# 数值变色：每个 stat 字段可带 <field>_color 伴随字段（缺省白，不写进 yaml）；
# 红=debuff/受伤，绿=buff，紫=中毒（游戏内采样，见 render/badges.py STAT_COLORS）
STAT_VALUE_COLORS = ("red", "green", "purple")


class SchemaError(Exception):
    """卡牌数据不合 schema；errors 为中文错误列表（每条指出字段名）。"""

    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("\n".join(self.errors))


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _allowed_fields(ctype: str) -> set[str]:
    allowed = set(_COMMON_FIELDS) | set(_MARK_FIELDS)
    allowed |= {f"{f}_color" for f in _STATS_BY_TYPE[ctype]}  # 数值变色伴随字段
    if ctype == "式神":
        allowed |= set(_SHIKIGAMI_ONLY) | set(_STATS_BY_TYPE["式神"])
        allowed |= set(_SHIKIGAMI_RENDER_FIELDS)
        allowed.add("frame_variant")  # 式神牌框同形态，支持四框品（无觉醒）
        allowed |= {"level", "faction_style"}  # 标记扩展：式神可选等级与派系样式
    else:
        allowed |= set(_NON_SHIKIGAMI_FIELDS) | set(_STATS_BY_TYPE[ctype])
        allowed |= set(_ASSIST_FIELDS) if ctype == "协战" else {"shikigami"}
        if ctype == "协战":
            allowed |= set(_REINFORCE_FIELDS)
        if ctype in _EVOLVE_TYPES:
            allowed.add("evolve")
            allowed.add("frame_variant")
    return allowed


def validate_card(data) -> list[str]:
    """返回中文错误列表（空列表 = 合法）；一次报全，不短路。"""
    if not isinstance(data, dict):
        return ["卡牌数据必须是 yaml 映射"]
    errors: list[str] = []

    ctype = data.get("type")
    if "type" not in data:
        errors.append("缺少必填字段：type")
        return errors
    if ctype not in CARD_TYPES:
        errors.append(f"字段 type：非法卡牌类型「{ctype}」，须为 {'/'.join(CARD_TYPES)} 之一")
        return errors

    if not isinstance(data.get("name"), str) or not data["name"].strip():
        errors.append("字段 name：必填且必须是非空字符串")
    # id 可留空（缺省）：BWPro 按 id 取文件/卡图按 id 命名用；仅校验类型
    if "id" in data and not isinstance(data["id"], str):
        errors.append("字段 id：必须是字符串")

    for key in data:
        if key != "artwork" and key not in _allowed_fields(ctype):
            errors.append(f"字段 {key}：类型「{ctype}」白名单之外的字段")

    if ctype == "式神":
        for field in _SHIKIGAMI_ONLY + _STATS_BY_TYPE["式神"]:
            if field not in data:
                errors.append(f"缺少必填字段：{field}")
        faction = data.get("faction")
        if "faction" in data and faction not in FACTIONS:
            errors.append(f"字段 faction：非法派系「{faction}」，须为 {'/'.join(FACTIONS)} 之一")
        if "faction_style" in data and (not _is_int(data["faction_style"])
                                        or data["faction_style"] not in FACTION_STYLES):
            errors.append(f"字段 faction_style：派系样式必须是整数 "
                          f"{'/'.join(map(str, FACTION_STYLES))} 之一")
    else:
        rarity = data.get("rarity")
        if "rarity" not in data:
            errors.append("缺少必填字段：rarity")
        elif rarity not in RARITIES:
            errors.append(f"字段 rarity：非法稀有度「{rarity}」，须为 {'/'.join(RARITIES)} 之一")
        if "evolve" in data and not isinstance(data["evolve"], bool):
            errors.append("字段 evolve：必须是布尔值（true/false）")
        if "duo_frame" in data and not isinstance(data["duo_frame"], bool):
            errors.append("字段 duo_frame：必须是布尔值（true/false）")
        if "frame_variant" in data and data["frame_variant"] not in FRAME_VARIANTS:
            errors.append(
                f"字段 frame_variant：非法框品「{data['frame_variant']}」，"
                f"须为 {'/'.join(FRAME_VARIANTS)} 之一")
        for field in ("shikigami", *_ASSIST_FIELDS, "special_type", "description"):
            if field in data and not isinstance(data[field], str):
                errors.append(f"字段 {field}：必须是字符串")
    if "level" in data and (not _is_int(data["level"]) or data["level"] not in LEVELS):
        errors.append(f"字段 level：等级必须是整数 {'/'.join(map(str, LEVELS))} 之一")
    if "level_color" in data and data["level_color"] not in LEVEL_COLORS:
        errors.append(f"字段 level_color：非法勾玉颜色「{data['level_color']}」，"
                      f"须为 {'/'.join(LEVEL_COLORS)} 之一")
    for field in _STATS_BY_TYPE[ctype]:
        cfield = f"{field}_color"
        if cfield in data and data[cfield] not in STAT_VALUE_COLORS:
            errors.append(f"字段 {cfield}：非法数值颜色「{data[cfield]}」，"
                          f"须为 {'/'.join(STAT_VALUE_COLORS)} 之一")
    if ctype == "式神" and "description" in data and not isinstance(data["description"], str):
        errors.append("字段 description：必须是字符串")

    evolve = bool(data.get("evolve", False))
    for field in _STATS_BY_TYPE[ctype]:
        if field not in data:
            continue
        if ctype == "法术" and not evolve:
            errors.append(f"字段 {field}：仅觉醒法术牌（evolve: true）可携带数值")
            continue
        if not _is_int(data[field]):
            errors.append(f"字段 {field}：必须是整数")
        elif field not in _SIGNED_STATS and data[field] < 0:
            errors.append(f"字段 {field}：必须是非负整数")

    if "artwork" in data:
        errors += _validate_artwork(data["artwork"])
    if "portrait" in data:
        errors += _validate_transform(data["portrait"], "portrait")
    return errors


def _validate_transform(t, field: str) -> list[str]:
    """变换组宽松校验（portrait 头像设置）：结构形状+数值类型，字段全可缺省。
    另允许可选布尔 frame（头像框开关：是否绘制斜方框与派系标，缺省 true）。"""
    if not isinstance(t, dict):
        return [f"字段 {field}：必须是映射（offset_x/offset_y/scale/rotate/frame 全可缺省）"]
    errors = []
    for key in ("offset_x", "offset_y", "rotate"):
        if key in t and not _is_num(t[key]):
            errors.append(f"字段 {field}.{key}：必须是数字")
    if "scale" in t and (not _is_num(t["scale"]) or t["scale"] <= 0):
        errors.append(f"字段 {field}.scale：必须是正数")
    if "frame" in t and not isinstance(t["frame"], bool):
        errors.append(f"字段 {field}.frame：必须是布尔值（true/false）")
    for key in t:
        if key not in ("offset_x", "offset_y", "scale", "rotate", "frame"):
            errors.append(f"字段 {field}.{key}：未知字段")
    return errors


def _validate_artwork(artwork) -> list[str]:
    """渲染段宽松校验：只检查结构形状，不强制字段。"""
    if not isinstance(artwork, dict):
        return ["字段 artwork：必须是映射（如 artwork.images 图像列表）"]
    images = artwork.get("images")
    if images is None:
        return []
    if not isinstance(images, list):
        return ["字段 artwork.images：必须是图像列表"]
    errors: list[str] = []
    for i, item in enumerate(images):
        if not isinstance(item, dict):
            errors.append(f"字段 artwork.images[{i}]：必须是映射（path/offset_x/offset_y/scale）")
            continue
        if "path" in item and not isinstance(item["path"], str):
            errors.append(f"字段 artwork.images[{i}].path：必须是字符串")
        for field in ("offset_x", "offset_y", "rotate"):
            if field in item and not _is_num(item[field]):
                errors.append(f"字段 artwork.images[{i}].{field}：必须是数字")
        if "scale" in item and (not _is_num(item["scale"]) or item["scale"] <= 0):
            errors.append(f"字段 artwork.images[{i}].scale：必须是正数")
    return errors
