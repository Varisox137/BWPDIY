# PSD 素材 ↔ 现有 assets 对应表（v1.0 评审稿 v2）

> 来源：`assets/百闻牌DIY模板整合（更新战力、乏力标识）BY 鹿倉暦.psd` + `assets/协战牌模板.psd`，
> 已导出至 `assets/psd_export/`（主 141 张 + 协战 44 张，topil() 直取图层像素）。
> 本表供审阅；⚠️ 标记为待拍板决策点（汇总见文末）。
>
> v2 变更：新增协战 PSD 解包（§I）；全部素材按术语表英文命名（§0）；
> 四色勾玉保留为二期染色方案（决策点 2 已按用户意见修订）；新增 webgui「扩展选项」栏规划（§J）。

## 0. 英文命名规范（依据 docs/terminology.md）

入库资产一律英文命名，代码标识沿用术语表：

| 概念 | 英文标识 |
|---|---|
| 卡牌类型 | `xt` 形态（式神共用）/ `zd` 战斗 / `fs` 法术 / `hj` 幻境 / `xz` 协战 |
| 框品 | `norm` 常规（PSD"基础"）/ `blue` 琉璃 / `black` 墨染 / `red` 百炼 |
| 派系 | `red` 红莲 / `green` 苍叶 / `blue` 青岚 / `purple` 紫岩 |
| 数值字段 | `power` 力量 / `health` 生命 / `shield` 护甲 / `pierce` 破甲 / `durability` 耐久 |
| 内嵌图标代码（二期 `#xx` 语法沿用） | `ll` 力量 / `sm` 生命 / `hj` 护甲 / `pj` 破甲 / `nl` 能量 / `nj` 耐久 / `zl` 战力 / `fl` 乏力 / `sj` 赏金 |
| 等级标三层 | `base` 底座 / `evolve_star` 觉醒图案 / `gouyu_{1,2,3}` 勾玉层 |

目标目录结构（替换完成后）：

```
assets/
  frames/    {xt,zd,fs,hj}_{norm,blue,black,red}.png + xz_norm.png（入库前统一缩放至标准画布）
  levels/    base.png / evolve_star.png / gouyu_{1,2,3}.png（二期追加 gouyu_{1,2,3}_{red,green,blue,purple}.png 四色染色版）
  rarity/    {R,SR,SSR}.png + {R,SR,SSR}_{blue,red}.png + xz_{R,SR,SSR}.png
  factions/  {red,green,blue,purple}.png（式神大派系标）
  stats/     {xt,zd,fs}_power.png / {xt,fs}_health.png / zd_shield.png / zd_pierce.png / hj_durability.png
  signs/     plus.png / minus.png
  portraits/ plate.png / frame.png / ring.png / faction_{red,green,blue,purple}.png（协战双头像框）
  icons/     {ll,sm,hj,pj,nl,nj,zl,fl}.png（描述内嵌小图标，二期 `#xx` 用，入库备用）
  fonts/     不变（两个 ttf）
