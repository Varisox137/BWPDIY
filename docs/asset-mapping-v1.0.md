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
| 等级标三层 | `base` 底座 / `evolve_star` 觉醒图案 / `level_<1,2,3>_yellow` 勾玉层 | — |

目标目录结构：

```
assets/
  frames/    {form,combat,spell,field}_{norm,blue,red,black}.png + reinforce_norm.png（高 512 居中）
  levels/    base.png / evolve_star.png / level_{1,2,3}_yellow.png
             （二期染色追加 level_{1,2,3}_{cyan,purple,red,blue,brown}.png，届时与 legacy 6 色数字版比对取舍）
  rarity/    {R,SR,SSR}.png + {R,SR,SSR}_{blue,red}.png + reinforce_{R,SR,SSR}.png + N.png（仅扩展选项可选）
  factions/  {red,green,blue,purple}_{1,2,3}.png（legacy 三变体，式神卡大派系标）
  stats/     {form,combat,spell}_power.png / {form,spell}_health.png
             / combat_shield.png / combat_fragile_{1,2}.png（默认 2，可换）/ field_intensity.png
             （TODO：energy/bounty 大角标缺失，以后补充）
  signs/     plus.png / minus.png
  icons/     {power,health,shield,fragile,energy,intensity,combat_power,weak}.png
             + faction_{red,green,blue,purple}{,_black}.png（二期内嵌图标备用）
  fonts/     不变（两个 ttf）
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
| `frame_xz_norm_low.png`（legacy 协战框） | `协战/协战牌框.png`（批复：采用 PSD 版） | `frames/reinforce_norm.png`（仅此一框品） |

说明：

- 预处理统一：裁 alpha bbox → 等比缩放至高 512 → 居中贴 512×512 透明画布
- 新合成顺序：**卡图 → 叠加牌框（卡图区天然透明，无需 mask）→ 裁掉牌框边缘以外内容 →
  叠加所有元素 → 最终导出按整卡 tightest alpha bbox 裁剪（不留 512 白边）**
- `masks/` 五张全部废弃入 legacy
- legacy `frames/unprocessed/`（high 版型与框品原图）留待以后

## B. 等级标（levels/ → 勾玉组）

| 现有资产 | PSD 素材 | 目标路径 |
|---|---|---|
| `levels/base.png` | `勾玉/勾玉-底框.png` | `levels/base.png` |
| `levels/star.png` | `勾玉/底框-觉醒.png` | `levels/evolve_star.png` |
| `levels/{6色}_{1-3}.png`（18 张） | `勾玉/一勾玉/二勾玉/三勾玉.png` | `levels/level_{1,2,3}_yellow.png`（默认黄色） |
| （无） | 二期染色生成 | `level_{1,2,3}_{cyan,purple,red,blue,brown}.png`（扩展四色=黄/青/紫/红；另两色保留生成） |

协战 PSD 内勾玉组与主 PSD 逐像素一致（已验证），去重只用一套。

## C. 稀有度（rarity/）

| 现有资产 | PSD 素材 | 目标路径 |
|---|---|---|
| `rarity/{R,SR,SSR}.png` | `罕贵度/{R,SR,SSR}.png`（整带裁左端单枚花标） | `rarity/{R,SR,SSR}.png` |
| （无） | `罕贵度/{R,SR,SSR} 琉璃光境.png` | `rarity/{R,SR,SSR}_blue.png` |
| （无） | `罕贵度/{R,SR,SSR} 百炼.png` | `rarity/{R,SR,SSR}_red.png` |
| `rarity/N.png` | PSD 无 N | 保留 legacy N.png，仅「扩展选项」启用时可选 |
| （无） | `协战/稀有度/{蓝,紫,金}色.png` | `rarity/reinforce_{R,SR,SSR}.png`（蓝=R/紫=SR/金=SSR，已确认） |

- 间距逻辑维持现有"短卡名固定 gap、长卡名按 margin 自动外移"动态逻辑
- 墨染（black）框沿用 norm 版花标（回退规则 `{R}_{variant}.png` 缺失 → `{R}.png`）

## D. 派系标（用户裁定）

| 现有资产 | PSD 素材 | 处置 |
|---|---|---|
| `factions/{color}_{1,2,3}.png`（12 张） | — | **沿用**（式神卡大派系标，不用 PSD 版；PSD 大标与 _2 同形但配色略浅，留 psd_export 备用） |
| （无） | `☆符号/派系/{4色}{,-墨染}.png`（8 枚小标） | `icons/faction_{color}{,_black}.png`（二期内嵌图标） |

## E. 数值角标（stats/，按类型分图）

| 现有资产 | PSD 素材 | 目标路径 |
|---|---|---|
| `icons/ll_l.png` | `基础_形态-攻击` / `战斗-攻击` / `法术-攻击` | `stats/form_power.png` / `combat_power.png` / `spell_power.png` |
| `icons/sm_l.png` | `基础_形态-生命` / `法术-生命` | `stats/form_health.png` / `spell_health.png` |
| `icons/hj_l.png` | `战斗-护甲` | `stats/combat_shield.png` |
| `icons/pj_l.png` | `战斗-破甲` + `战斗-破甲1` | `stats/combat_fragile_{1,2}.png`，**默认用 2（可换）** |
| `icons/nj_l.png` | `幻境-数值/幻境`（鸟居） | `stats/field_intensity.png` |
| （无） | 能量/赏金大角标 PSD 缺失 | TODO 以后补充 |
| `icons/sj_s.png` 及旧小图 | `☆符号/{攻击,生命,护甲,破甲,能量,幻境}.png`、`☆新增战力乏力/{战力,乏力}.png` | `icons/{power,health,shield,fragile,energy,intensity,combat_power,weak}.png` 入库备用 |
| （无） | 各数值组 `数值-*`（type 图层数字样本） | 不入库，仅样式参考 |

## F. 数字与正负号（用户裁定）

- 数字 0-9 仍用田氏颜体，模仿 PSD 样本描边（白字黑边）
- 正负号用 PSD 贴图：`signs/plus.png`（27×40）/ `signs/minus.png`（21×14），
  调整大小位置后直接绘制；布局加符号 offset 参数；废弃字体 ±0.65 压缩方案
- `加号_2/减号_2/法术加号` 等重复项弃；协战 +/- 备用（协战 stat 不开放）

## G. 字体与文字颜色

- `fonts/` 两个 ttf 保留
- `文字-{基础,墨染,琉璃光境,百炼}/` 40 张 + `协战/文字颜色选取.png` 不入库——取样颜色写入渲染配置，
  按框品切换（取色结果见 `.superpowers/sdd/2026-09-17-m23-editor-skeleton/t1-assets-report.md`）：
  - norm：深色字 / black（墨染）：金色字 / red·blue：浅色字

## H. 扩展素材（psd_export 备用，v1.0 不使用）

灵咒技能框 / 技能描述黑框（3/4/5 行字）/ 加护蚀印 / 烹饪 / 文字描述-EX / 卡牌标识 62px / 卡背图。

## I. 协战专节（用户裁定）

| PSD 素材 | 处置 |
|---|---|
| `协战牌框.png` | `frames/reinforce_norm.png`（v1.0 采用，仅 norm） |
| `稀有度/{蓝,紫,金}色.png` | `rarity/reinforce_{R,SR,SSR}.png` |
| `勾玉/` 5 张 | 与主 PSD 逐像素一致，去重 |
| `式神头像框/`（底板/双框/突出/派系小标） | **v1.0 不加入**——双式神框仅 BWPro 卡组构筑/对战详情用，排 v1.1 再议 |
| `插图/蒙版底板.png`、`攻击值/生命值`、`特殊符号/`、`文字描述/`、`文字颜色选取.png` | 备用/取色参考 |

## J. webgui「扩展选项」栏（v1.0 新增）

- 顶栏勾选框组，默认全部不勾选，localStorage 持久化：
  ① 手动调整布局（不勾选则隐藏布局设置 tab）② 允许 N 稀有度 ③ 勾玉四色（disabled 置灰，标"二期"）

## 决策点收尾（全部关闭）

1. 协战框 → PSD 版，仅 norm ✓
2. 等级标 → `level_<n>_<color>` 默认黄色；四色二期染色，届时与 legacy 6 色数字版比对取舍 ✓
3. N 稀有度 → 保留，仅扩展选项可选 ✓
4. 破甲 → `combat_fragile_{1,2}.png` 默认 2 可换 ✓
5. 数字 → 田氏颜体+描边；正负号 PSD 贴图 ✓
6. 协战头像框 → v1.1 再议 ✓
7. 协战稀有度 蓝/紫/金 = R/SR/SSR ✓
8. 派系大标 → 沿用 legacy 三变体；小标用 PSD 版 ✓
