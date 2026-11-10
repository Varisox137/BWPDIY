# PSD 素材 ↔ 现有 assets 对应表（v1.0 定稿 v4）

> 来源：`assets/百闻牌DIY模板整合（更新战力、乏力标识）BY 鹿倉暦.psd` + `assets/协战牌模板.psd`，
> 已导出至 `assets/psd_export/`（主 141 张 + 协战 44 张，topil() 直取图层像素）。
>
> v4 变更（用户批复）：命名对齐 BWPro 术语表（**协战=reinforce、破甲=fragile、幻境耐久=intensity、
> 战力=combat_power、乏力=weak**）；现有资产全部归档 `assets/legacy/`；协战框采用 PSD 版（仅 norm）；
> 式神卡大派系标沿用 legacy 三变体（不用 PSD 版）；最终导出按 tightest bbox 裁剪不留白边。
> 全部决策点已关闭，本表为实施依据。

## 0. 英文命名规范（对齐 BWPro `docs/terminology.md`）

| 概念 | 英文命名 | 拼音首字母映射（保留，二期 `#xx` 内嵌图标用） |
|---|---|---|
| 卡牌类型 | `form` 形态（式神共用）/ `combat` 战斗 / `spell` 法术 / `field` 幻境 / `reinforce` 协战 | `xt→form` / `zd→combat` / `fs→spell` / `hj→field` / `xz→reinforce` |
| 框品 | `norm` 常规 / `blue` 琉璃 / `black` 墨染 / `red` 百炼 | — |
| 派系 | `red` 红莲 / `green` 苍叶 / `blue` 青岚 / `purple` 紫岩 | — |
| 数值 | `power` 力量 / `health` 生命 / `shield` 护甲 / `fragile` 破甲 / `intensity` 幻境耐久 / `energy` 能量 / `combat_power` 战力 / `weak` 乏力 / `bounty` 赏金 | `ll→power` / `sm→health` / `hj→shield` / `pj→fragile` / `nl→energy` / `nj→intensity` / `zl→combat_power` / `fl→weak` / `sj→bounty` |
| 等级标四层 | `base` 底座 / `evolve` 新觉醒星 / `evolve_circle` 旧圆盘 / `level_<1,2,3>_yellow` 勾玉层 | — |

现行目标目录结构（2026-11 美术资源更新后）：

```
assets/
  frames/    {form,combat,spell,field,reinforce}_{norm,blue,red,black}.png（高 512 居中）
  levels/    base.png / evolve.png / evolve_circle.png（旧圆盘保留原画布配准）
             / level_{1,2,3}_{yellow,cyan,purple,red,blue,brown,greyblue,orange}.png（八色）
             （level_4_* / level_3_4_* 仅作备用命名，不接等级枚举、表单或渲染引用）
  rarity/    {R,SR,SSR}.png + {R,SR,SSR}_{blue,red}.png + N.png（仅扩展选项可选）
             （black 等缺失变体统一回退常规版，不保留 reinforce_* 专图）
  factions/  {red,green,blue,purple}_{1,2,3}.png（legacy 三变体，式神卡大派系标）
  stats/     power.png / health.png / shield.png / combat_fragile_{1,2}.png
             / intensity.png / energy.png / countdown.png / defeated_countdown.png
             / combat_power.png / weak.png（大卡与小卡战力/乏力均使用此目录）
  numbers/   {white,red,green,purple,orange}_{0..9,plus,minus}.png + white_inf.png
             （运行时 yellow 映射 orange；plus/minus 中三枚由脚本合成补齐）
  badges/    {加护,蚀印,缘结,诅咒,天晖,梦魇,无始无终,无穷无尽,未使用,多状态,已展示}.png
             （保留中文文件名，AssetLibrary 将内部英文状态代码映射到这些文件）
  icons/     {power,health,shield,fragile,energy,intensity,combat_power,weak,bounty}.png
             + faction_{red,green,blue,purple}_{1,2,3}.png（逐条目内嵌派系样式）
  mech/      frame_invocation_{3,4,5}.png / frame_skill_{3,4,5}.png / frame_seal.png
  fonts/     不变（两个 ttf；不再用于数字）
  legacy/    全部被替换的旧素材归档（frames/icons/levels/masks/rarity 旧图；不进 exe）
  psd_export/  PSD 图层原始镜像档案（中文名不动，不作运行时资源）
```

