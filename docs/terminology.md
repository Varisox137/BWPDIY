# BWPDIY 术语表

定稿日期：2026-09-14。v1.0 修订：2026-09-18（PSD 素材替换/四框品/新合成管线/扩展选项）。新增/变更术语须同步本表。

## 渲染层级（自底向上合成顺序）

| 术语 | 代码标识 | 说明 |
|---|---|---|
| 卡图 | artwork | 用户导入的插画，经变换后叠加于牌框之下；一张卡可有原画+多张异画 |
| 原画 | default art | `artwork.images[0]` |
| 异画 | alt art | `artwork.images[1:]`，仅立绘不同，卡面布局/形状不变；与原画 id 不同、共用一份 yaml |
| ~~蒙版~~ | ~~mask~~ | **v1.0 废弃**：牌框卡图区天然透明，合成顺序改为 卡图→叠牌框→裁框外内容，不再需要蒙版抠图；旧 masks 封存 `assets/legacy/masks/` |
| 牌框 | frame | 完整卡框（卡图区透明），资源 `frames/{form,combat,spell,field,reinforce}_{框品}.png`（协战仅 norm），PSD 导出经预处理（裁 alpha bbox→等比缩至高 512→居中贴 512×512 透明画布）；版型 `high`/`low` 概念废弃（PSD 框即官方定版） |
| 框品 | frame_variant | 常规(norm)/琉璃(blue)/墨染(black)/百炼(red)；v1.0 开放——卡牌 yaml 可选字段 `frame_variant`（缺省 norm，仅战斗/法术/形态/幻境可携带），按框品自动切换牌框/稀有度贴图/文字颜色 |
| 等级标 | level_badge | 三层自底向上叠加（无等级卡牌整体跳过）：① 底座 `levels/base.png`（勾玉底框）→ ② 觉醒图案 `levels/evolve_star.png`（五角星金底，仅觉醒牌；觉醒 = evolve: true，仅战斗/法术/形态/幻境可携带，式神/协战不可）→ ③ 勾玉层 `levels/level_{1,2,3}_yellow.png`（官方勾玉个数制，默认黄色；四色=黄/青/紫/红二期染色生成，BWPro 对战四位己方式神渲染用，另 blue/brown 两色保留生成） |
| 稀有度标 | rarity_mark | N/R/SR/SSR，资源 `rarity/{R,SR,SSR}{,_blue,_red}.png`（罕贵度整带裁单枚花标；black 框品回退 norm 版）+ `rarity/reinforce_{R,SR,SSR}.png`（协战专版：蓝=R/紫=SR/金=SSR）+ `rarity/N.png`（legacy 图，仅「扩展选项」启用时可选） |
| 派系标 | faction_mark | 红莲 red/苍叶 green/青岚 blue/紫岩 purple/无相；式神卡大标沿用 legacy 三变体 `factions/{color}_{1,2,3}.png`（style 默认 2）；`icons/faction_{color}{,_black}.png` 小标为二期内嵌图标备用 |
| 数值标 | stat | 力量(power)/生命(health)/战斗牌护甲加成(shield)/幻境耐久(intensity)；角标贴图按类型分图 `stats/{code}_{field}.png`（负护甲自动换 `stats/combat_fragile_2.png` 破甲图，变体 1/2 可选默认 2）；正负号贴图 `signs/{plus,minus}.png`（不经数字字体）；适用矩阵见「元素」行 |
| 卡名 | name_text | 田氏颜体大字库 |
| 描述文本 | desc_text | 方正北魏楷书，自动排版（从大到小试字号、自动换行、逐行居中、文本块竖直居中）；文字颜色按框品（`FRAME_TEXT_FILL`，取色自官方模板文字样本：norm 深色/black 金色/blue·red 浅色） |
| 成品导出 | 512 顶格适配 | 最终卡图按整卡 tightest alpha bbox 裁剪后等比缩放至高 512（**上下顶格、左右居中留白**）贴回 512×512 导出（宽溢出则退为按宽适配、上下留白）；布局预览（crop=False）仍返回 512 全画布合成结果 |
| 轮廓裁剪 | silhouette clip | 叠框前牌框先做 alpha 阈值清理（`FRAME_ALPHA_THRESHOLD=192`，删去 PSD 导出框缘外/窗内低透明度散点，v1.0.2；经 T=0/32/64/128/192 对比，差异仅为边缘 1-2px 抗锯齿，不伤内部装饰），再删去**牌框实际形状**之外的所有像素（框 alpha==0 且与画布边缘连通的区域；卡图窗被框缘完整包围不受影响）——矩形 bbox 裁剪会残留框形外卡图（v1.0.1 修复）；元素在轮廓裁剪之后绘制，探出框缘的等级标等不受影响 |

