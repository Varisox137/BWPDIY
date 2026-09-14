# BWPDIY 术语表

定稿日期：2026-09-14。新增/变更术语须同步本表。

## 渲染层级（自底向上合成顺序）

| 术语 | 代码标识 | 说明 |
|---|---|---|
| 卡图 | artwork | 用户导入的插画，经变换与蒙版裁切；一张卡可有原画+多张异画 |
| 原画 | default art | `artwork.images[0]` |
| 异画 | alt art | `artwork.images[1:]`，仅立绘不同，卡面布局/形状不变；与原画 id 不同、共用一份 yaml |
| 蒙版 | mask | 卡图抠图形状，边缘高斯平滑（radius=1） |
| 牌框 | frame | 完整卡框，有 `high`/`low` 两种**版型**，区别在于卡图区域与文本区域所占比例（low 文本区更大，适合长文本）；MVP 默认 low，简体中文场景暂不提供选择 |
| 框品 | frame_variant | 常规(norm)/琉璃(blue)/墨染(black)/百炼(red)；一期固定 norm，二期开放 |
| 等级标 | level_badge | 三层自底向上叠加（无等级卡牌整体跳过）：① 底座 base（青黑色）→ ② 觉醒图案 evolve_star（五角星，仅觉醒牌叠加）→ ③ 等级数字 level_num（1–3 级 × 4 种颜色，对应对局 4 个位置） |
| 稀有度标 | rarity_mark | N/R/SR/SSR |
| 派系标 | faction_mark | 红莲/苍叶/青岚/紫岩/无相 |
| 数值标 | stat | 力量(power)/生命(health)/战斗牌护甲加成(shield)/幻境耐久(durability)，数值带正负号显示规则 |
| 卡名 | name_text | 田氏颜体大字库 |
| 描述文本 | desc_text | 方正北魏楷书，自动排版（从大到小试字号、自动换行、逐行居中） |

## 卡牌类型代码（沿用 legacy 资源前缀）

| 代码 | 类型 |
|---|---|
| `zd` | 战斗 |
| `fs` | 法术 |
| `xt` | 形态 |
| `hj` | 幻境 |
| `xz` | 协战 |
| （同 xt） | 式神——卡面外观形状同形态牌，渲染时蒙版/牌框沿用形态牌版型，差异化元素为派系标/力量/生命 |

## 数据与组织

| 术语 | 说明 |
|---|---|
| 式神项目 | library 下的一个目录 = 1 式神 + 8 卡 + 衍生物，含 `shikigami.yaml`、`cards/`、`images/` |
| 衍生物 | 项目内由卡效果派生的实体卡，存于 `cards/`，带派生标记 |
| 引擎段 | 卡牌 yaml 中与 BWPro 口径对齐的字段（type/name/level/rarity/description…） |
| 渲染段 | `artwork` 段：`images` 列表，每项 `path/offset_x/offset_y/scale` 全可缺省（默认 `<card_id>.png` / 0 / 0 / 1.0） |

## 二期术语（预留，一期不实现）

| 术语 | 说明 |
|---|---|
| 关键词上色 | 描述文本中 `[关键词]` 高亮着色 |
| 内嵌图标 | 描述文本中 `#xx` 语法插入小图标（#sm 生命、#hj 护甲、#ll 力量、#pj 破甲、#nl 能量、#nj 耐久、#zl 战力、#fl 乏力、#sj 赏金） |