## A. 牌框（frames/）

| 现有资产 | PSD 素材 | 目标路径 |
|---|---|---|
| `frame_xt_norm_low.png`（式神/形态共用） | `卡框-基础_形态/基础.png` | `frames/form_norm.png` |
| （无） | `卡框-基础_形态/{琉璃光境,百炼,墨染}.png` | `frames/form_{blue,red,black}.png` |
| `frame_zd_norm_low.png` | `卡框-战斗/基础.png` | `frames/combat_norm.png` |
| （无） | `卡框-战斗/{琉璃光境,百炼,墨染}.png` | `frames/combat_{blue,red,black}.png` |
| `frame_fs_norm_low.png` | `卡框-法术/基础.png` | `frames/spell_norm.png` |
| （无） | `卡框-法术/{琉璃光境,百炼,墨染}.png` | `frames/spell_{blue,red,black}.png` |
| `frame_hj_norm_low.png` | `卡框-幻境/基础.png` | `frames/field_norm.png` |
| （无） | `卡框-幻境/{琉璃光境,百炼,墨染}.png` | `frames/field_{blue,red,black}.png` |
| `frame_xz_norm_low.png`（legacy 协战框） | PSD 常规框 + 后续补充的三种框品 | `frames/reinforce_{norm,blue,red,black}.png` |

说明：

- 预处理统一：裁 alpha bbox → 等比缩放至高 512 → 居中贴 512×512 透明画布
- 新合成顺序：**卡图 → 叠加牌框（卡图区天然透明，无需 mask）→ 轮廓裁剪（删去牌框实际形状外所有像素，v1.0.1 修复矩形 bbox 裁剪的残留）→
  叠加所有元素 → 导出按整卡 tightest alpha bbox 裁剪后等比缩放至高 512 贴回 512×512（上下顶格、左右留白）**
- `masks/` 五张全部废弃入 legacy
- legacy `frames/unprocessed/`（high 版型与框品原图）留待以后

## B. 等级标（levels/ → 勾玉组）

| 来源 | 现行目标路径 |
|---|---|
| `勾玉/勾玉-底框.png`、`勾玉/底框-觉醒.png` | `levels/base.png`、`levels/evolve.png` |
| `勾玉/一勾玉/二勾玉/三勾玉.png` | `levels/level_{1,2,3}_yellow.png`（PSD 导入脚本管理） |
| 本批八色位图资源 | `levels/level_{1,2,3}_{yellow,cyan,purple,red,blue,brown,greyblue,orange}.png` |

协战 PSD 内勾玉组与主 PSD 逐像素一致（已验证），去重只用一套。`level_4_*` 与 `level_3_4_*` 仅作备用命名，不接等级枚举、表单或渲染引用。

## C. 稀有度（rarity/）

| 来源 | 现行目标路径 |
|---|---|
| `罕贵度/{R,SR,SSR}.png`（整带裁左端单枚花标） | `rarity/{R,SR,SSR}.png` |
| `罕贵度/{R,SR,SSR} 琉璃光境.png` | `rarity/{R,SR,SSR}_blue.png` |
| `罕贵度/{R,SR,SSR} 百炼.png` | `rarity/{R,SR,SSR}_red.png` |
| legacy N.png | `rarity/N.png`，仅「扩展功能」启用时可选 |

- 间距逻辑维持“短卡名固定 gap、长卡名按 margin 自动外移”。
- black、reinforce 等变体没有专图时统一回退常规版；协战 PSD 花标仅留归档，不再生成运行时 `reinforce_*` 文件。

## D. 派系标

| 来源 | 现行目标路径 |
|---|---|
| legacy 三变体（12 张） | `factions/{color}_{1,2,3}.png`（式神卡大派系标） |
| 本批逐条目小标（12 张） | `icons/faction_{color}_{1,2,3}.png` |

卡牌与机制均可选 `inline_faction_style`（1/2/3，缺省 1），控制本条全部 `#hl/#cy/#ql/#zy` 小标；不再按墨染框自动切换文件。大标 `faction_style` 与小标字段相互独立。

## E. 数值角标与文本小图标

