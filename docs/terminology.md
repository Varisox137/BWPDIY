# BWPDIY 术语表

定稿日期：2026-09-14。修订：v1.0（2026-09-18，PSD 素材替换/四框品/新合成管线/扩展选项）；v1.2（描述文本关键字高亮）；v1.3.0（描述文本 `#xx` 内嵌图标）；v1.4.0（标记扩展：勾玉六色/式神等级/派系样式/N 稀有度合并；数值变色与多位数逐字拼接）；v1.4.1（协战双式神框渲染部件）。新增/变更术语须同步本表。

## 渲染层级（自底向上合成顺序）

合成顺序：卡图 → 牌框 → 框内静态（卡名/稀有度双标/脚注）→ 框上叠加（等级标/派系标/stat 角标图标/协战双式神框）→ 描述文本 → stat 数值（符号+数字，压在描述文本之上）。stat 元素因此分层绘制：图标层随框上叠加、数值层最后画（`render_element` 的 `stat_part` = "icon"/"number"/缺省两者）。

| 术语 | 代码标识 | 说明 |
|---|---|---|
| 卡图 | artwork | 用户导入的插画，经变换后叠加于牌框之下；一张卡可有原画+多张异画；变换字段 `offset_x`/`offset_y`/`scale`/`rotate`（v1.2.1，绕图片中心顺时针度数、画布自动扩展，加载即缓存）；cover 缩放后按 中心+offset 取景，正 offset=图像相对画布右/下移（v1.3.0 起；此前为取景窗语义、方向相反），v1.3.0 起 offset 不钳制、平出画面区域留透明（方形图 cover 无余量也能挪动） |
| 原画 | default art | `artwork.images[0]` |
| 异画 | alt art | `artwork.images[1:]`，仅立绘不同，卡面布局/形状不变；与原画 id 不同、共用一份 yaml |
| ~~蒙版~~ | ~~mask~~ | **v1.0 废弃**：牌框卡图区天然透明，合成顺序改为 卡图→叠牌框→裁框外内容，不再需要蒙版抠图；旧 masks 封存 `assets/legacy/masks/` |
| 牌框 | frame | 完整卡框（卡图区透明），资源 `frames/{form,combat,spell,field,reinforce}_{框品}.png`（协战仅 norm），PSD 导出经预处理（裁 alpha bbox→等比缩至高 512→居中贴 512×512 透明画布）；版型 `high`/`low` 概念废弃（PSD 框即官方定版） |
| 框品 | frame_variant | 常规(norm)/琉璃(blue)/墨染(black)/百炼(red)；v1.0 开放——卡牌 yaml 可选字段 `frame_variant`（缺省 norm，式神/战斗/法术/形态/幻境可携带，式神牌框同形态、协战恒 norm），按框品自动切换牌框/稀有度贴图/文字颜色 |
| 等级标 | level_badge | 三层自底向上叠加（无等级卡牌整体跳过）：① 底座 `levels/base.png`（勾玉底框）→ ② 觉醒图案 `levels/evolve_star.png`（五角星金底，仅觉醒牌；觉醒 = evolve: true，仅战斗/法术/形态/幻境可携带，式神/协战不可）→ ③ 勾玉层 `levels/level_{1,2,3}_{yellow,cyan,purple,red,blue,brown}.png`（官方勾玉个数制；默认黄色，v1.4.0 接入 legacy 六色，卡牌 yaml 可选字段 `level_color`，缺省 yellow 不写进 yaml）；布局参数三组：`pos` 底座坐标、`star_offset` 觉醒星相对底座偏移、`num_offset` 勾玉相对底座偏移（缺省 [0,0]） |
| 稀有度标 | rarity_mark | N/R/SR/SSR，资源 `rarity/{R,SR,SSR}{,_blue,_red}.png`（罕贵度整带裁单枚花标；black 框品回退 norm 版）+ `rarity/reinforce_{R,SR,SSR}.png`（协战专版：蓝=R/紫=SR/金=SSR）+ `rarity/N.png`（legacy 图，仅「标记扩展」启用时可选） |
| 派系标 | faction_mark | 红莲 red/苍叶 green/青岚 blue/紫岩 purple/无相；式神卡大标沿用 legacy 三变体 `factions/{color}_{1,2,3}.png`（style 默认 2）；`icons/faction_{color}{,_black}.png` 小标为 `#xx` 内嵌图标用（v1.3.0 起，墨染框用 `_black` 变体） |
| 双式神框 | duo_frame | 协战专属（v1.4.1）：牌框左上外侧叠加的双菱形头像组件，**默认不绘制**，卡面可选布尔字段 `duo_frame: true` 开启（缺省不写进 yaml）；每槽位自底向上 黑底板 `duo/back.png`（其 alpha 即菱形掩膜）→ 头像（cover 适配槽位盒+乘底板 alpha 裁菱形），两槽位各自再叠 斜方框（突出高光 `duo/highlight_{1,2}.png` + 框线 `duo/frame_{1,2}.png`，双框拆半、同一偏移）与 派系小标 `duo/faction_{red,green,blue,purple}.png`（无相/缺派系不画）；素材取自 `psd_export/协战/式神头像框/`（派系 1/2 仅苍叶有噪点级差异，合并存一份）。布局元素 `{"kind": "duo_frame", ...}` 共 10 个可调参数：pos=上框底图（槽位1 基底）中心、slot2_dy=下框底图相对上框的竖直间距（缺省 74，两框 x 恒一致竖直对齐）、back_size=底图大小（等比 contain，缺省 88）、frame_size=斜方框大小（高光+框线同一尺寸框，缺省 75）、frame_offset=斜方框相对底图中心偏移（缺省 [0,0]）、faction_offset=派系标中心相对底图中心偏移（缺省 [17,23]）、faction_size=派系标大小（缺省 32）——除 pos/slot2_dy 外上下两框共通；每槽位自底向上 底图→斜方框→派系标 依次叠加。头像自动取自所属式神卡图：web 预览按 `shikigami1`/`shikigami2` 在项目 `shikigami/` 按名找式神卡，取其 `artwork.images[0]` 图（缺省 `<id 或卡名>.png`，路径须解析在项目 `images/` 内；载入后先裁 alpha 透明边再 cover 适配居中，透明边不影响对中）、`portrait` 头像变换段（v1.4.1，式神专属可选渲染段 `{offset_x, offset_y, scale, rotate}` 全可缺省、缺省 0/0/1.0/0 自动居中填满，与卡图变换独立）与 `faction`，注入内部键 `card["_duo"]`（长度 2 列表，槽位 None=空菱形；缺式神 → None；缺图 → 槽位只带 faction（空菱形+派系标）；内部键不进 schema/表单/yaml）；布局 tab 样卡无项目上下文，开开关时注入占位派系（苍叶/青岚）渲染空槽位框供定位；编辑式神卡时卡图预览下方以布局参数 2 倍渲染单槽位「式神头像预览」（`render_portrait`，接口 `portrait_preview`，仅式神卡可用），右栏卡图四项右侧并排「头像」四项输入（写入 `portrait` 段），派系标随该式神派系 |
| 数值标 | stat | 力量(power)/生命(health)/战斗牌护甲加成(shield)/幻境耐久(intensity)；角标贴图 `stats/{stem}.png`（力量/生命全类型共用 `power.png`/`health.png`；护甲 `combat_shield.png`，负护甲自动换 `stats/combat_fragile_2.png` 破甲图，变体 1/2 可选默认 2；耐久 `field_intensity.png`）；正负号贴图 `signs/{plus,minus}.png`（不经数字字体）；适用矩阵见「元素」行 |
| 卡名 | name_text | 田氏颜体大字库 2.0（生僻字字形风格已统一，v1.2.3 起） |
| 描述文本 | desc_text | 方正北魏楷书，自动排版（从大到小试字号、自动换行、逐行居中、文本块竖直居中）；文字颜色按框品（`FRAME_TEXT_FILL`，取色自官方模板文字样本：norm 深色/black 金色/blue·red 浅色）；**关键字高亮**（v1.2）：`[[关键字]]` 双英文方括号标记（v1.2.1 起；单 [ ] 为字面字符），括号不绘制、内容按框品异色（`FRAME_KEYWORD_FILL`，norm 金棕取色自官方卡面关键字样本，blue/red 同族金橙、black 亮橙以对金色正文保持区分）；v1.3.0 起改为从左往右匹配（`'[['` 配其后最近 `']]'`），未匹配括号（无闭合/无配对/空 `[[]]`）一律按字面文本显示、不再校验报错；高亮内部不再解析新 `'[['`，`#` 图标照常解析（异色对图标无效果）；**内嵌图标**（v1.3.0）：`#<两位拼音首字母>` 行内绘制小图标（映射 `render/text.py` ICON_CODES，高=字号×desc 区 `icon_scale`（缺省 1.0），内嵌前预处理为 alpha bbox 外接最紧方形 box（内容居中、占位恒为正方形）、竖直中心对齐行中心；记号不进输出，未知代码 ValueError，'#' 后非两字母为字面字符），派系图标墨染框下用 `_black` 变体；图标与同行相邻文字间自动加四分之一宽空格（0.25em，行首/行尾该侧无空格、图标-图标不加），空格与图标宽度均计入换行与逐行居中 |
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