```

`assets/psd_export/` 保持中文目录名不动——它是 PSD 图层结构的原始镜像档案，不作为运行时资源。

## A. 牌框（frames/ → PSD 4 类型 × 4 框品 + 协战框）

| 现有资产 | PSD 素材 | 尺寸 | 目标路径 |
|---|---|---|---|
| `frame_xt_norm_low.png`（式神/形态共用） | `卡框-基础_形态/基础.png` | 312×590 | `frames/xt_norm.png` |
| （无） | `卡框-基础_形态/{琉璃光境,百炼,墨染}.png` | 313-321 宽 | `frames/xt_{blue,red,black}.png` |
| `frame_zd_norm_low.png` | `卡框-战斗/基础.png` | 310×587 | `frames/zd_norm.png` |
| （无） | `卡框-战斗/{琉璃光境,百炼,墨染}.png` | 313-320 宽 | `frames/zd_{blue,red,black}.png` |
| `frame_fs_norm_low.png` | `卡框-法术/基础.png` | 313×570 | `frames/fs_norm.png` |
| （无） | `卡框-法术/{琉璃光境,百炼,墨染}.png` | 313-322 宽 | `frames/fs_{blue,red,black}.png` |
| `frame_hj_norm_low.png` | `卡框-幻境/基础.png` | 352×604 | `frames/hj_norm.png` |
| （无） | `卡框-幻境/{琉璃光境,百炼,墨染}.png` | 333-397 宽 | `frames/hj_{blue,red,black}.png` |
| `frame_xz_norm_low.png`（legacy 协战框） | `协战/协战牌框.png`（真协战框） | 308×533 | `frames/xz_norm.png` |

说明：

- **决策点 1 已解决**：协战 PSD 已提供真协战框，legacy xz 框废弃
- 协战框仅 norm 一种（PSD 无框品变体）
- 新合成顺序：**卡图 → 叠加牌框（卡图区天然透明，无需 mask）→ 裁掉牌框边缘以外内容 → 叠加所有元素**；`masks/` 五张全部废弃删除
- 各框品宽高比略有差异（如战斗：基础 310×587 ≈ 0.528、百炼 320×589 ≈ 0.543），入库时统一预处理缩放到同一画布口径

## B. 等级标（levels/ → 勾玉组）

| 现有资产 | PSD 素材 | 尺寸 | 目标路径 |
|---|---|---|---|
| `levels/base.png`（青黑底座） | `勾玉/勾玉-底框.png` | 69×69 | `levels/base.png` |
| `levels/star.png`（觉醒星，原待用户重制） | `勾玉/底框-觉醒.png` | 99×99 | `levels/evolve_star.png`——官方版直接可用，无需重制 |
| `levels/{6色}_{1-3}.png`（数字层 18 张） | `勾玉/一勾玉/二勾玉/三勾玉.png` | 32-51px | `levels/gouyu_{1,2,3}.png` |
| （无） | 染色生成（hue 旋转勾玉贴图） | — | 二期 `levels/gouyu_{1,2,3}_{red,green,blue,purple}.png` |

- 协战 PSD 内勾玉组与主 PSD **逐像素一致**（已验证），去重只用一套
- **决策点 2 已按用户意见修订**：官方勾玉无颜色变体，但四色勾玉需求保留（用于 BWPro 对战中渲染四位己方式神）——排期二期，以染色方式从原图生成四色变体；v1.0 仅无色版

## C. 稀有度（rarity/ → 罕贵度组 + 协战三色）

| 现有资产 | PSD 素材 | 尺寸 | 目标路径 |
|---|---|---|---|
| `rarity/R.png` | `罕贵度/R.png` | 248×25 整带 | `rarity/R.png`（裁单枚花标） |
| `rarity/SR.png` | `罕贵度/SR.png` | 246×28 | `rarity/SR.png` |
| `rarity/SSR.png` | `罕贵度/SSR.png` | 246×29 | `rarity/SSR.png` |
| （无） | `罕贵度/{R,SR,SSR} 琉璃光境.png` | ~243×26-34 | `rarity/{R,SR,SSR}_blue.png` |
| （无） | `罕贵度/{R,SR,SSR} 百炼.png` | ~243×28-33 | `rarity/{R,SR,SSR}_red.png` |
| （无） | `协战/稀有度/蓝色.png` | 229×26 整带 | `rarity/xz_R.png`（裁单枚） |
| （无） | `协战/稀有度/紫色.png` | 227×26 | `rarity/xz_SR.png` |
| （无） | `协战/稀有度/金色.png` | 229×26 | `rarity/xz_SSR.png` |
| `rarity/N.png` | **PSD 无 N** | — | ⚠️ 决策点 3 |

说明：

- PSD 罕贵度均为**整带**（两端各一朵花标、中间透明），入库时裁出单枚花标，适配现有"卡名两侧对称"（rarity_flank）逻辑
- **墨染框品稀有度 PSD 缺失**——black 框沿用 norm 版花标（回退规则：`{R}_{variant}.png` 缺失时用 `{R}.png`）
- 协战稀有度按颜色区分：蓝=R / 紫=SR / 金=SSR（按惯例推定，⚠️ 如有误请指正）

## D. 派系标（factions/ 12 张 → 基础-派系组）

| 现有资产 | PSD 素材 | 尺寸 | 目标路径 |
|---|---|---|---|
| `factions/{color}_{1,2,3}.png`（12 张） | `基础-派系/{红莲,苍叶,青岚,紫岩}.png` | 95-100px | `factions/{red,green,blue,purple}.png` |
| （无） | `☆符号/派系/{4色}{,-墨染}.png`、`协战/特殊符号/派系符号/{4色}.png` | 30-39px | 入库备用（描述内嵌/头像框小标见 §I） |

## E. 数值角标（icons/ → 各类型数值组，按类型分图）

| 现有资产 | PSD 素材 | 尺寸 | 目标路径 |
|---|---|---|---|
| `icons/ll_l.png`（力量，现全类型通用） | `基础_形态-数值/基础_形态-攻击.png`、`战斗-数值/战斗-攻击.png`、`法术-数值/法术-攻击.png` | 68×72 | `stats/xt_power.png` / `zd_power.png` / `fs_power.png` |
| `icons/sm_l.png`（生命） | `基础_形态-生命.png`、`法术-生命.png` | 63×77 | `stats/xt_health.png` / `fs_health.png` |
| `icons/hj_l.png`（护甲） | `战斗-数值/战斗-护甲.png` | 62×78 | `stats/zd_shield.png` |
| `icons/pj_l.png`（破甲，负值换图） | `战斗-数值/战斗-破甲.png`（60×76 粉白裂纹盾）；另有 `战斗-破甲1.png`（54×71 更红更深） | — | `stats/zd_pierce.png` ⚠️ 决策点 4：二选一 |
| `icons/nj_l.png`（幻境耐久） | `幻境-数值/幻境.png`（鸟居） | 68×60 | `stats/hj_durability.png` |
| `icons/sj_s.png`（赏金，未使用；PSD 无对应） | 无 | — | 删除，二期需要时再找素材 |
| `icons/{ll,sm,hj,pj,nl,nj}_s.png` 等小图 | `☆符号/{攻击,生命,护甲,破甲,能量,幻境}.png`、`☆新增战力乏力/{战力,乏力}.png`（59-60×70 高清） | 17-70px | `icons/{ll,sm,hj,pj,nl,nj,zl,fl}.png` 入库备用（二期 `#xx` 内嵌图标） |
| （无） | 各数值组 `数值-攻击/数值-生命/...`（type 图层栅格化样本） | 18-28×42-47 | **不入库**——官方数字样式样本（白字黑边细长美术体），无法程序化渲染任意数字，仅作样式参考 |

