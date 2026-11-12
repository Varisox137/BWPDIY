# BWPDIY 术语表

本表只记录现行口径；历史更新见 GitHub Releases 与工具内「最近更新」。新增或变更术语须同步本表。

## 渲染层级

大卡自底向上：卡图 → 牌框 → 框内静态（卡名、稀有度双标、脚注）→ 框上叠加（等级、派系、stat/burst/status 图标、协战双式神框）→ 描述文本 → stat/burst 数值。`render_element` 的 `stat_part` 为 `icon` / `number` / 缺省两者；status 只有图标，无等级卡也绘制。

对局小卡：底框与卡图（气绝时灰化）→ 等级与数值 → 右上能量/倒计时 → 气绝组件。

| 术语 | 代码标识 | 现行口径 |
|---|---|---|
| 卡图 | artwork | 用户插画，经 `offset_x/offset_y/scale/rotate` 变换后叠于牌框下；offset 为图像相对画布的位置，正值向右/向下，不钳制；scale 为有限正数；rotate 绕图片中心顺时针旋转并扩展画布 |
| 原画 / 异画 | default art / alt art | `artwork.images[0]` / `artwork.images[1:]`；当前渲染只消费首图，调用方先选择异画；每张图变换独立 |
| 牌框 | frame | `frames/{form,combat,spell,field,reinforce}_{框品}.png`；式神复用 form。卡图区透明，不再使用 mask |
| 框品 | frame_variant | 常规 norm / 琉璃 blue / 墨染 black / 百炼 red；缺省 norm，全类型可用；影响牌框、稀有度回退和文字颜色 |
| 等级标 | level_badge | 底座 base → 觉醒星 evolve（仅觉醒）→ 纯色圆 evolve_circle（仅觉醒）→ 勾玉 `level_{1,2,3}_<color>`；八色为 yellow/cyan/purple/red/blue/brown/greyblue/orange，缺省 yellow。布局为 `pos/star_offset/num_offset`，圆盘跟随星标 |
| 稀有度标 | rarity_mark | N/R/SR/SSR；R/SR/SSR 按框品读专图，缺失回退常规版，N 始终读 `rarity/N.png`。N 与无稀有度仅扩展功能开放选择，隐藏控件不改数据 |
| 派系标 | faction_mark | 红莲 red / 苍叶 green / 青岚 blue / 紫岩 purple / 无相；大标 `factions/<color>_{1,2,3}.png`，缺省样式 2；内嵌小标 `icons/faction_<color>_{1,2,3}.png`，逐条目 `inline_faction_style` 缺省 1 |
| 数值标 | stat | 力量 power / 生命 health / 护甲 shield / 破甲 fragile / 幻境耐久 intensity；图标读 `stats/`。负护甲自动用破甲，变体 1/2 可选、缺省 2 |
| 位图数字 | numbers | `numbers/<color>_<0–9/plus/minus>.png`，另有 `white_inf.png`；颜色 white/red/green/purple/orange，运行时 yellow 映射 orange。`font_size` 是单字目标高度，多位数按逐行墨迹最小水平间距 3px 拼接，竖直中点对齐；不使用程序渐变或描边，遗留 `stroke_width` 不绘制 |
| 卡名 / 脚注 | name_text / footer | 卡名用田氏颜体大字库 2.0；脚注缺省为「所属式神-类型[/子类型]」，协战为「式神1×式神2-协战」，中立牌省略所属式神，式神回退卡名。两者按给定点居中 |
| 描述文本 | desc_text | 方正北魏楷书；自动换行、逐行居中、文本块竖直居中、字号递减。换行与水平居中按整行文字掩膜的最紧边界测宽，保留段内 advance/字距，仅排除整行最外侧字框空白。正文与高亮色按框品，资源映射见 `render/text.py` |
| 关键字高亮 | `[[...]]` | 双英文方括号，括号不绘制，内容按框品异色；从左往右配最近闭合，未匹配或空标记按字面文本；高亮内不嵌套双括号，# 图标仍解析但不变色 |
| 内嵌图标 | `#xx` | 两位拼音首字母映射见 `render/text.py ICON_CODES`；未知代码报错。图标裁最紧方形 box，高为字号 × `icon_scale`，与相邻文字加八分之一宽空格，行首/行尾不加该侧空格；宽度参与换行与居中 |
| 三态描述排版 | text_layout | `smart`（缺省）/`wrap`/`off`。smart 独立开头完整纯关键字短句并去末尾句号，排除突袭/坚守/鼓舞/爆能/运势等带后续效果能力；条件/增强/响应/觉醒前生成断行候选，自动断行上一行至少占可用宽 35%；同字号且不增加行数时，优先避免闭标点/句读位于行首及比较/运算符、前引号或开括号留在行尾，再避免高亮短语跨行、内嵌图标位于行首，会增加行数则回退；2–3 行末行不足 35% 时可缩小至多 2px，只有减少行数才采用。wrap 仅换行适配；off 仅显式换行、固定最大字号、不避让角标；原始输入不改写 |
| 行首标点避让 | — | 超宽时把前一个可见文字或图标连同连续闭合标点移至下一行，重算行宽、居中与障碍避让；显式 `\n` 后用户主动写的行首标点不变 |
| 文本区 | text_regions.desc | `center/width/height`，可选 `center_offset/obstacle_gap/icon_scale`。当前字号排不下或任一行被障碍挤偏时，先逐 1px 上移居中锚点（至多半行高），再减小字号。stat 碰撞轮廓取 alpha≥128，y 带仅外扩 1px |
| 成品导出 | tightest bbox | 大卡默认按全部可见元素透明边界裁齐，原尺寸返回；`crop=False` 返回工作画布。大卡、小卡、头像支持 `width/height` 原生重绘，规则见集成文档 |
| 轮廓裁剪 | silhouette clip | 牌框先按 alpha≥128 取得实心轮廓并向内腐蚀 2px，再裁掉框外卡图，最后叠框与元素；探出框缘的元素不受影响 |
| 双式神框 | duo_frame | 协战可选布尔字段，缺省不绘制。每槽位为底图/头像 → 内外斜框 → 派系标；资源 `duo/{back,frame_1,frame_2,highlight_1}.png`，槽位 2 高光旋转派生，派系复用 `factions/`。头像由 web 按所属式神注入内部 `_duo`，不进 schema |
| 头像 | portrait | 主要式神可选 `{offset_x,offset_y,scale,rotate,frame}`，与卡图变换独立；`frame=false` 只导出菱形裁剪头像。衍生物式神不使用头像 |
| 爆能 | burst | 大卡临时带符号整数，绝对值最多 10 位；0/缺省不绘制。仅战斗/法术/形态/幻境支持，式神/协战忽略；WebGUI 输入仅非正整数。以等级 pos + offset 定位，白字能量大图标，不持久化 |
| 特殊状态 | status | 大卡临时字段：None/bless/eclipse/bond/curse/radiance/nightmare/eternal/endless/unused/multi_status/shown，对应 badges 中文资源；以等级锚点 + offset 定位，icon_size 控制大小。可越出基础画布并纳入紧致边界，不持久化 |
| 对局式神 | entity / render_entity | 96×144 小卡，来源限式神/形态/觉醒；等级 0–3，0 仅底框与卡图。power/health 非负，combat_power/shield 可负；四色字段缺省白，可 red/green/purple。`art_scale` 独立控制小卡原画缩放，偏移沿用大卡并按框内透明窗修正，默认再上移窗高 4% |
| 右上组件 | energy / countdown | 均为非负整数、含 0；energy 黄字，countdown 白字。前端互斥，渲染库允许共存且 countdown 后绘制；气绝保留 energy、隐藏 countdown |
| 气绝组件 | defeated_countdown | 非负整数（含 0，供复活过渡帧）或精确字符串 `infinity`；白字，永久气绝经 `numbers/white_inf.png` 绘制 ∞；最后绘制 |

