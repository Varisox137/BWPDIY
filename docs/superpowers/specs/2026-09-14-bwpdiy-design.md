# BWPDIY 百闻牌 DIY 卡牌工具 — 设计文档

日期：2026-09-14
状态：已获用户批准（讨论过程见对话记录）

## 1. 背景与定位

《阴阳师百闻牌》自制 DIY 卡牌工具，带 WebGUI。前身是 `legacy/` 下的 Qt/PIL 半成品（Qt 方案已放弃，详见 legacy 摸底结论）。

双重定位：

1. **独立工具**：供粉丝成套 DIY（1 式神 + 8 卡 + 衍生物），带卡牌库管理与可视化编辑器；
2. **渲染服务方**：BWPro 后期的 GUI 对战（构筑/局内卡牌/局内实体）以**包导入**方式调用本工具渲染卡面，最低粒度为**单张完整卡面 PNG**。

关键约束：BWPro 官方数据库**不收录**任何人的 DIY 卡；DIY 数据独立存放，引擎与工具仅提供加载支持（不保证强度平衡，但需基本数据格式校验）。

## 2. 总体架构

单 Python 包内分层（方案 A）：

```
BWPDIY/
├── bwpdiy/
│   ├── render/      # 纯渲染库：只依赖 Pillow，BWPro import 的唯一入口
│   ├── store/       # 卡牌库存取 + schema 校验
│   ├── web/         # FastAPI 编辑器服务（API + 静态前端）
│   └── __main__.py  # python -m bwpdiy 启动编辑器
├── assets/          # 美术资源（从 legacy/bwpCardDIY/basics 迁移）
├── library/         # 用户 DIY 卡牌库（gitignore，属个人创作数据）
├── tests/
├── legacy/          # 只读封存，不改动
└── docs/
```

依赖方向：`render` 不 import `store`/`web`（BWPro 引入 `bwpdiy.render` 时不拖入 FastAPI）；`store`、`web` 可依赖 `render`。

技术栈：Python 3.12+ / uv / Pillow / PyYAML / FastAPI + uvicorn / vanilla JS（无构建步骤）/ pytest。

## 3. 数据模型与存储

式神项目制，文件系统即数据库：

```
library/
└── <项目名>/                # 一个式神项目（v1.2.2 起对应 BWPro 大版本，可多式神）
    ├── project.yaml         # 可选元数据：全库唯一的三位项目 ID
    ├── shikigami/
    │   └── <任意文件名>.yaml  # 无所属式神的主要式神，上限 49，卡名以文件内 name 为准
    ├── cards/
    │   └── <任意文件名>.yaml  # 其他卡牌与有所属式神的衍生物式神，单项目上限 299 组
    └── images/              # 卡图原图（上传按最终 <id><ext> 落盘，见 §5）
```

文件名与卡名脱钩（v1.2.2）：文件名任意（方便 BWPro 按 id 命名取文件），卡名以文件内
`name` 字段为准；主要式神卡名全项目唯一（引用按名关联），改名时服务端联动改写同项目所有卡的
`shikigami`/`shikigami1`/`shikigami2` 引用。衍生物式神以 `shikigami` 记录所属主要式神。

### 自动编号

保存或上传卡图时，store 为空白 ID 统一补号，前端不自行计算，已有手动 ID 原样保留。项目 ID 可编辑；留空时首次编号从 `051–999` 取全库最小空号并写入 `project.yaml`，修改项目 ID 不迁移旧卡。完整卡牌 ID 同样跳过全库占用。

| 条目 | ID 规则与号段 |
|---|---|
| 主要式神 | `1<三位项目ID><01–99>`，首位异画位自动取 1 |
| 普通所属卡 | `<所属式神六位ID><01–20>` |
| 协战牌 | 较小的所属式神六位 ID + `21–50` |
| 衍生牌 | 所属式神六位 ID + `51–99`，从 51 递增 |
| 衍生物式神 | 所属式神六位 ID + `51–99`，从 99 递减 |
| 中立非协战牌 | 八位独立 ID，从 `19999999` 起全库递减 |