## 卡牌类型代码（v1.0 起对齐 BWPro 英文定名）

| 代码 | 类型 |
|---|---|
| `combat` | 战斗 |
| `spell` | 法术 |
| `form` | 形态 |
| `field` | 幻境 |
| `reinforce` | 协战 |
| （同 form） | 式神——卡面外观形状同形态牌，差异化元素为派系标/力量/生命 |

拼音首字母→术语映射保留（二期 `#xx` 内嵌图标语法用）：`xt→form` `zd→combat` `fs→spell` `hj→field` `xz→reinforce`；`ll→power` `sm→health` `hj→shield` `pj→fragile` `nl→energy` `nj→intensity` `zl→combat_power` `fl→weak` `sj→bounty`（数值英文名单对齐 BWPro：破甲=fragile、幻境耐久=intensity、战力=combat_power、乏力=weak、赏金=bounty）。

## 数据与组织

| 术语 | 说明 |
|---|---|
| 式神项目 | library 下的一个目录 = 1 式神 + 8 卡 + 衍生物，含 `shikigami.yaml`、`cards/`、`images/` |
| 保留卡名 | `shikigami`：项目的式神卡固定存于 `shikigami.yaml`，可覆盖保存、不可删除；`cards/` 下不允许 `type: 式神` |
| 项目名/卡名合法性 | store 层保存时拒绝：空名、首尾空白、`.`/`..`、路径分隔符与 `<>:"\|?*`、控制字符、以点结尾（防路径注入）、Windows 保留设备名（CON/PRN/AUX/NUL/COM1–9/LPT1–9，大小写不敏感、按 `.` 前缀截断判定）；`cards/` 下字段 `name` 须与文件名一致 |
| 衍生物 | 项目内由卡效果派生的实体卡，存于 `cards/`，带派生标记 |
| 引擎段 | 卡牌 yaml 中与 BWPro 口径对齐的字段（type/name/level/rarity/description…；v1.0 增可选 `frame_variant`） |
| 渲染段 | `artwork` 段：`images` 列表，每项 `path/offset_x/offset_y/scale` 全可缺省（默认 `<card_id>.png` / 0 / 0 / 1.0） |
| 布局配置 | `assets/layout.json`（出厂值入 git）+ 包内 `bwpdiy/render/default_layout.json` 回退；按 6 卡牌类型各一套「元素表 + 命名文本区」；同名元素的尺寸类字段（size/icon_size/font_size/num_offset/sign_offset/sign_size/stroke_width/gap/margin/base_size 等除 pos 与内容类外的数值字段）跨类型必须一致，load 时不一致按多数值归一并告警（平票取先出现类型）；GUI 保存时的跨类型传播只镜像样式键白名单，kind/field/pos/enabled 一律不镜像 |
| 元素 | 布局中的可定位渲染单元，kind ∈ level_badge（`enabled` per-type 开关，缺省 true；协战不提供开关）/ rarity_flank（卡名两侧对称双标：`gap`=默认半间距，短名时双标静态固定在 pos±gap；仅卡名渲染宽度超宽时按与卡名缘固定 `margin` 外移，即 effective=max(gap, name_width/2+margin)，margin 缺省 8）/ faction（`style` 选贴图样式，默认 2）/ stat（图标+数字一组，图标由 (卡牌类型, field) 推导 `stats/{code}_{field}.png`、负护甲自动换破甲图；num_offset 相对偏移；符号（如有，signs/plus|minus.png 贴图，sign_size 缩放、sign_offset 偏移）+ 数字作为整体块，块的视觉中心对齐 num_pos；数字白字黑描边（`stroke_width` 可配，默认 2）；**stat 适用矩阵**为唯一口径（渲染/文本避让/GUI 输入同表）：式神·形态 力量+生命、幻境 耐久——无符号、非负（GUI 输入 min=0 约束，渲染不强制 clamp）、0 照常绘制；战斗 力量+/护甲+、法术觉醒 力量+/生命+——± 号按实际正负贴图、0 值整个角标不渲染；协战/非觉醒法术/其余表外 (type, field) 组合即使 card 带该字段也不绘制、GUI 不提供输入框）/ text（卡名 name 与脚注 footer 点元素：pos 中心水平居中单行，font_size 固定无递减，footer 缺省 = “式神名-类型[/子类型]”小字；颜色按框品）；贴图统一先裁 alpha 透明边、再等比 contain 进 size 框（size=内容可见尺寸，禁止非等比拉伸） |
| 文本区 | 命名矩形区域（仅 desc：`center`+`width`+`height`，可选 `obstacle_gap` 避让间距、缺省 4），自动换行、逐行居中、文本块竖直居中（先定字号与行数，再把文本块中心对齐区域中心）、字号递减适配；显式 `\n` 强制断行（连续 `\n` 合并为一个，每段内再自动换行）；激活的 stat 元素（0 值不渲染的 stat 不参与）在透明层单独渲染取 alpha **真实墨迹**作避让掩膜（非组件矩形 bbox；图标走 alpha_composite 保真源 alpha，不吃默认 paste 的 alpha 平方）：每个描述行 y 带内被占用的 x 区间向外扩 `obstacle_gap` 后逐行收窄，保证描述墨迹与角标墨迹相距 ≥ gap（y 带同样竖直外扩 gap 查询） |
| 扩展选项 | 顶栏勾选框组（localStorage `bwpdiy_ext_options` 持久化，默认全部不勾选、对应功能不对普通使用者开放）：① 手动调整布局（不勾选则隐藏布局设置 tab）② 允许 N 稀有度（稀有度下拉默认 R/SR/SSR）③ 勾玉四色（disabled 置灰预留，二期） |
| 素材归档 | `assets/legacy/` = 被替换的旧位图资产封存（旧 frames/icons/levels/masks/rarity，含 unprocessed 框品/high 版型原图留待以后）；`assets/psd_export/` = PSD 图层原始镜像档案（中文名，不作运行时资源）；两者均不进 exe（build_exe.py 排除）；运行时资产由 `scripts/import_psd_assets.py` 从 psd_export 再生成 |

## 二期术语（预留，一期不实现）

| 术语 | 说明 |
|---|---|
| 关键词上色 | 描述文本中 `[关键词]` 高亮着色 |
| 内嵌图标 | 描述文本中 `#xx` 语法插入小图标（拼音首字母代码→`icons/{术语}.png` 映射见「卡牌类型代码」节） |
| 勾玉四色 | `levels/level_{1,2,3}_{yellow,cyan,purple,red}.png` 染色生成（另 blue/brown 保留），BWPro 对战四位己方式神渲染用；届时与 legacy 6 色数字版比对取舍 |
| 协战双式神头像框 | 双菱形头像+派系小标（素材在 `psd_export/协战/式神头像框/`）；仅 BWPro 卡组构筑/对战详情用，DIY 工具一般不绘制 |
