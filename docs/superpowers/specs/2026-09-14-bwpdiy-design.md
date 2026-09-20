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
    ├── shikigami/
    │   └── <任意文件名>.yaml  # 式神卡，上限 49，卡名以文件内 name 为准
    ├── cards/
    │   └── <任意文件名>.yaml  # 非式神卡，单项目上限 299 张
    └── images/              # 卡图原图（上传按 <id 或卡名><ext> 落盘，见 §5）
```

文件名与卡名脱钩（v1.2.2）：文件名任意（方便 BWPro 按 id 命名取文件），卡名以文件内
`name` 字段为准；式神卡名全项目唯一（引用按名关联），改名时服务端联动改写同项目所有卡的
`shikigami`/`shikigami1`/`shikigami2` 引用。

### 卡牌 yaml 结构

分引擎段与渲染段。引擎段字段与 BWPro yaml 口径对齐、按卡牌类型分字段（机制未实现不进数据，schema 字段只增不改）：

```yaml
# 引擎段（示例：法术）
type: 法术            # 式神/战斗/法术/形态/幻境/协战
name: 示例卡
id: "100301"          # 可选可留空（v1.2.5）；上传卡图按 <id><ext> 落盘，留空回退 <卡名><ext>；改 id 不重命名已有卡图
level: 1
rarity: R             # N/R/SR/SSR
shikigami: 示例式神
description: 造成 3 点伤害。

# 渲染段（整段可缺省）
artwork:
  images:             # 可缺省，默认 [{path: <id 或卡名>.png}]
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

**一期不做**：框品（墨染/琉璃/百炼）与多牌框支持。渲染器一期只用 norm 框、low 版型；`frame_variant` 字段预留但不进表单，schema 白名单暂拒该字段，二期开放时放行。

### schema 校验

按类型白名单校验（保存时执行）：类型枚举、按类型必填字段、数值范围、派系/稀有度枚举；错误信息中文并指出字段名。

## 4. 渲染管线（render）

移植 legacy `image_processor.py` 思路，重写为无全局状态的函数式管线：

1. 卡图按 `rotate/scale/offset` 变换（旋转绕中心、画布扩展、加载即缓存；v1.2.1；v1.2.2 起 cover 缩放基准固定为旋转前原图尺寸，旋转不再自带缩放）→ 叠加牌框（卡图区天然透明）→ 裁掉框外内容（v1.0 起蒙版废弃）
2. 牌框合成：框品 `frame_variant`（v1.0 开放 norm/blue/black/red，缺省 norm；版型 high/low 概念废弃）
3. 叠图标层：
   - 等级标三层叠加（无等级卡牌跳过）：底座 base → 觉醒星（仅觉醒牌）→ 勾玉层（1–3 勾玉，默认黄色；四色二期）
   - 稀有度标、派系标、数值标（力量/生命/护甲加成/耐久，正负号贴图 signs/{plus,minus}.png）
4. 文本：卡名（田氏颜体大字库 2.0）+ 描述（方正北魏楷书）自动排版——从大到小试字号、自动换行、逐行居中；文字颜色按框品；`[[关键词]]` 异色高亮（v1.2，双括号标记+配对校验）与 `#xx` 内嵌图标（v1.3.0，ICON_CODES 拼音首字母映射、派系墨染变体、相邻文字半宽空格、宽度计入换行/居中、大小=字号×desc 区 `icon_scale` 系数）均已落地
5. 成品导出：tightest alpha bbox 裁剪后等比缩放至高 512（上下顶格、左右居中留白）贴回 512×512（v1.0.1 起；此前为直接裁剪有效区）

对外主入口：

```python
bwpdiy.render.render_card(card: dict, assets_dir: Path) -> PIL.Image
```

合成在资源原生 512×512 画布进行（四周透明）。叠框后先做**轮廓裁剪**（v1.0.1）：删去牌框实际形状之外的所有像素（框 alpha==0 且与画布边缘连通；卡图窗被框缘包围不受影响），元素在其后绘制、探出框缘不受影响。`render_card` 最终按合成图 tightest alpha bbox 裁剪后等比缩放至高 512（上下顶格、左右居中留白；宽溢出退为按宽适配）贴回 512×512 输出；`crop=False` 时返回完整 512×512 合成画布，供配置工具预览对齐用。缺资源/缺字段抛明确异常，由调用方兜底（BWPro 侧 try/except 显示占位卡面）。