衍生牌与衍生物式神共用 `51–99`，从两端取空号且无固定分界。非式神、非协战卡以可选布尔 `token: true` 标记衍生牌；该字段不自动修改稀有度。保存和上传响应均返回最终 `id`；旧空白 ID 的历史版本组同步补号。`save_card` 内联动写入由项目级快照回滚与串行写锁保护；上传图片原子写入，写图后的保存失败只恢复图片，不回滚前置补号已写入的项目/所属式神 YAML。

### 卡牌 yaml 结构

分引擎段与渲染段。引擎段字段与 BWPro yaml 口径对齐、按卡牌类型分字段（机制未实现不进数据，schema 字段只增不改）：

```yaml
# 引擎段（示例：法术）
type: 法术            # 式神/战斗/法术/形态/幻境/协战
name: 示例卡
id: "100301"          # 可留空，保存/上传时自动补齐；改 id 不重命名已有卡图
level: 1
rarity: R             # N/R/SR/SSR；衍生牌可缺省
shikigami: 示例式神
token: true           # 可选；仅非式神、非协战衍生牌
description: 造成 3 点伤害，获得#hl。
inline_faction_style: 1  # 可选 1/2/3，缺省 1；逐条目控制全部内嵌派系小标

# 渲染段（整段可缺省）
artwork:
  images:             # 可缺省，默认 [{path: <id 或卡名>.png}]（隐式卡名路径保留旧数据兼容）
    - path: a.png     # 原画（images[0]）；path 可缺省，默认 <id 或卡名>.png
      offset_x: 0     # 均可缺省：0 / 0 / 1.0 / 0（自动居中填满，不旋转）
      offset_y: 0
      scale: 1.0
      rotate: 0       # v1.2.1：绕图片中心顺时针度数，画布自动扩展
    - path: b.png     # 异画（images[1:]）：id 不同但共用一份 yaml，定位参数各自独立
      offset_y: -12
      scale: 1.15
```

按类型字段（沿用 legacy `config_parser.py` 字段表）：

- 式神：faction（红莲/苍叶/青岚/紫岩/无相）、power、health
- 非式神通用：level、rarity、special_type；所属式神——常规卡单引用 `shikigami`，协战双引用 `shikigami1`/`shikigami2`（v1.2.2 起，脚注自动 `式神1×式神2-协战`）；evolve（觉醒）仅战斗/法术/形态/幻境（式神/协战不可）
- 战斗：power/shield 加成；法术觉醒：power/health；形态：power/health；幻境：durability

### 异画定位

异画不涉及卡图形状/布局的改变，仅立绘不同。按 BWPro 的 id 原则：异画卡与原画卡 id 不同，但无需新增 yaml——同一份 yaml 的 `artwork.images` 列表按序对应。每张图的 offset/scale 独立微调。

**现行框品与扩展字段**：norm/blue/black/red 四框品已开放，全类型均可使用；卡牌/机制 `inline_faction_style` 由「扩展功能」控制控件显隐，缺省 1，关闭扩展不回退已保存值。大卡的 burst/status 仅为临时渲染字典字段，不进 store schema。

### schema 校验

按类型白名单校验（保存时执行）：类型枚举、按类型必填字段、数值范围、派系/稀有度枚举及 `token` 布尔值；错误信息中文并指出字段名。

## 4. 渲染管线（render）

移植 legacy `image_processor.py` 思路，重写为无全局状态的函数式管线：

