# 美术资源映射

本文记录 PSD/旧位图到运行时 `assets/` 的对应关系；元素语义见 `docs/terminology.md`。PSD 来源为 `assets/百闻牌DIY模板整合（更新战力、乏力标识）BY 鹿倉暦.psd` 与 `assets/协战牌模板.psd`，图层归档于 `assets/psd_export/`。

## 命名规范

- 类型：form 形态（式神共用）/ combat 战斗 / spell 法术 / field 幻境 / reinforce 协战。
- 框品：norm 常规 / blue 琉璃 / black 墨染 / red 百炼。
- 派系：red 红莲 / green 苍叶 / blue 青岚 / purple 紫岩。
- 数值：power 力量 / health 生命 / shield 护甲 / fragile 破甲 / intensity 幻境耐久 / energy 能量 / combat_power 战力 / weak 乏力 / bounty 赏金。
- 内嵌拼音映射与资源语义见术语表，不再另维护一套名称。

## 运行时目录

```
assets/
  frames/    {form,combat,spell,field,reinforce}_{norm,blue,red,black}.png
  levels/    base.png / evolve.png / evolve_circle.png
             level_{1,2,3}_{yellow,cyan,purple,red,blue,brown,greyblue,orange}.png
  rarity/    {R,SR,SSR}.png / {R,SR,SSR}_{blue,red}.png / N.png
  factions/  {red,green,blue,purple}_{1,2,3}.png
  stats/     power.png / health.png / shield.png / combat_fragile_{1,2}.png
             intensity.png / energy.png / countdown.png / defeated_countdown.png
             combat_power.png / weak.png
  numbers/   {white,red,green,purple,orange}_{0..9,plus,minus}.png / white_inf.png
  badges/    {加护,蚀印,缘结,诅咒,天晖,梦魇,无始无终,无穷无尽,未使用,多状态,已展示}.png
  icons/     {power,health,shield,fragile,energy,intensity,combat_power,weak,bounty}.png
             faction_{red,green,blue,purple}_{1,2,3}.png
  duo/       back.png / frame_{1,2}.png / highlight_1.png
  mech/      frame_invocation_{3,4,5}.png / frame_skill_{3,4,5}.png / frame_seal.png
  fonts/     卡名与描述字体，不用于数字
  legacy/    退役位图归档，不进 exe
  psd_export/ PSD 图层镜像，不作运行时资源、不进 exe
```

`level_4_*` 与 `level_3_4_*` 仅作备用命名，不接等级枚举、表单或渲染引用。

## 来源对应

| 来源 | 运行时资源与处理 |
|---|---|
| 各类型卡框 PSD 图层 | `frames/`；裁 alpha bbox、等比缩至高 512、居中贴回 512×512 工作画布。运行时先处理轮廓再合成，最终按全部可见内容紧致导出，不保留 512 留白 |
| 勾玉底框、觉醒底框 | `levels/base.png`、`levels/evolve.png` |
| 旧觉醒星中央色 | `levels/evolve_circle.png`；取中央 9×9 平均色，保留原画布配准 |
| 一/二/三勾玉与八色资源 | `levels/level_<1,2,3>_<color>.png`；协战重复勾玉不另存 |
| R/SR/SSR 花标 | `rarity/`；black、reinforce 等无专图时回退常规版，协战不保留 reinforce_* 专图 |
| legacy N 花标 | `rarity/N.png`，仅扩展功能可选 |
| legacy 三变体大派系标 | `factions/`；式神大标缺省样式 2 |
| 逐条目派系小标 | `icons/faction_*`；由 `inline_faction_style` 选择，缺省 1 |
| 力量、生命、护甲、破甲、幻境耐久 | `stats/`；负护甲用 combat_fragile，默认变体 2 |
| 状态与大角标资源 | `stats/{energy,countdown,defeated_countdown,combat_power,weak}.png`；小卡战力/乏力也用这里的 stats 大图 |
| 文本小图标 | `icons/`；只有描述内嵌 `#zl/#fl` 等使用此目录 |
| 数字、正负号、永久气绝 | `numbers/`；font_size 为单字目标高度，yellow 运行时映射 orange，不使用程序渐变或描边 |
| 状态角标 | `badges/`；保留中文文件名，由 `AssetLibrary.BADGE_FILES` 映射；shown 仅大卡，机制 badge 仅 bless/eclipse |
| 协战头像框 | `duo/`；槽位 2 高光由 highlight_1 旋转派生，派系复用 factions |
| 灵咒/关键字/加护蚀印框 | `mech/`；角标独立放 badges |

`scripts/import_psd_assets.py` 只再生成其管理的 PSD 基础资源，不重建退役兼容路径。`scripts/build_number_signs.py` 只用于重建 orange_minus、purple_plus、purple_minus 三枚合成符号。赏金大角标仍待补，`icons/bounty.png` 已接入 `#sj`。
