# PSD 素材 ↔ 现有 assets 对应表（v1.0 定稿 v3）

> 来源：`assets/百闻牌DIY模板整合（更新战力、乏力标识）BY 鹿倉暦.psd` + `assets/协战牌模板.psd`，
> 已导出至 `assets/psd_export/`（主 141 张 + 协战 44 张，topil() 直取图层像素）。
>
> v3 变更：按用户裁定定稿——素材改完整英文术语命名（保留拼音首字母映射）、
> 等级标命名 `level_<n>_<color>` 默认黄色、正负号用 PSD 贴图、协战框入 unprocessed、
> 头像框排 v1.1。全部决策点已关闭。

## 0. 英文命名规范（用户裁定 v3）

入库资产一律**完整英文术语**命名（弃拼音首字母代码）：

| 概念 | 英文命名 | 拼音首字母映射（保留，二期 `#xx` 内嵌图标用） |
|---|---|---|
| 卡牌类型 | `form` 形态（式神共用）/ `combat` 战斗 / `spell` 法术 / `field` 幻境 / `assist` 协战 | `xt→form` / `zd→combat` / `fs→spell` / `hj→field` / `xz→assist` |
| 框品 | `norm` 常规 / `blue` 琉璃 / `black` 墨染 / `red` 百炼 | — |
| 派系 | `red` 红莲 / `green` 苍叶 / `blue` 青岚 / `purple` 紫岩 | — |
| 数值 | `power` 力量 / `health` 生命 / `shield` 护甲 / `pierce` 破甲 / `durability` 耐久 / `energy` 能量 / `might` 战力 / `feeble` 乏力 / `bounty` 赏金 | `ll→power` / `sm→health` / `hj→shield` / `pj→pierce` / `nl→energy` / `nj→durability` / `zl→might` / `fl→feeble` / `sj→bounty` |
| 等级标三层 | `base` 底座 / `evolve_star` 觉醒图案 / `level_<1,2,3>_<color>` 勾玉层 | — |

目标目录结构（替换完成后）：

```
assets/
  frames/    {form,combat,spell,field}_{norm,blue,black,red}.png（入库前统一缩放至标准画布）
             unprocessed/assist_norm.png（协战框 raw；缺 blue/black/red 三种，待补）
  levels/    base.png / evolve_star.png / level_{1,2,3}_yellow.png
             （二期染色追加 level_{1,2,3}_{cyan,purple,red,blue,brown}.png）
  rarity/    {R,SR,SSR}.png + {R,SR,SSR}_{blue,red}.png + N.png（legacy 保留，仅扩展选项可选）
             + assist_{R,SR,SSR}.png
  factions/  {red,green,blue,purple}_{1,2,3}.png（legacy 三变体保留，式神卡用）
             + {red,green,blue,purple}_4.png（PSD 基础-派系大标，第 4 变体可选）
  stats/     {form,combat,spell}_power.png / {form,spell}_health.png
             / combat_shield.png / combat_pierce_{1,2}.png（默认 2，可换）/ field_durability.png
             （TODO：energy/bounty 大角标缺失，以后补充）
  signs/     plus.png / minus.png
  icons/     {power,health,shield,pierce,energy,durability,might,feeble}.png
             + faction_{red,green,blue,purple}{,_black}.png（8 枚派系小标）
             （描述内嵌小图标，二期 `#xx` 用，入库备用）
  fonts/     不变（两个 ttf）