1. 卡图按 `rotate/scale/offset` 变换（旋转绕中心、画布扩展、加载即缓存；v1.2.1；v1.2.2 起 cover 缩放基准固定为旋转前原图尺寸，旋转不再自带缩放；v1.3.0 起 offset 不钳制、平出画面留透明）→ 叠加牌框（卡图区天然透明）→ 裁掉框外内容（v1.0 起蒙版废弃）
2. 牌框合成：框品 `frame_variant`（v1.0 开放 norm/blue/black/red，缺省 norm；版型 high/low 概念废弃）
3. 叠图标层：
   - 等级标三层叠加（无等级卡牌跳过）：底座 base → 觉醒星（仅觉醒牌）→ 勾玉层（1–3 勾玉，卡面 `level_color` 可选 yellow/cyan/purple/red/blue/brown/greyblue/orange 八色）；`level_4_*` 与 `level_3_4_*` 仅作备用命名，不接等级枚举、表单或渲染引用
   - 稀有度标、派系标、数值标（力量/生命/护甲加成/耐久）；协战及墨染等缺失的稀有度变体回退常规版，不再保留协战专用花标
   - 大卡临时 `status`（None/bless/eclipse/bond/curse/radiance/nightmare/eternal/endless/unused/multi_status/shown）读取 `badges/<状态中文名>.png`（由 AssetLibrary.BADGE_FILES 映射），无等级卡也绘制，六类型布局均以等级锚点加 `offset` 定位、以 `icon_size` 控制尺寸；不持久化，均不进入机制 badge
   - 协战双式神框（v1.4.1）：卡面可选布尔 `duo_frame`（缺省不绘制）；双菱形头像槽位（黑底板+头像菱形裁剪+高光+派系小标）+双框线盖顶，素材 `duo/`；头像由 web 预览按 `shikigami1`/`shikigami2` 注入所属式神卡图（内部键 `_duo`，不进 schema/yaml）
4. 文本：卡名（田氏颜体大字库 2.0）+ 描述（方正北魏楷书）自动排版——从大到小试字号、自动换行、逐行居中；文字颜色按框品；`[[关键词]]` 异色高亮（v1.2，双括号标记；v1.3.0 起未匹配括号按字面文本显示）与 `#xx` 内嵌图标（ICON_CODES 拼音首字母映射、相邻文字八分之一宽空格、宽度计入换行/居中、大小=字号×desc 区 `icon_scale` 系数）均已落地。卡牌与机制正文自动换行时避免行首闭合/句读标点，必要时将前一个可见文字或图标连同标点移至下一行；显式 `\n` 后的行首标点保留。v1.8.3 卡牌可选 `text_layout=smart/wrap/off`（缺省 smart）：智能模式拆分开头纯关键字短句并比较条件/增强/响应/觉醒前候选断行（上一行至少占可用宽 35%），wrap 为旧排版，off 仅显式换行且固定最大字号；机制不使用该字段。卡牌与机制均可选 `inline_faction_style`（1/2/3，缺省 1），逐条目控制全部派系小标，不再按墨染框自动切换文件
5. 数值与爆能使用 `numbers/` 五色位图数字及同色正负号，`font_size` 表示单字缩放目标高度，多位数按逐行墨迹最小间距拼接；yellow 映射 orange 文件。旧字体数字、程序渐变与描边不再参与绘制，布局遗留 `stroke_width` 仅为兼容校验字段
6. 成品导出：默认按 tightest alpha bbox 裁齐后直接返回原尺寸 PNG；可选 `width`/`height` 按目标原生重绘画布、卡图、布局、字体与图标，禁止先渲染默认成品再 resize

对外主入口：

```python
bwpdiy.render.render_card(card: dict, assets_dir: Path) -> PIL.Image
```

默认合成在资源原生 512×512 工作画布进行（四周透明）。叠框后先做**轮廓裁剪**（v1.0.1）：删去牌框实际形状之外的所有像素（框 alpha==0 且与画布边缘连通；卡图窗被框缘包围不受影响），元素在其后绘制、探出框缘不受影响。`render_card` 默认按合成图 tightest alpha bbox 裁齐返回；`crop=False` 时返回完整工作画布，供管线分层断言用。缺资源/缺字段抛明确异常，由调用方兜底（BWPro 侧 try/except 显示占位卡面）。

## 5. 编辑器 WebGUI

