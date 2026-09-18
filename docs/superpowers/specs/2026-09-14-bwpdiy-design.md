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
└── <项目名>/                # 一个式神项目
    ├── shikigami.yaml       # 式神卡
    ├── cards/
    │   └── <卡名>.yaml      # 8 张卡 + 衍生物，每张一个文件
    └── images/              # 卡图原图
```

### 卡牌 yaml 结构

分引擎段与渲染段。引擎段字段与 BWPro yaml 口径对齐、按卡牌类型分字段（机制未实现不进数据，schema 字段只增不改）：

```yaml
# 引擎段（示例：法术）
type: 法术            # 式神/战斗/法术/形态/幻境/协战
name: 示例卡
level: 1
rarity: R             # N/R/SR/SSR
shikigami: 示例式神
description: 造成 3 点伤害。

# 渲染段（整段可缺省）
artwork:
  images:             # 可缺省，默认 [{path: <card_id>.png}]
    - path: a.png     # 原画（images[0]）；path 可缺省，默认 <card_id>.png
      offset_x: 0     # 均可缺省：0 / 0 / 1.0（自动居中填满）
      offset_y: 0
      scale: 1.0
    - path: b.png     # 异画（images[1:]）：id 不同但共用一份 yaml，定位参数各自独立
      offset_y: -12
      scale: 1.15
```

按类型字段（沿用 legacy `config_parser.py` 字段表）：

- 式神：faction（红莲/苍叶/青岚/紫岩/无相）、power、health
- 非式神通用：level、rarity、shikigami、special_type；evolve（觉醒）仅战斗/法术/形态/幻境（式神/协战不可）
- 战斗：power/shield 加成；法术觉醒：power/health；形态：power/health；幻境：durability

### 异画定位

异画不涉及卡图形状/布局的改变，仅立绘不同。按 BWPro 的 id 原则：异画卡与原画卡 id 不同，但无需新增 yaml——同一份 yaml 的 `artwork.images` 列表按序对应。每张图的 offset/scale 独立微调。

**一期不做**：框品（墨染/琉璃/百炼）与多牌框支持。渲染器一期只用 norm 框、low 版型；`frame_variant` 字段预留但不进表单，schema 白名单暂拒该字段，二期开放时放行。

### schema 校验

按类型白名单校验（保存时执行）：类型枚举、按类型必填字段、数值范围、派系/稀有度枚举；错误信息中文并指出字段名。

## 4. 渲染管线（render）

移植 legacy `image_processor.py` 思路，重写为无全局状态的函数式管线：

1. 卡图按 `scale/offset` 变换 → 蒙版（高斯平滑 radius=1）抠图
2. 牌框合成：版型选择（一期固定 `low`）+ 框品（一期固定 `norm`）
3. 叠图标层：
   - 等级标三层叠加（无等级卡牌跳过）：底座 base（青黑）→ 觉醒星（仅觉醒牌）→ 等级数字（1–3 × 4 色，对应对局 4 位置）
   - 稀有度标、派系标、数值标（力量/生命/护甲加成/耐久，带正负号规则）
4. 文本：卡名（田氏颜体）+ 描述（方正北魏楷书）纯文本自动排版——从大到小试字号、自动换行、逐行居中；`[关键词]` 上色与 `#xx` 内嵌图标预留接口，二期实现

对外主入口：

```python
bwpdiy.render.render_card(card: dict, assets_dir: Path) -> PIL.Image
```

合成在资源原生 512×512 画布进行（四周透明），`render_card` 最终按合成图 alpha bbox 裁剪输出卡面有效区，水平方向以牌框中心 x=256 为基准对称裁剪（元素单侧探出不带偏内容；各类型尺寸略有差异，宽高比实测 ≈0.63；统一缩放/缩略图由调用方负责；`crop=False` 时返回完整 512×512，供配置工具预览对齐用）。缺资源/缺字段抛明确异常，由调用方兜底（BWPro 侧 try/except 显示占位卡面）。

## 5. 编辑器 WebGUI

vanilla JS 单页（无构建），`/` 为编辑器主体页，双 tab：「卡牌库」与「布局设置」（原独立布局页已退役，`/layout` 307 重定向 `/#layout`）。

**卡牌库 tab**（M2+M3 骨架，已落地）三栏：