```

`assets/psd_export/` 保持中文目录名不动——PSD 图层结构的原始镜像档案，不作运行时资源。

## A. 牌框（frames/ → PSD 4 类型 × 4 框品）

| 现有资产 | PSD 素材 | 尺寸 | 目标路径 |
|---|---|---|---|
| `frame_xt_norm_low.png`（式神/形态共用） | `卡框-基础_形态/基础.png` | 312×590 | `frames/form_norm.png` |
| （无） | `卡框-基础_形态/{琉璃光境,百炼,墨染}.png` | 313-321 宽 | `frames/form_{blue,red,black}.png` |
| `frame_zd_norm_low.png` | `卡框-战斗/基础.png` | 310×587 | `frames/combat_norm.png` |
| （无） | `卡框-战斗/{琉璃光境,百炼,墨染}.png` | 313-320 宽 | `frames/combat_{blue,red,black}.png` |
| `frame_fs_norm_low.png` | `卡框-法术/基础.png` | 313×570 | `frames/spell_norm.png` |
| （无） | `卡框-法术/{琉璃光境,百炼,墨染}.png` | 313-322 宽 | `frames/spell_{blue,red,black}.png` |
| `frame_hj_norm_low.png` | `卡框-幻境/基础.png` | 352×604 | `frames/field_norm.png` |
| （无） | `卡框-幻境/{琉璃光境,百炼,墨染}.png` | 333-397 宽 | `frames/field_{blue,red,black}.png` |
| `frame_xz_norm_low.png`（legacy 协战框） | `协战/协战牌框.png`（308×533） | — | **不入运行时**——raw 存 `frames/unprocessed/assist_norm.png`，标记暂缺 blue/black/red 三种；v1.0 协战沿用 legacy 框 |

说明：

- 新合成顺序（四类型）：**卡图 → 叠加牌框（卡图区天然透明，无需 mask）→ 裁掉牌框边缘以外内容 → 叠加所有元素**；`masks/` 中 form/combat/spell/field 四张废弃删除，xz 蒙版随 legacy 协战框暂留
- 各框品宽高比略有差异（如战斗：基础 310×587 ≈ 0.528、百炼 320×589 ≈ 0.543），入库时统一预处理缩放到同一画布口径

## B. 等级标（levels/ → 勾玉组，用户裁定命名）

| 现有资产 | PSD 素材 | 尺寸 | 目标路径 |
|---|---|---|---|
| `levels/base.png`（青黑底座） | `勾玉/勾玉-底框.png` | 69×69 | `levels/base.png` |
| `levels/star.png` | `勾玉/底框-觉醒.png` | 99×99 | `levels/evolve_star.png` |
| `levels/{6色}_{1-3}.png`（18 张） | `勾玉/一勾玉/二勾玉/三勾玉.png` | 32-51px | `levels/level_{1,2,3}_yellow.png`（官方勾玉即金色，**默认黄色**） |
| （无） | 二期染色生成（hue 旋转） | — | `level_{1,2,3}_{cyan,purple,red}.png`（扩展四色=黄/青/紫/红）；`blue/brown` 两色也保留生成 |

- 协战 PSD 内勾玉组与主 PSD**逐像素一致**（已验证），去重只用一套
- 四色勾玉（BWPro 对战渲染四位己方式神用）排期二期，经 webgui「扩展选项」开放

## C. 稀有度（rarity/ → 罕贵度组 + 协战三色；用户裁定）

| 现有资产 | PSD 素材 | 尺寸 | 目标路径 |
|---|---|---|---|
| `rarity/R.png` | `罕贵度/R.png` | 248×25 整带 | `rarity/R.png`（裁单枚花标） |
| `rarity/SR.png` | `罕贵度/SR.png` | 246×28 | `rarity/SR.png` |
| `rarity/SSR.png` | `罕贵度/SSR.png` | 246×29 | `rarity/SSR.png` |
| （无） | `罕贵度/{R,SR,SSR} 琉璃光境.png` | ~243×26-34 | `rarity/{R,SR,SSR}_blue.png` |
| （无） | `罕贵度/{R,SR,SSR} 百炼.png` | ~243×28-33 | `rarity/{R,SR,SSR}_red.png` |
| `rarity/N.png` | PSD 无 N | — | **保留 legacy N.png，仅「扩展选项」启用时可选** |
| （无） | `协战/稀有度/蓝色.png` | 229×26 整带 | `rarity/assist_R.png`（裁单枚） |
| （无） | `协战/稀有度/紫色.png` | 227×26 | `rarity/assist_SR.png` |
| （无） | `协战/稀有度/金色.png` | 229×26 | `rarity/assist_SSR.png` |

说明：

- **间距逻辑（用户征询意见，建议采纳）**：维持现有"短卡名固定 `gap`、长卡名按 `margin` 自动外移"的
  动态逻辑，不用 PSD 整带的固定间距——卡名长度可变，动态逻辑已测试稳定；PSD 整带裁单枚花标使用
- **墨染（black）框采用与标准（norm）一致的稀有度素材**（用户裁定）；回退规则 `{R}_{variant}.png` 缺失 → `{R}.png`
- 协战稀有度颜色映射 **蓝=R / 紫=SR / 金=SSR（用户确认正确）**

## D. 派系标（用户裁定）

| 现有资产 | PSD 素材 | 处置 |
|---|---|---|
| `factions/{color}_{1,2,3}.png`（12 张 legacy） | — | **保留**——式神卡派系仍按原 3 种可选变体 |
| （无） | `基础-派系/{红莲,苍叶,青岚,紫岩}.png`（95-100px） | 入库为第 4 可选变体 `factions/{color}_4.png` |
| （无） | `☆符号/派系/{4色}{,-墨染}.png`（30-39px，8 枚） | **全部保留**，`icons/faction_{color}{,_black}.png`（二期内嵌图标用） |

## E. 数值角标（stats/，按类型分图；用户裁定）

| 现有资产 | PSD 素材 | 尺寸 | 目标路径 |
|---|---|---|---|
| `icons/ll_l.png` | `基础_形态-攻击.png` / `战斗-攻击.png` / `法术-攻击.png` | 68×72 | `stats/form_power.png` / `combat_power.png` / `spell_power.png` |
| `icons/sm_l.png` | `基础_形态-生命.png` / `法术-生命.png` | 63×77 | `stats/form_health.png` / `spell_health.png` |
| `icons/hj_l.png` | `战斗-护甲.png` | 62×78 | `stats/combat_shield.png` |
| `icons/pj_l.png` | `战斗-破甲.png`（60×76 粉白）+ `战斗-破甲1.png`（54×71 深红） | — | `stats/combat_pierce_1.png` / `combat_pierce_2.png`，**默认用 2（可换）** |
| `icons/nj_l.png` | `幻境-数值/幻境.png`（鸟居） | 68×60 | `stats/field_durability.png` |
| （无） | 能量/赏金大角标 **PSD 缺失** | — | **TODO 以后补充** |
| `icons/sj_s.png` | 无对应 | — | 删除 |
| `icons/{ll,sm,hj,pj,nl,nj}_s.png` 等小图 | `☆符号/{攻击,生命,护甲,破甲,能量,幻境}.png`、`☆新增战力乏力/{战力,乏力}.png`（59-60×70 高清） | 17-70px | `icons/{power,health,shield,pierce,energy,durability,might,feeble}.png` 入库备用 |
| （无） | 各数值组 `数值-*`（type 图层数字样本） | — | 不入库，仅样式参考 |

## F. 数字与正负号（用户裁定）

- **数字 0-9 仍用数字字体**（田氏颜体），需**模仿 PSD 样本描边**（白字黑边细长体风格，
  现有 `_render_ink` 已有白字黑描边，实施时对照样本调描边宽度/比例）
- **正负号不再经字体渲染**：`signs/plus.png`（27×40）/ `minus.png`（21×14）贴图，
  调整大小和位置后直接绘制；布局配置新增符号相对数字块的 offset 参数
- 废弃"田氏颜体 ± 号 0.65 水平压缩"逻辑

| PSD 素材 | 目标路径 |
|---|---|
| `战斗-数值/加号.png` | `signs/plus.png` |
| `战斗-数值/减号.png` | `signs/minus.png` |
| `加号_2/减号_2/法术加号` 等重复项 | 弃 |
| `协战/攻击值/生命值` 组（增加/减少攻击生命 + 数字样本） | 备用（协战 stat 不开放） |

## G. 字体与文字颜色

- `fonts/` 两个 ttf **保留**
- `文字-{基础,墨染,琉璃光境,百炼}/` 40 张 + `协战/文字颜色选取.png` **不入库**——取样颜色值写入渲染配置，
  按框品自动切换卡名/描述/脚注颜色（norm 深色 / black 金色 / red·blue 浅色）

## H. 扩展素材（psd_export 备用，v1.0 不使用）

灵咒技能框 / 技能描述黑框（3/4/5 行字）/ 加护蚀印 / 烹饪 / 文字描述-EX / 卡牌标识 62px / 卡背图——
全部留存 psd_export 备用。

## I. 协战专节（用户裁定）

| PSD 素材 | 处置 |
|---|---|
| `协战牌框.png`（308×533） | raw 存 `frames/unprocessed/assist_norm.png`，**暂缺 blue/black/red 三种框品**；v1.0 协战沿用 legacy 框 |
| `稀有度/{蓝,紫,金}色.png` | `rarity/assist_{R,SR,SSR}.png`（见 §C） |
| `勾玉/` 5 张 | 与主 PSD 逐像素一致，去重 |
| `式神头像框/`（底板/双框/突出/派系小标） | **v1.0 不加入**——双式神框仅 BWPro 卡组构筑/对战查看详情时用，DIY 工具一般不绘制；素材留存 psd_export，排 v1.1 再议 |
| `插图/蒙版底板.png` | 备用 |
| `攻击值/生命值`、`特殊符号/`、`文字描述/`、`文字颜色选取.png` | 备用/取色参考 |

## J. webgui「扩展选项」栏（v1.0 新增，用户裁定）

- 界面新增「扩展选项」区（勾选框组），**默认全部不勾选、对应功能不对普通使用者开放**
- 首期收容：
  - 「手动调整各元素布局」——勾选后才显示布局设置 tab
  - 「N 稀有度可选」——勾选后稀有度下拉出现 N
  - 「勾玉四色」——预留位（功能二期实现，先置灰）
- 配置存本地，渲染/API 层不感知

## 决策点收尾

1. 协战框 → PSD 有真框，但 4 框品不齐，raw 入 unprocessed，v1.0 沿用 legacy 框 ✓
2. 等级标 → `level_<n>_<color>`，默认黄色；四色（黄/青/紫/红）二期染色，另两色（blue/brown）保留生成 ✓
3. N 稀有度 → 保留 legacy 素材，仅扩展选项启用时可选 ✓
4. 破甲 → 双变体 `combat_pierce_{1,2}.png`，默认 2 可换 ✓
5. 数字 → 田氏颜体 + 模仿 PSD 描边；正负号 PSD 贴图 ✓
6. 协战头像框 → v1.1 再议 ✓
7. 协战稀有度 蓝/紫/金 = R/SR/SSR ✓