vanilla JS 单页（无构建），`/` 为编辑器主体页，三个主 tab：「卡牌库」「对局预览」与「全局布局设置」（原独立布局页已退役，`/layout` 307 重定向 `/#layout`；v1.8.1 起对局预览整页默认隐藏，由「扩展功能」开启并控制 hash 直达，头像参数/预览还须同时满足扩展功能与头像框开启）。20261030 起 HTML 只保留结构，CSS 与共享/卡牌/对局/机制/布局/入口六段 JS 分文件按序加载，不引入框架或模块系统。

**卡牌库 tab**（M2+M3 骨架，已落地）三栏：

- **左栏**：项目列表 + 卡牌列表分「主要式神」（无所属式神的式神卡，n/49）与「卡牌/衍生物」（n/299）两栏；新建输入框放在对应栏目下方，长列表在栏目内部滚动；v1.2.2 起：新建项目为空项目，式神卡可删；卡名在表单直接编辑，不再提供「重命名卡牌」按钮——文件名与卡名脱钩，GUI 不改文件名；主要式神改名时服务端联动更新同项目引用并提示）
- **中栏**：预览——编辑期走项目卡预览 + 表单整体覆盖（含未保存修改与卡图 offset/scale，基准目录 = 项目 `images/`）debounce 实时刷新；选中/保存后走项目卡预览（读盘，缺图回退占位）
- **右栏**：项目选中时编辑三位项目 ID；卡牌表单按类型动态显隐字段（含觉醒勾选框与非式神、非协战卡的「衍生牌」`token`），即时校验（口径对齐 store schema），保存 422 错误表单侧展示；卡名上方有可留空 id 输入框，保存/上传后采用响应返回的最终 ID；所属式神为下拉（「（手动填写）」+ 同项目式神名列表，协战为式神1/2 两个）；卡牌类型创建后固定，卡图上传仅按当前表单覆盖 id/token/所属字段，类型沿用已保存卡牌；空白 ID 先由服务端补齐，再按最终 `<id><ext>` 落盘项目 `images/`；改 id 不重命名已有卡图、不清理旧图，写回 `artwork.images[0].path`；卡图定位 offset_x/offset_y/scale/rotate 数字输入支持鼠标调整

**对局预览 tab**（v1.8.0）：读取卡牌库当前选择及未保存编辑，式神仅提供小卡，形态/觉醒可切换大卡与小卡，其他卡仅提供大卡；等级、勾玉和数值颜色、爆能、特殊状态、能量/倒计时及气绝均为临时状态，不写盘、不置脏，返回卡牌库保留原条目与未保存内容。大卡爆能 `burst` 与特殊状态 `status`（None/bless/eclipse/bond/curse/radiance/nightmare/eternal/endless/unused/multi_status/shown，无等级也绘制）只是渲染字典临时字段，不进 store schema；这些 status 仅大卡可用，机制 seal 仍只有 bless/eclipse。所有卡牌与对局状态数值最多 10 位；非气绝 `countdown` 允许 0，供倒计时触发动画使用。

**布局设置 tab**：六类型与框品切换，元素/文本区画布拖拽定位，卡牌内容（样卡数值/式神名/子类型/描述/觉醒/爆能/特殊状态）可编辑实时预览；全部元素与文本区按卡牌类型 × 框品独立，不做跨类型同步。六类型 status 元素均以等级锚点加 offset 定位、以 icon_size 控制尺寸；数字与符号由位图资源原生缩放，遗留 stroke_width 不参与绘制。「对局式神」页另可调整右上组件与气绝倒计时，并提供能量/普通倒计时、气绝及永久样例。

**空闲自动终止**（防占用）：连续 2h 无 HTTP 操作进程自动退出（`/api/update/check` 自动轮询不计入活动，否则挂页面永不空闲）；GUI 包装 fetch，连接级失败弹「连接已断开」说明窗提示重启。v1.7.7 起顶栏提供「退出DIY工具」，对所有编辑区统一做未保存确认，`POST /api/shutdown` 记录「手动按钮关闭」并延迟清理退出；前端随后关闭标签页，浏览器禁止脚本关窗时提示手动关闭。选卡时主卡/头像均只作废旧响应而保留当前图，待新数据到达后由预览函数统一替换或隐藏，避免同卡版本切换闪烁。