拼音首字母→术语映射保留（v1.3.0 起 `#xx` 内嵌图标语法用）：`xt→form` `zd→combat` `fs→spell` `hj→field` `xz→reinforce`；`ll→power` `sm→health` `hj→shield` `pj→fragile` `nl→energy` `nj→intensity` `zl→combat_power` `fl→weak` `sj→bounty`（数值英文名单对齐 BWPro：破甲=fragile、幻境耐久=intensity、战力=combat_power、乏力=weak、赏金=bounty）。ICON_CODES 实收 ll/sm/hj/pj/nl/nj/zl/fl + 派系 hl/cy/ql/zy（sj 赏金素材缺失暂未收录）。

## 数据与组织

| 术语 | 说明 |
|---|---|
| 式神项目 | library 下的一个目录（v1.2.2 起对应 BWPro 大版本）：`shikigami/`（式神卡，一式神一文件、上限 49）+ `cards/`（非式神卡，上限 299）+ `images/`（卡图，上传按 `<id 或卡名><ext>` 落盘，同卡名不同 id 可存多版本）；编辑器左栏分「主要式神」（式神卡）与「卡牌」两栏计数 |
| 卡名与文件名脱钩 | yaml 文件名任意（方便 BWPro 按 id 取文件），卡名以文件内 `name` 字段为准；式神卡名全项目唯一（引用按名关联），改名时服务端联动改写同项目所有卡的 `shikigami`/`shikigami1`/`shikigami2` |
| 项目名/卡名合法性 | store 层保存时拒绝：空名、首尾空白、`.`/`..`、路径分隔符与 `<>:"\|?*`、控制字符、以点结尾（防路径注入）、Windows 保留设备名（CON/PRN/AUX/NUL/COM1–9/LPT1–9，大小写不敏感、按 `.` 前缀截断判定）——约束文件 stem 与项目名 |
| 衍生物 | 项目内由卡效果派生的实体卡，存于 `cards/`，带派生标记 |
| 引擎段 | 卡牌 yaml 中与 BWPro 口径对齐的字段（type/name/level/rarity/description…；v1.0 增可选 `frame_variant`；v1.3.0 增可选可留空 `id`，上传卡图按 `<id><ext>` 落盘、留空回退 `<卡名><ext>`，改 id 不重命名已有卡图；v1.4.0 增可选 `level_color`（勾玉六色）与式神专属可选 `level`/`faction_style`） |
| 渲染段 | `artwork` 段：`images` 列表，每项 `path/offset_x/offset_y/scale` 全可缺省（默认 `<id 或卡名>.png` / 0 / 0 / 1.0） |
| 布局配置 | `assets/layout.json`（出厂值入 git）+ 包内 `bwpdiy/render/default_layout.json` 回退；按 6 卡牌类型各一套「元素表 + 命名文本区」；同名元素的尺寸类字段（size/icon_size/font_size/num_offset/star_offset/sign_offset/sign_size_plus/sign_size_minus/stroke_width/gap/margin/base_size/fragile_icon_size/fragile_num_offset/fragile_sign_offset 等除 pos/group_offset/fragile_pos 与内容类外的数值字段）跨类型必须一致，load 时不一致按多数值归一并告警（平票取先出现类型）；`group_offset`（四类带符号数值的符号数字整体偏移，叠加在 num_offset 之上）与 `fragile_pos`（破甲角标坐标）为 per-type 键不归一；GUI 保存时的跨类型传播只镜像样式键白名单，kind/field/pos/group_offset/fragile_pos/enabled 一律不镜像 |
| 元素 | 布局中的可定位渲染单元，kind ∈ level_badge（是否绘制由卡面等级决定：等级 0/无 level 不绘制，v1.1.2 起不再提供启用开关）/ rarity_flank（卡名两侧对称双标：`gap`=默认半间距，短名时双标静态固定在 pos±gap；仅卡名渲染宽度超宽时按与卡名缘固定 `margin` 外移，即 effective=max(gap, name_width/2+margin)，margin 缺省 8）/ faction（`style` 选贴图样式，默认 2；v1.4.0 起卡面可选字段 `faction_style`（1-3）优先于布局 style）/ duo_frame（协战双式神框，卡面 `duo_frame: true` 才绘制，口径见「双式神框」行）/ stat（图标+数字一组，图标由 field 推导 `stats/{stem}.png`、负护甲自动换破甲图；num_offset 相对偏移；破甲（战斗负护甲）四键分离 `fragile_pos`/`fragile_icon_size`/`fragile_num_offset`/`fragile_sign_offset`（缺省回退基础键，fragile_pos 为 per-type 键），贴图变体 `fragile_variant`（1/2，缺省 2），字号/描边/符号尺寸/group_offset 与护甲共享；符号（如有，signs/plus|minus.png 贴图，sign_size_plus/sign_size_minus 分开缩放、sign_offset 偏移）+ 数字作为整体块，块的视觉中心对齐 num_pos；数字白字黑描边（`stroke_width` 可配，默认 2；多位数逐字拼接（v1.4.0）：各字竖直中点同线、相邻字按墨迹最小水平间距 3px 排列（非字体 bbox，避免「41」类组合虚宽），变色渐变以整串墨迹计；v1.4.0 起可选数值变色——卡面伴随字段 `<field>_color`（red/green/purple，缺省白不写进 yaml）：红=debuff/受伤、绿=buff、紫=中毒，色值采样自游戏内截图（红/紫竖直渐变上深下亮、绿近均匀青绿），带符号时符号贴图按亮度掩膜重着色同步变色）；**stat 适用矩阵**为唯一口径（渲染/文本避让/GUI 输入同表）：式神·形态 力量+生命、幻境 耐久——无符号、非负（GUI 输入 min=0 约束，渲染不强制 clamp）、0 照常绘制；战斗 力量+/护甲+、法术觉醒 力量+/生命+——± 号按实际正负贴图、0 值整个角标不渲染；协战/非觉醒法术/其余表外 (type, field) 组合即使 card 带该字段也不绘制、GUI 不提供输入框）/ text（卡名 name 与脚注 footer 点元素：pos 中心水平居中单行，font_size 固定无递减，footer 缺省 = "所属式神-类型[/子类型]"小字（协战为 "式神1×式神2-协战"，缺任一式神只标 "协战"），中立牌（无所属式神）只标 "类型[/子类型]"、式神卡回退卡名；颜色按框品）；贴图统一先裁 alpha 透明边、再等比 contain 进 size 框（size=内容可见尺寸，禁止非等比拉伸） |
| 文本区 | 命名矩形区域（仅 desc：`center`+`width`+`height`，可选 `obstacle_gap` 避让间距、缺省 4；可选 `center_offset` 居中锚点偏移、缺省 [0,0]、per-type 键——区域边界与行宽不变，只平移水平逐行居中与竖直整体居中的视觉基准，如右下角大数字时左移锚点让触界行视觉居中；可选 `icon_scale` 内嵌图标相对文字大小、缺省 1.0、尺寸类跨类型归一——图标高=字号×系数、宽度计入换行与逐行居中），自动换行、逐行居中（行水平中心默认居中锚点；仅当行的实际宽度触到收窄边界时才最小平移避让，短末行不因远处角标偏移）、文本块竖直居中（先定字号与行数，再把文本块中心对齐居中锚点；块整体须落在区域内，出界视为排版失败走字号递减）、字号递减适配——**自适应次序**：当前字号排不下或任一行被障碍挤偏（未水平居中，v1.2.2 起由仅末行放宽为每行都检查）时，先逐 1px 临时上移居中锚点（至多半行高）重试，全部不行才减小字号；显式 `\n` 强制断行（连续 `\n` 合并为一个，每段内再自动换行）；激活的 stat 元素（0 值不渲染的 stat 不参与）在透明层单独渲染，取 alpha≥128 的**碰撞轮廓**作避让掩膜（非组件矩形 bbox，也非原始 alpha 全量墨迹——仿牌框阈值预处理，抗锯齿淡边缘不算墨迹；图标走 alpha_composite 保真源 alpha，不吃默认 paste 的 alpha 平方）：每个描述行 y 带内被占用的 x 区间向外扩 `obstacle_gap` 后逐行收窄，保证竖直贴邻行之间描述墨迹与角标墨迹横向相距 ≥ gap（y 带竖直只外扩 1px——贴邻行之外不收窄，给文本更多可用空间） |
| 扩展选项 | 顶栏勾选框组（localStorage `bwpdiy_ext_options` 持久化，默认全部不勾选、对应功能不对普通使用者开放）：① 手动调整布局（不勾选则隐藏布局设置 tab）② 标记扩展（v1.4.0 合并原「允许 N 稀有度」与勾玉颜色等标记类扩展，旧键 rarity_n 自动迁移）：稀有度下拉开放 N；等级旁开放勾玉六色（黄/青/紫/红/蓝/棕）；式神开放可选等级（0-3，0=无）与派系样式（1-3，默认 2）；各 stat 数值开放变色（白=常态/红=debuff 或受伤/绿=buff/紫=中毒，卡面 `<field>_color` 字段，正负号贴图跟随重着色）——取消勾选只隐藏控件，已写入卡牌的 level_color/faction_style/level/*_color 不回退、渲染照常生效 |
| 素材归档 | `assets/legacy/` = 被替换的旧位图资产封存（旧 frames/icons/levels/masks/rarity，含 unprocessed 框品/high 版型原图留待以后）；`assets/psd_export/` = PSD 图层原始镜像档案（中文名，不作运行时资源）；两者均不进 exe（build_exe.py 排除）；运行时资产由 `scripts/import_psd_assets.py` 从 psd_export 再生成 |

## 二期术语（预留，一期不实现）

| 术语 | 说明 |
|---|---|
| 关键词上色 | 描述文本中 `[关键词]` 高亮着色 |
| 勾玉四色 | （已于 v1.4.0 落地并扩展为六色，见「等级标」；BWPro 对战四位己方式神渲染用黄/青/紫/红） |
| 能量/赏金大角标 | 左上角大角标（energy/bounty），素材缺失待补，暂未实现 |