⚠️ **决策点 5**：官方数字是细长美术体，只有样本图没有字体文件。数字继续用田氏颜体？（风格与官方略有差距）

## F. 正负号（新增独立素材，替换字体符号方案）

| PSD 素材 | 尺寸 | 目标路径 |
|---|---|---|
| `战斗-数值/加号.png` | 27×40 | `signs/plus.png` |
| `战斗-数值/减号.png` | 21×14 | `signs/minus.png` |
| `加号_2/减号_2/法术的加号` 等重复项 | — | 与主图一致，弃 |
| `协战/攻击值/{增加攻击,减少攻击}.png`、`生命值/增加生命.png` | 20-26×16-37 | 备用（协战 stat 当前不开放，见 §I） |

替换现有"田氏颜体 ± 号 0.65 水平压缩"逻辑为贴图绘制；布局配置新增符号相对数字块的 offset 参数。

## G. 字体与文字颜色

- `fonts/` 两个 ttf **保留**（田氏颜体=卡名/数字，方正北魏楷书=描述/脚注）
- `文字-{基础,墨染,琉璃光境,百炼}/` 40 张位图 + `协战/文字颜色选取.png`（4 色取样条）**不入库**——
  是各框品文字样式样本/调色板，从中**取样颜色值**写入渲染配置，按框品自动切换卡名/描述/脚注颜色：
  - norm：深色字；black（墨染）：金色字；red/blue（百炼/琉璃）：浅色字