- **左栏**：项目列表 + 项目内卡牌列表（新建/重命名/删除；式神卡 shikigami 随项目出厂，不可删除/重命名，可覆盖保存）
- **中栏**：预览——编辑期走样卡管线 debounce 实时刷新（卡图用占位底图）；选中/保存后走项目卡预览（artwork 基准目录 = 项目 `images/`，缺图回退占位）
- **右栏**：表单，按卡牌类型动态显隐字段（含觉醒勾选框，仅战斗/法术/形态/幻境），即时校验（口径对齐 store schema），保存 422 错误表单侧展示

**布局设置 tab**：六类型切换，元素/文本区画布拖拽定位，卡牌内容（样卡数值/式神名/子类型/描述/觉醒）可编辑实时预览，按类型开关元素，保存时样式键跨类型传播。

**M3 完整版未做**：卡图上传（存入项目 `images/`）、预览上拖拽/滚轮缩放定位卡图（前端写回 offset/scale）、单卡导出 PNG、项目批量导出。

## 6. BWPro 集成

- **主路径**：BWPro `import bwpdiy.render`，传卡牌 dict 拿 PIL Image / PNG bytes，异常兜底占位卡面
- **辅助路径**：编辑器服务暴露 `POST /api/render`（传 json 拿 PNG），用于调试与第三方
- 集成契约（dict 字段表）写入 `docs/integration.md`，两边共同遵守

## 7. 错误处理

- 保存时 schema 校验（见 §3）
- 渲染时：图片不存在、字体缺失、蒙版尺寸不符 → 明确异常
- 编辑器：表单即时校验 + 预览失败显示错误条而非空白

## 8. 测试

pytest 三层：schema 校验单测、渲染 smoke（各类型各出一张图不炸 + 输出尺寸断言）、FastAPI API 测试（TestClient）。
测试命令（Windows Git Bash）：`PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`

## 9. 开发范式

沿用用户级约定：全程中文；uv 依赖管理；中文 conventional commit 且每次 commit 后 push（失败不阻塞，汇报即可）；大改动先 plan mode；批量改动委托子代理；改完同步文档（术语/机制变更 → `docs/terminology.md`，项目规则 → 本仓库 `AGENTS.md`）。`legacy/` 只读封存。

## 10. 分期

- **M1**：项目骨架 + assets 迁移 + render 管线（含纯文本排版）+ 命令行渲染一张示例卡
- **M2**：store 层（项目/卡牌 CRUD + schema 校验）——已落地（StoreError 语义 code、名称安全/路径注入防护、原子写）
- **M3**：WebGUI 编辑器完整流程（列表/表单/预览/拖拽定位/导出）——骨架已落地（双 tab 编辑器：CRUD/表单/实时预览/布局调参）；卡图上传、卡图拖拽定位、PNG 导出未做
- **M4**：HTTP API + `docs/integration.md` + 与 BWPro 对联调示例
- **二期**：`[关键词]`/`#图标` 富文本排版、框品/多牌框开放、等级数字 4 色接入对局位置

## 11. 术语表

见 `docs/terminology.md`（定稿于本次讨论）。

## 12. 开放问题 / 待办

1. **BWPro 现有 524 张卡 yaml 需补 `artwork` 段**：offset/scale 需逐卡人工调试。因 `artwork` 整段可缺省、缺省自动居中，旧 yaml 不补也能渲染，无迁移阻塞；逐卡精调是后期工作。（提醒用户）
2. **BWPro 侧美术资产目录安排待定**：`artwork.images[].path` 在 BWPro 调用侧的相对基准目录以后确定。
3. ~~**式神卡资源核实**~~（已核实）：式神卡外观形状同形态牌，渲染按 `TYPE_FRAME_CODE` 复用 `xt` 资源（`masks/mask_xt_low.png` + `frames/frame_xt_norm_low.png`，见 `bwpdiy/render/pipeline.py`），差异化元素为派系标/力量/生命。assets 精修后现库仅收五类型 `*_norm_low` 牌框/蒙版；high 版型与 blue/black/red 框品原图留存 `assets/frames/unprocessed/`（二期接线时取用），已弃用的 `*_bound.png` 蒙版已删除。
4. 框品资源映射：常规=norm / 琉璃=blue / 墨染=black / 百炼=red（用户已确认，二期开放时按此接线）。
5. **觉醒星美术资源可能需重制**（用户提醒）：`assets/levels/star.png`（126×127，legacy 程序化生成）在正式使用前需用户确认/替换。