## 资源与类型代码

- 卡牌类型：combat 战斗、spell 法术、form 形态（式神共用）、field 幻境、reinforce 协战。
- 内嵌映射：`ll→power`、`sm→health`、`hj→shield`、`pj→fragile`、`nl→energy`、`nj→intensity`、`zl→combat_power`、`fl→weak`、`sj→bounty`；派系为 hl/cy/ql/zy。
- `stats/` 是大卡与小卡角标资源；小卡战力/乏力也用 `stats/combat_power.png`、`stats/weak.png`。`icons/` 仅用于文本内嵌小图。
- 机制框：`mech/frame_invocation_{3,4,5}.png`、`mech/frame_skill_{3,4,5}.png`、`mech/frame_seal.png`。
- 大卡状态与机制角标：`badges/<中文状态名>.png`，由 `AssetLibrary.BADGE_FILES` 映射英文代码；`shown` 仅大卡，机制 badge 仅 bless/eclipse。
- 归档：`assets/legacy/` 为退役位图，`assets/psd_export/` 为 PSD 图层镜像；二者不作运行时资源、不进 exe。
- 待补：赏金大角标；`icons/bounty.png` 与 `#sj` 已可用。

## 数据与组织

| 术语 | 现行口径 |
|---|---|
| 式神项目 | `library/<项目>/project.yaml + shikigami/ + cards/ + images/`；主要式神上限 49，其他卡牌/衍生物上限 299，按版本组计 |
| 项目 ID / 发布日期 | `project.yaml` 可选三位全库唯一 `id` 与 `release_date`；项目 ID 留空时首次从 051 递增，发布日期只作为新建主要式神空白版本日期的优先值 |
| 自动编号 | store 在保存/上传时为空白 ID 补号；完整规则见 `AGENTS.md` 与 `docs/integration.md`。衍生牌与衍生物式神共用 51–99，从两端取号；中立非协战牌从 19999999 递减 |
| 卡名与文件名脱钩 | YAML 文件名任意，name 是显示与引用口径；主要式神改名联动更新同项目引用。历史无 ID 且按卡名命名的文件在改名时同步重命名，响应带新 stem |
| 名称合法性 | 拒绝空名、首尾空白、路径分隔符、Windows 非法字符/保留设备名、控制字符、`.`/`..` 与点结尾；项目名 `mechanisms` 保留 |
| 版本日期 | 卡牌/机制 `version_date=YYYYMMDD`；卡牌按 id+name、机制按 name 归组，同组共享 layout/artwork；新版本文件名 `基础stem@日期` |
| 引擎段 | 与 BWPro 对齐的卡牌字段；level/rarity 可缺省表示无等级/无稀有度，协战所属为 shikigami1/2，衍生物式神用 shikigami；衍生牌在新建时用 token 选定并默认无稀有度 |
| 渲染段 | `artwork.images[]={path,offset_x,offset_y,scale,rotate}`，均可缺省；path 缺省为 `<id 或卡名>.png`。主要式神另有 portrait，单卡另有稀疏 layout |
| 布局配置 | 统一读写 `$HOME/.bwpdiy/layout.json`；六类型按类型 × 框品解耦，单卡再稀疏覆盖。对局式神与机制为独立段，不参与六类型传播 |
| 扩展选项 | 「手动调整布局」控制布局页与单卡布局入口；「扩展功能」控制对局预览、N/无稀有度、无等级、派系/内嵌派系样式及主要式神头像控件。关闭只隐藏控件，不清值 |