## 5. 编辑器 WebGUI

vanilla JS 单页（无构建），`/` 为编辑器主体页，双 tab：「卡牌库」与「布局设置」（原独立布局页已退役，`/layout` 307 重定向 `/#layout`）。

**卡牌库 tab**（M2+M3 骨架，已落地）三栏：

- **左栏**：项目列表 + 卡牌列表分「主要式神」（式神卡，n/49）与「卡牌」（n/299）两栏；v1.2.2 起：新建项目为空项目，式神卡可删；卡名在表单直接编辑，不再提供「重命名卡牌」按钮——文件名与卡名脱钩，GUI 不改文件名；式神改名时服务端联动更新同项目引用并提示）
- **中栏**：预览——编辑期走项目卡预览 + 表单整体覆盖（含未保存修改与卡图 offset/scale，基准目录 = 项目 `images/`）debounce 实时刷新；选中/保存后走项目卡预览（读盘，缺图回退占位）
- **右栏**：表单，按卡牌类型动态显隐字段（含觉醒勾选框，仅战斗/法术/形态/幻境），即时校验（口径对齐 store schema），保存 422 错误表单侧展示；卡名上方有可留空 id 输入框（v1.2.5）；所属式神为下拉（「（手动填写）」+ 同项目式神名列表，协战为式神1/2 两个）；卡图上传（选图 → 按 `<id 或卡名><ext>` 落盘项目 `images/`，同卡名不同 id 可存多版本；改 id 不重命名已有卡图、不清理旧图；写回 `artwork.images[0].path`）与卡图定位 offset_x/offset_y/scale/rotate 数字输入（v1.2.1 起支持旋转；不做拖拽/滚轮定位）

**布局设置 tab**：六类型切换，元素/文本区画布拖拽定位，卡牌内容（样卡数值/式神名/子类型/描述/觉醒）可编辑实时预览，按类型开关元素，保存时样式键跨类型传播。

**M3 完整版未做**：单卡导出 PNG、项目批量导出。

## 6. BWPro 集成

- **主路径**：BWPro `import bwpdiy.render`，传卡牌 dict 拿 PIL Image / PNG bytes，异常兜底占位卡面
- **辅助路径**：编辑器服务暴露 `POST /api/render`（传 json 拿 PNG），用于调试与第三方
- 集成契约（dict 字段表）写入 `docs/integration.md`，两边共同遵守

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
- **M3**：WebGUI 编辑器完整流程（列表/表单/预览/导出）——骨架已落地（双 tab 编辑器：CRUD/表单/实时预览/布局调参/卡图上传与 offset 调参）；PNG 导出未做
- **M4**：HTTP API + `docs/integration.md` + 与 BWPro 对联调示例
- **二期**：`#图标` 描述内嵌小图标（`[[关键词]]` 异色高亮 v1.2 已落地）、等级数字 4 色接入对局位置

## 11. 术语表

见 `docs/terminology.md`（定稿于本次讨论）。

## 12. 开放问题 / 待办

1. **BWPro 现有 524 张卡 yaml 需补 `artwork` 段**：offset/scale 需逐卡人工调试。因 `artwork` 整段可缺省、缺省自动居中，旧 yaml 不补也能渲染，无迁移阻塞；逐卡精调是后期工作。（提醒用户）
2. **BWPro 侧美术资产目录安排待定**：`artwork.images[].path` 在 BWPro 调用侧的相对基准目录以后确定。
3. ~~**式神卡资源核实**~~（已核实）：式神卡外观形状同形态牌，渲染按 `TYPE_FRAME_CODE` 复用 `form` 资源（见 `bwpdiy/render/pipeline.py`），差异化元素为派系标/力量/生命。v1.0 起牌框/蒙版体系已由 PSD 官方素材替换（masks 废弃），legacy 旧资源含 unprocessed 原图封存 `assets/legacy/`。
4. ~~框品资源映射~~（v1.0 已开放）：常规=norm / 琉璃=blue / 墨染=black / 百炼=red。
5. **觉醒星美术资源可能需重制**（用户提醒）：`assets/levels/star.png`（126×127，legacy 程序化生成）在正式使用前需用户确认/替换。
