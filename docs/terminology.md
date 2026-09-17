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
| 等级标 | level_badge | 三层自底向上叠加（无等级卡牌整体跳过）：① 底座 base（青黑色）→ ② 觉醒图案 evolve_star（五角星，仅觉醒牌叠加；觉醒 = evolve: true，仅战斗/法术/形态/幻境可携带，式神/协战不可）→ ③ 等级数字 level_num（1–3 级 × 4 种颜色，对应对局 4 个位置） |
| 稀有度标 | rarity_mark | N/R/SR/SSR |
| 派系标 | faction_mark | 红莲/苍叶/青岚/紫岩/无相 |
| 数值标 | stat | 力量(power)/生命(health)/战斗牌护甲加成(shield)/幻境耐久(durability)；正负号/0 值/类型适用规则见「元素」行 stat 适用矩阵 |
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
| 保留卡名 | `shikigami`：项目的式神卡固定存于 `shikigami.yaml`，可覆盖保存、不可删除；`cards/` 下不允许 `type: 式神` |
| 项目名/卡名合法性 | store 层保存时拒绝：空名、首尾空白、`.`/`..`、路径分隔符与 `<>:"\|?*`、控制字符、以点结尾（防路径注入）、Windows 保留设备名（CON/PRN/AUX/NUL/COM1–9/LPT1–9，大小写不敏感、按 `.` 前缀截断判定）；`cards/` 下字段 `name` 须与文件名一致 |
| 衍生物 | 项目内由卡效果派生的实体卡，存于 `cards/`，带派生标记 |
| 引擎段 | 卡牌 yaml 中与 BWPro 口径对齐的字段（type/name/level/rarity/description…） |
| 渲染段 | `artwork` 段：`images` 列表，每项 `path/offset_x/offset_y/scale` 全可缺省（默认 `<card_id>.png` / 0 / 0 / 1.0） |
| 布局配置 | `assets/layout.json`（出厂值入 git）+ 包内 `bwpdiy/render/default_layout.json` 回退；按 6 卡牌类型各一套「元素表 + 命名文本区」；同名元素的尺寸类字段（size/icon_size/font_size/num_offset/gap/margin/base_size 等除 pos 与内容类外的数值字段）跨类型必须一致，load 时不一致按多数值归一并告警（平票取先出现类型）；GUI 保存时的跨类型传播只镜像样式键白名单（size/icon_size/font_size/num_offset/gap/margin/base_size/star_size/num_size/font/style），kind/field/icon/icon_neg/pos/enabled 一律不镜像 |
| 元素 | 布局中的可定位渲染单元，kind ∈ level_badge（`enabled` per-type 开关，缺省 true；协战不提供开关）/ rarity_flank（卡名两侧对称双标：`gap`=默认半间距，短名时双标静态固定在 pos±gap；仅卡名渲染宽度超宽时按与卡名缘固定 `margin` 外移，即 effective=max(gap, name_width/2+margin)，margin 缺省 8）/ faction（`style` 选贴图样式，默认 2）/ stat（图标+数字一组，num_offset 相对偏移；符号（如有）+ 数字作为整体块，块的视觉中心对齐 num_pos；**stat 适用矩阵**为唯一口径（渲染/文本避让/GUI 输入同表，取代旧 signed 段）：式神·形态 力量+生命、幻境 耐久——无符号、非负（GUI 输入 min=0 约束，渲染不强制 clamp）、0 照常绘制；战斗 力量+/护甲+、法术觉醒 力量+/生命+——± 号按实际正负拼（负值同走压缩路径）、0 值整个角标不渲染；协战/非觉醒法术/其余表外 (type, field) 组合即使 card 带字段也不绘制、GUI 不提供输入框；符号离屏渲染取真墨迹、水平压至 0.65 宽后与数字墨迹中心竖直对齐贴入；`icon_neg` 负值自动换贴图——战斗护甲 shield+ 值<0 用破甲 pj，否则护甲 hj，不提供手动选择）/ text（卡名 name 与脚注 footer 点元素：pos 中心水平居中单行，font_size 固定无递减，footer 缺省 = “式神名-类型[/子类型]”小字）；贴图统一先裁 alpha 透明边、再等比 contain 进 size 框（size=内容可见尺寸，禁止非等比拉伸） |
| 文本区 | 命名矩形区域（仅 desc：`center`+`width`+`height`），自动换行、逐行居中、字号递减适配；显式 `\n` 强制断行（连续 `\n` 合并为一个，每段内再自动换行）；激活的 stat 元素作为障碍矩形参与 desc 逐行收窄（文本避让，0 值不渲染的 stat 不参与） |

## 二期术语（预留，一期不实现）

| 术语 | 说明 |
|---|---|
| 关键词上色 | 描述文本中 `[关键词]` 高亮着色 |
| 内嵌图标 | 描述文本中 `#xx` 语法插入小图标（#sm 生命、#hj 护甲、#ll 力量、#pj 破甲、#nl 能量、#nj 耐久、#zl 战力、#fl 乏力、#sj 赏金） |