**后续候选**：项目批量导出（单卡、头像与对局小卡导出均已实现）。

## 6. BWPro 集成

- **主路径**：BWPro `import bwpdiy.render`，传卡牌 dict 拿 PIL Image，由调用方保存 PNG 或转换为字节，异常兜底占位卡面；基础安装只引入 Pillow。
- 集成契约（dict 字段表、四类渲染入口、尺寸与异常规则）见 `docs/integration.md`，两边共同遵守；不经过 WebGUI 服务。

## 7. 错误处理

- 保存时 schema 校验（见 §3）
- 渲染时：图片不存在、字体缺失、美术资源缺失 → 明确异常
- 编辑器：表单即时校验 + 预览失败显示错误条而非空白

## 8. 测试

pytest 三层：schema 校验单测、渲染 smoke（各类型各出一张图不炸 + 输出尺寸断言）、FastAPI API 测试（TestClient）。
测试命令（Windows Git Bash）：`PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`

## 9. 开发范式

沿用用户级约定：全程中文；uv 依赖管理；中文 conventional commit 且每次 commit 后 push（失败不阻塞，汇报即可）；大改动先 plan mode；批量改动委托子代理；改完同步文档（术语/机制变更 → `docs/terminology.md`，项目规则 → 本仓库 `AGENTS.md`）。`legacy/` 只读封存。

## 10. 分期

- **M1**：项目骨架 + assets 迁移 + render 管线（含纯文本排版）+ 命令行渲染一张示例卡
- **M2**：store 层（项目/卡牌 CRUD + schema 校验）——已落地（StoreError 语义 code、名称安全/路径注入防护、原子写）
- **M3**：WebGUI 编辑器完整流程（列表/表单/预览/导出）——骨架已落地（三主 tab 编辑器：CRUD/表单/实时预览/独立对局预览/布局调参/卡图上传与 offset 调参）；PNG 导出 v1.4.0 落地（前端「导出」按钮）；协战双式神框渲染部件 v1.4.1 落地（卡面 `duo_frame` 开关，头像自动取所属式神卡图）
- **M4**：HTTP API + `docs/integration.md` + 与 BWPro 对联调示例
- **二期**：`#图标` 描述内嵌小图标（`[[关键词]]` 异色高亮 v1.2 已落地）、等级数字 4 色接入对局位置

## 11. 术语表

见 `docs/terminology.md`（定稿于本次讨论）。

## 12. 开放问题 / 待办

1. **BWPro 现有 524 张卡 yaml 需补 `artwork` 段**：offset/scale 需逐卡人工调试。因 `artwork` 整段可缺省、缺省自动居中，旧 yaml 不补也能渲染，无迁移阻塞；逐卡精调是后期工作。（提醒用户）
2. **BWPro 侧美术资产目录安排待定**：`artwork.images[].path` 在 BWPro 调用侧的相对基准目录以后确定。
3. ~~**式神卡资源核实**~~（已核实）：式神卡外观形状同形态牌，渲染按 `TYPE_FRAME_CODE` 复用 `form` 资源（见 `bwpdiy/render/pipeline.py`），差异化元素为派系标/力量/生命。v1.0 起牌框/蒙版体系已由 PSD 官方素材替换（masks 废弃），legacy 旧资源含 unprocessed 原图封存 `assets/legacy/`。
4. ~~框品资源映射~~（v1.0 已开放）：常规=norm / 琉璃=blue / 墨染=black / 百炼=red。
5. **觉醒星美术资源可能需重制**（用户提醒）：`assets/levels/evolve.png`（99×99，legacy 程序化生成）在正式使用前需用户确认/替换。
6. **赏金左上角大角标尚未实现**：描述内嵌 `#sj` 已使用 `icons/bounty.png` 小图标；本批不新增赏金大角标。能量大图标已于 v1.8.0 接入爆能与对局状态组件。