## H. 扩展素材（已入库 psd_export 备用，v1.0 不使用）

| PSD 素材组 | 内容 | 后续用途 |
|---|---|---|
| `灵咒技能框/`、`技能描述黑框/` | 3/4/5 行字技能框 | 式神技能区 |
| `加护蚀印描述框/` | 加护/蚀印图标+底框 | 扩展机制 |
| `烹饪/` | 佳肴/食材/底框 | 扩展机制 |
| `文字描述-EX/` | 唯一/瞬发/技能名/技能描述字样 | 关键字样式参考 |
| `卡牌标识/` | 战斗/法术/形态/幻境 62px 标识 | 类型角标（待定） |
| `卡图放在这里/`、两个 `_整卡示例.png` | 卡背/模板示例 | 不入库使用 |

## I. 协战专节（协战牌模板.psd，44 张）

| PSD 素材 | 尺寸 | 目标路径/处置 |
|---|---|---|
| `协战牌框.png` | 308×533 | `frames/xz_norm.png`（决策点 1 解决） |
| `稀有度/{蓝,紫,金}色.png` | 227-229×26 整带 | `rarity/xz_{R,SR,SSR}.png`，见 §C |
| `勾玉/` 5 张 | 同主 PSD | 逐像素一致，去重 |
| `式神头像框/头像{1,2}/底板.png` | 92×83 黑菱板 | `portraits/plate.png`（两张一致则去重） |
| `式神头像框/双框.png` | 77×153 | `portraits/frame.png` |
| `式神头像框/突出 {1,2}.png` | 75×75 菱形描边 | `portraits/ring.png`（两张一致则去重） |
| `式神头像框/派系{1,2}/{4色}.png` | 26-30px | `portraits/faction_{red,green,blue,purple}.png` |
| `插图/蒙版底板.png` | 267×328 | 卡图占位底板，入库备用 |
| `攻击值/生命值` 组（增加攻击/减少攻击/增加生命 + 数字样本 type 层） | — | 备用——协战 stat 适用矩阵当前不开放（维持用户裁定），素材留存 |
| `特殊符号/属性符号` 8 张、`派系符号` 4 张 | 13-24px | 备用（与主 PSD 符号组同用途，尺寸微差） |
| `文字描述/`（卡牌名称/技能描述/式神名字 type 层） | — | 文字样式样本，不入库，取色参考 |

**协战头像框是新的渲染元素**（双菱形头像 + 各自派系小标，见 `_整卡示例.png`）：
需要卡牌数据新增 portraits 字段（2 张头像图 + 各所属式神/派系）与 GUI 上传入口。
⚠️ 决策点 6：协战头像框是否进 v1.0？（工作量大可排 v1.1，v1.0 协战先只换框）

## J. webgui「扩展选项」栏（v1.0 新增，用户要求）

- 界面新增「扩展选项」区（勾选框组），**默认全部不勾选、对应功能不对普通使用者开放**
- 首期收容：
  - 「手动调整各元素布局」——勾选后才显示布局设置 tab（现布局编辑功能降级为扩展功能）
  - 「勾玉四色」——预留位（功能本身二期实现，勾选框可先置灰或隐藏）
- 配置存本地（library 或 localStorage），渲染/API 层不感知

## 决策点汇总（待拍板）

1. ~~协战框~~ **已解决**：协战 PSD 提供真协战框
2. ~~等级标颜色~~ **已解决**：v1.0 无色勾玉；四色勾玉二期染色生成（BWPro 对战渲染四位己方式神用）
3. **N 稀有度**：PSD 无 N。a) 保留旧 N 图；b) v1.0 暂不支持 N（rarity 限 R/SR/SSR）
4. **破甲图标**：`战斗-破甲`（粉白裂纹盾 60×76）还是 `战斗-破甲1`（更红更深 54×71）？
5. **数字字体**：继续用田氏颜体？（无官方数字字体可用）
6. **协战头像框**：进 v1.0 还是排 v1.1？
7. **协战稀有度颜色映射**：蓝=R / 紫=SR / 金=SSR 是否正确？