| 来源 | 现行目标路径 |
|---|---|
| `基础_形态-攻击`、`基础_形态-生命` | `stats/power.png`、`stats/health.png`（全类型共用） |
| `战斗-护甲`、`战斗-破甲`、`战斗-破甲1` | `stats/shield.png`、`stats/combat_fragile_{1,2}.png`（默认 2） |
| `幻境-数值/幻境` | `stats/intensity.png` |
| 本批状态与大角标资源 | `stats/{energy,countdown,defeated_countdown,combat_power,weak}.png` |
| `☆符号` 与新增战力乏力小图 | `icons/{power,health,shield,fragile,energy,intensity,combat_power,weak}.png` |
| 本批赏金小图 | `icons/bounty.png`，已接入描述 `#sj`；赏金大角标仍未实现 |

对局小卡的战力/乏力与大卡统一使用 `stats/` 大图标；仅描述文本 `#zl`/`#fl` 使用 `icons/` 小图。各数值组 `数值-*` 只作样式参考。

## F. 位图数字、符号与特殊状态

- 数字 0–9、正负号和永久气绝均使用位图：`numbers/{white,red,green,purple,orange}_{0..9,plus,minus}.png` + `numbers/white_inf.png`。
- `font_size` 表示单字源图缩放目标高度；多位数裁紧后按逐行墨迹最小间距拼接，带符号数字读取同色符号。运行时 yellow 映射 orange。
- `scripts/build_number_signs.py` 仅用于重建三枚合成符号：orange_minus、purple_plus、purple_minus；旧 signs 目录不再生成。
- 不再使用字体数字、程序渐变或描边绘制数值；布局遗留 `stroke_width` 仅作兼容校验字段。
- 角标保留中文文件名：`badges/{加护,蚀印,缘结,诅咒,天晖,梦魇,无始无终,无穷无尽,未使用,多状态,已展示}.png`，由 `AssetLibrary.BADGE_FILES` 映射内部英文状态代码。这些状态均可供大卡临时 status 使用，无等级卡也绘制；机制 seal 的 badge 仍仅 bless/eclipse。

## G. 字体与文字颜色

- `fonts/` 两个 ttf 保留给卡名与描述文字，不再用于数字。
- `文字-{基础,墨染,琉璃光境,百炼}/` 40 张 + `协战/文字颜色选取.png` 不入库——取样颜色写入渲染配置：
  - norm：深色字 / black（墨染）：金色字 / red·blue：浅色字

## H. 扩展素材

机制框使用 `mech/frame_invocation_{3,4,5}.png`、`mech/frame_skill_{3,4,5}.png` 与 `mech/frame_seal.png`；独立角标已移至 `badges/`。烹饪、文字描述-EX、卡牌标识 62px、卡背图等其余 PSD 素材继续留作归档备用。

## I. 协战专节

| PSD 素材 | 现行处置 |
|---|---|
| `协战牌框.png` + 后续补充的三种框品 | `frames/reinforce_{norm,blue,black,red}.png` |
| `稀有度/{蓝,紫,金}色.png` | 仅留 PSD 归档；运行时协战回退常规 R/SR/SSR 花标 |
| `勾玉/` 5 张 | 与主 PSD 逐像素一致，去重 |
| `式神头像框/` | 已接入 `duo/`，槽位 2 高光由 `highlight_1.png` 旋转派生 |
| `插图/蒙版底板.png`、`攻击值/生命值`、`特殊符号/`、`文字描述/`、`文字颜色选取.png` | 备用/取色参考 |

## J. webgui「扩展选项」栏

- 顶栏勾选框组，localStorage 持久化：手动调整布局与扩展功能。
- 扩展功能开放 N/无稀有度、等级 0/无等级、勾玉八色、式神大派系样式和卡牌/机制 `inline_faction_style` 控件；取消勾选只隐藏控件，不回退已保存字段。

## 决策点收尾（现行口径）

1. 协战框 → 四框品均已接入；稀有度无专图的框品回退常规版。
2. 等级标 → `level_<n>_<color>`，1–3 勾玉、八色；4/3_4 仅备用。
3. N 稀有度 → 保留，仅扩展功能可选。
4. 破甲 → `combat_fragile_{1,2}.png` 默认 2 可换。
5. 数字与符号 → 五色位图；font_size 为目标高度，无程序渐变/描边。
6. 协战头像框 → 已接入 `duo/`。
7. 派系大标 → legacy 三变体；小标 → 逐条目 `inline_faction_style` 三变体。
8. 特殊状态 → `badges/`；shown 仅大卡，机制 badge 仅 bless/eclipse。