## 机制

机制是跨项目共享池 `library/mechanisms/*.yaml` 中的条目，字段为 `name/frame/text/version_date`，可选 `badge/inline_faction_style/chars_per_line`。

- frame：invocation 灵咒框 / skill 关键字框 / seal 加护蚀印框。原版游戏无「技能」概念，界面与文档统一使用「关键字」；归档素材文件名除外。
- 名称金色、左对齐、字号略大于正文且不加粗；名称与描述之间空一行，描述逐行左对齐，正文色按框体。seal 的 bless/eclipse 角标使名称自动右移。
- 内容行数 = 名称 + 空行 + 描述行，下限 2；行高由正文字号决定。原生 3–5 行直接用对应素材，其余从素材中部裁拼，框高随内容变化。
- `chars_per_line` 为正整数，条目与调用缺省 12，决定文本宽和框宽；`font_scale` 同步缩放文字、文本区、框宽/横向偏移和行高，保持每行字数，不缩放角标。
- 布局「机制」段三类共用 `name_size/text_size/icon_scale`；`frames.<frame>` 各有 `text_x/text_dy/width`，seal 另有 `badge_size/badge_pos`。名称与描述同左缘，不单独偏移；文本区无固定高度。
- 描述支持高亮、内嵌图标和行首标点避让，不支持卡牌 `text_layout`。
