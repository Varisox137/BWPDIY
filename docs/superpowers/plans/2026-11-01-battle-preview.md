# BWPDIY 1.8.0 对局预览与状态组件 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 新增独立对局预览页、小卡能量/倒计时/气绝（含永久）组件、大卡爆能和五色数字渐变，且全部对局配置仅临时生效。

**Architecture:** 保持 `render` 纯 PIL，大卡从渲染字典读取 `burst`，小卡从 `state` 读取新状态；复用现有项目预览 API。前端新增 `editor-battle.js` 管理选中卡的临时预览，卡牌库移除旧对局控件，全局布局补新元素。

**Tech Stack:** Python 3.12+、Pillow、FastAPI、原生 HTML/CSS/JavaScript、pytest、Node.js 行为测试。

## Global Constraints

- 版本统一为 `1.8.0`，本计划不构建 exe、不发布 Release。
- 设计事实来源：`docs/superpowers/specs/2026-11-01-battle-preview-design.md`。
- `energy`/`countdown` 至多一个非空；能量与普通倒计时允许 0；`defeated_countdown` 为非负整数、`"infinity"` 或 `None`。
- 气绝只灰化底框和卡图；保留原色能量、隐藏倒计时，中央气绝组件最后绘制。0 级仍只画底框和卡图。
- `burst` 为带符号整数，0 不绘制；只属于渲染字典，不加入 store schema，不写 YAML。
- 黄色只供能量自动使用，普通 `<field>_color` 仍只接受 red/green/purple；倒计时、气绝和爆能固定白色。
- 新组件支持紧致边界与 `width/height` 原生重绘，不得缩放默认成品代替。
- 对局预览不写盘、不置脏；返回卡牌库保留原条目及此前未保存编辑。
- 不改 `legacy/`，不还原或提交用户当前对 `assets/legacy/` 的删除；只暂存本任务明确列出的文件。
- 全量命令：`PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`；中文 conventional commit，每次 commit 后 `git push`。

---

### Task 1: 接入状态图标并校准五色数字

**Files:**
- Create: `assets/stats/energy.png`、`assets/stats/countdown.png`、`assets/stats/defeated_countdown.png`
- Add existing references: `assets/ref/*.png`
- Modify: `bwpdiy/render/badges.py:59-89,143-182,317-329`
- Test: `tests/test_badges.py`

**Interfaces:**
- Produces: `STAT_COLORS` 包含 white/red/green/purple/yellow 渐变；`STAT_VALUE_COLORS = {"red", "green", "purple"}` 作为外部可选颜色白名单。
- Produces: `_render_digits(text, font, stroke_width, color=None, gap=_DIGIT_GAP)` 缺省使用 white 渐变；`_render_infinity(font_size, stroke_width)` 返回白色双环 `∞` RGBA 墨迹图。

- [x] **Step 1: 写五色与资源失败测试**

新增测试，直接检查 `_render_digits("6", lib.font("name", 40), 2)` 的亮像素包含各色顶色，并确认普通状态校验不接受 yellow：

```python
@pytest.mark.parametrize("color", ["white", "red", "green", "purple", "yellow"])
def test_five_number_gradients(assets_dir, color):
    from bwpdiy.render.badges import STAT_COLORS, _render_digits
    lib = AssetLibrary(assets_dir)
    img = _render_digits("6", lib.font("name", 40), 2, color)
    top = STAT_COLORS[color][0]
    assert any(all(abs(pixel[i] - top[i]) <= 3 for i in range(3))
               for pixel in img.getdata() if pixel[3] > 200)


def test_infinity_has_white_ink_and_stroke(assets_dir):
    from bwpdiy.render.badges import _render_infinity
    img = _render_infinity(36, 2)
    assert img.width > img.height > 0
    assert any(p[:3] == (0, 0, 0) and p[3] > 0 for p in img.getdata())
    assert any(p[0] > 180 and p[3] > 200 for p in img.getdata())
```

- [x] **Step 2: 运行测试并复制资源**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_badges.py -k "five_number or infinity"`
Expected: 因 white/yellow 配色和 `_render_infinity` 尚不存在而 FAIL。

执行资源复制，不改动 `assets/ref/`：

```bash
cp assets/ref/能量_大图标.png assets/stats/energy.png
cp assets/ref/倒计时_大图标.png assets/stats/countdown.png
cp assets/ref/气绝倒计时_大图标.png assets/stats/defeated_countdown.png
```

- [x] **Step 3: 实现参考色采样与无限符号**

用参考数字内部亮像素确定五组顶部/底部 RGB，写入 `STAT_COLORS`；新增独立 `STAT_VALUE_COLORS`，不把 white/yellow 开放给普通字段。`_render_digits` 用 `color or "white"`，符号也始终按同一渐变处理。

无限符号不依赖字体缺字：按字号生成两个横向相切椭圆，先画黑色粗轮廓，再画白色细线，裁 alpha bbox 后套 white 渐变。尺寸只由 `font_size` 和 `stroke_width` 决定，原生尺寸调用时随布局字号缩放。

- [x] **Step 4: 跑相关测试并检查真实资源**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_badges.py tests/test_entity_render.py`
Expected: PASS；将 entity 的颜色白名单切换到 `STAT_VALUE_COLORS` 后，既有非法 white/yellow 测试仍通过。

- [x] **Step 5: 提交并推送**

```bash
git add assets/ref assets/stats/energy.png assets/stats/countdown.png assets/stats/defeated_countdown.png bwpdiy/render/badges.py bwpdiy/render/entity.py tests/test_badges.py tests/test_entity_render.py
git commit -m "feat(渲染): 接入状态图标并校准五色数字"
git push
```

---

### Task 2: 大卡爆能组件与布局

**Files:**
- Modify: `bwpdiy/render/badges.py`
- Modify: `bwpdiy/render/pipeline.py:166-216,291-338`
- Modify: `bwpdiy/render/size.py:9-26`
- Modify: `bwpdiy/render/layout.py`
- Modify: `assets/layout.json`、`bwpdiy/render/default_layout.json`
- Test: `tests/test_badges.py`、`tests/test_pipeline.py`、`tests/test_layout.py`

**Interfaces:**
- Consumes: `assets/stats/energy.png`、Task 1 白色数字与符号。
- Produces: `render_element(..., elem={"kind": "burst", ...})`；pipeline 在调用前注入 `elem["_anchor"] = elements["level"]["pos"]`。
- Layout: `burst.offset` 为相对等级底座的二维偏移；`num_offset/group_offset/sign_offset` 沿用现有带符号数字口径。

- [x] **Step 1: 写爆能失败测试**

覆盖正/负/0、无等级仍定位、等级移动跟随和非法位数：

```python
@pytest.mark.parametrize("value, sign", [(10, "plus"), (-10, "minus")])
def test_burst_signed_white_component(assets_dir, sign, value):
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "burst", "_anchor": [100, 60], "offset": [0, 50],
            "icon_size": 50, "num_offset": [0, 0], "font_size": 36,
            "stroke_width": 2, "sign_size_plus": 20, "sign_size_minus": 14,
            "sign_offset": [0, 0], "group_offset": [0, 0]}
    img = render_element(canvas(), lib, "burst", elem,
                         {"type": "法术", "burst": value})
    assert opaque(img) > 0
    assert opaque(render_element(canvas(), lib, "burst", elem,
                                 {"type": "法术", "burst": 0})) == 0
```

在 `test_pipeline.py` 用默认布局渲染 `burst=-10`，再把 `level.pos` 平移 `[7, 9]`，断言爆能区域同步移动而卡名不变；对 `burst=True`、`1.5`、`10**12` 断言 `ValueError`。

- [x] **Step 2: 运行失败测试**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_badges.py tests/test_pipeline.py -k burst`
Expected: 因未知 kind/burst 未渲染而 FAIL。

- [x] **Step 3: 实现爆能渲染和布局回补**

在 `render_element` 增加 `kind == "burst"`：严格校验整数且非 bool、绝对值最多 12 位；中心为 `_anchor + offset`，图标用 `lib.stat_badge("energy")`，数字与符号固定 white，0 返回原画布。抽取现有 stat 的符号+数字块 helper 供 stat/burst 共用，保持旧 stat 像素行为不变。

pipeline 在 `_to_canvas_coords` 后为每个 burst 注入当前 level 的 `_anchor`，并让它参与图标层/数值层分层。`size.py` 把 `offset` 加入坐标对缩放键。`layout.py` 对六类型只回补缺失的 burst 默认元素，再生成框品有效布局；其他旧配置不做无关迁移。

在两份默认 JSON 的六类型常规布局加入 burst；非常规框按需稀疏覆盖。初始值以 `offset=[0,55]`、能量图标 56、字号 40、白色描边 2 为调参起点，最终通过真实预览检查。

- [x] **Step 4: 运行渲染与布局测试**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_badges.py tests/test_pipeline.py tests/test_layout.py`
Expected: PASS；更新元素集合断言为各旧集合加 `burst`，并断言缺新元素的旧布局自动回补、已有 burst 不被覆盖。

- [x] **Step 5: 提交并推送**

```bash
git add bwpdiy/render/badges.py bwpdiy/render/pipeline.py bwpdiy/render/size.py bwpdiy/render/layout.py assets/layout.json bwpdiy/render/default_layout.json tests/test_badges.py tests/test_pipeline.py tests/test_layout.py
git commit -m "feat(大卡): 支持等级下方爆能组件"
git push
```

---

### Task 3: 小卡能量、倒计时与气绝组件

**Files:**
- Modify: `bwpdiy/render/entity.py`
- Modify: `assets/layout.json`、`bwpdiy/render/default_layout.json`
- Test: `tests/test_entity_render.py`、`tests/test_layout.py`

**Interfaces:**
- Consumes: Task 1 三枚图标、五色数字与 `_render_infinity`。
- State: `energy: int | None`、`countdown: int | None`、`defeated_countdown: int | "infinity" | None`。
- Layout: `elements.right_top` 与 `elements.defeated`，均为 `kind: counter`，含 `pos/icon_size/num_offset/font_size/stroke_width`。

- [x] **Step 1: 写状态校验和组件失败测试**

更新默认状态断言，新增：

```python
@pytest.mark.parametrize("state", [
    {"energy": 0, "countdown": 1}, {"energy": -1}, {"energy": True},
    {"countdown": 0}, {"countdown": 1.5}, {"defeated_countdown": 0},
    {"defeated_countdown": -1}, {"defeated_countdown": "inf"},
    {"defeated_countdown": True},
])
def test_entity_rejects_invalid_counter_states(state):
    with pytest.raises(ValueError):
        validate_entity_state(state)


def test_entity_permanent_defeat_accepts_infinity():
    assert validate_entity_state(
        {"defeated_countdown": "infinity"})["defeated_countdown"] == "infinity"
```

用 monkeypatch 记录 `lib.stat_badge` 和 `_render_digits`：energy=0 必须读取 energy 并使用 yellow；countdown=2 使用 countdown/white；气绝+能量保留 energy 且不读取 countdown；气绝+倒计时隐藏普通 countdown；永久气绝调用 `_render_infinity`。0 级携带全部新状态时不得读取状态图标或渲染数字。

- [x] **Step 2: 运行失败测试**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_entity_render.py -k "counter or permanent or level_zero"`
Expected: 因新字段未规范化、新组件未实现而 FAIL。

- [x] **Step 3: 实现状态、灰化和绘制顺序**

在 `validate_entity_state` 规范化三个新字段并执行互斥、整数、位数与 `"infinity"` 校验。`_entity_work_bounds` 只在组件实际显示时计入图标与数字/`∞` 墨迹，返回对应预备图层。

`_render_frame` 后、任何角标绘制前，如果 `defeated_countdown` 非空，使用 `ImageOps.grayscale` 灰化 RGB 并恢复原 alpha。绘制顺序固定：

```python
canvas = _render_level(...)
canvas = _render_existing_stats(...)
canvas = _render_right_top(...)   # 气绝时只允许 energy
canvas = _render_defeated(...)    # 永远最后，普通数字或 infinity
```

right_top 在 energy 非空时用 energy/yellow；否则仅在未气绝且 countdown 非空时用 countdown/white。defeated 使用 defeated_countdown 图标和白字。新元素启用状态、坐标、尺寸、字号和描边沿用现有限幅校验。

- [x] **Step 4: 同步布局并运行测试**

两份默认 JSON 的「对局式神」加入 right_top/defeated；右上初始 `pos=[82,18]`，中央初始 `pos=[48,66]`，图标 28/44、字号 24/40 作为视觉调参起点。`layout.py` 的实体深补全自动带入旧配置，不新增版本迁移倍率。

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_entity_render.py tests/test_layout.py`
Expected: PASS；补充组件越界扩大工作画布、灰化仅影响底框卡图、气绝组件顶层遮挡及 width 原生重绘断言。

- [x] **Step 5: 提交并推送**

```bash
git add bwpdiy/render/entity.py assets/layout.json bwpdiy/render/default_layout.json tests/test_entity_render.py tests/test_layout.py
git commit -m "feat(对局式神): 支持能量倒计时与永久气绝"
git push
```

---

### Task 4: 独立对局预览页与旧控件迁移

**Files:**
- Create: `bwpdiy/web/static/editor-battle.js`
- Modify: `bwpdiy/web/static/editor.html`
- Modify: `bwpdiy/web/static/editor.css`
- Modify: `bwpdiy/web/static/editor-core.js:106-165`
- Modify: `bwpdiy/web/static/editor-cards.js`
- Modify: `bwpdiy/web/static/editor-main.js:89-117`
- Test: `tests/test_web.py`、`tests/test_web_projects.py`

**Interfaces:**
- Consumes: 当前 `formData/curCard/curProject/curMech/cDirty/mDirty`、项目大卡 preview 和 `/api/entity-preview`。
- Produces: `battleStyle`（card/entity）、`battleCardState`、`battleEntityState`、`enterBattlePreview()`、`leaveBattlePreview()`；均不写盘、不修改 dirty。
- Script order: core → cards → battle → mech → layout → main。

- [x] **Step 1: 写前端结构与状态失败测试**

更新静态资源测试包含 editor-battle.js。Node 测试拼接真实脚本，覆盖：

```javascript
assert.deepStrictEqual(battleStyles({type: '式神'}), ['entity']);
assert.deepStrictEqual(battleStyles({type: '式神', shikigami: '白狼'}), ['entity']);
assert.deepStrictEqual(battleStyles({type: '战斗'}), ['card']);
assert.deepStrictEqual(battleStyles({type: '形态'}), ['card', 'entity']);
assert.deepStrictEqual(battleStyles({type: '法术', evolve: true}), ['card', 'entity']);
```

另断言未选卡/机制编辑态进入时显示提示；切换对局控件不改变 `cDirty/mDirty`；离开后重新进入重建临时状态；卡牌库原选择和未保存表单不变。

- [x] **Step 2: 运行失败测试**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_web.py tests/test_web_projects.py -k "battle or editor_static"`
Expected: 因新页面和函数不存在而 FAIL。

- [x] **Step 3: 实现页面、预览和导出**

HTML 在卡牌库与全局布局之间加入 navtab 和 `tab-battle` 三栏；左栏只放样式按钮，中央为图片、状态和导出，右栏为动态表单。`tryShowTab` 支持第三页并保留现有未保存提示。

进入时从 `formData` 深拷贝来源，按 Task 的样式规则初始化：大卡含临时 level/level_color、现有 stat 颜色和 burst；小卡沿用旧 `makeEntityState` 默认值并加入 energy/countdown/defeated_countdown。右上 UI 使用 none/energy/countdown 下拉，气绝复选框控制 defeated_countdown，永久复选框写入 `"infinity"` 并禁用数字输入。

大卡预览把临时副本 POST 到现有项目卡 preview；小卡 POST `{project, card, state}` 到 entity-preview。每通道序号作废旧响应，失败保留上一张有效图。导出复用同一请求和 Blob 文件名清理，不调用保存 API。

- [x] **Step 4: 删除旧对局入口并跑行为测试**

从卡牌库移除 `c-entity`、对局参数表单、实体预览/导出与颜色控件；保留 `c-portrait` 和大卡。标记扩展中的等级 0–3 下拉仍留在卡牌表单，只拆走勾玉颜色；已有 YAML 颜色仅用于初始化新页。`applyExtOptions` 不再因颜色控件重建整套卡牌表单，N/0 等级等标记扩展行为不变。

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_web.py tests/test_web_projects.py`
Expected: PASS；补充 API 测试确认大卡 burst 和实体新状态能经现有 preview 返回 PNG，且请求前后项目 YAML 字节不变。

- [x] **Step 5: 提交并推送**

```bash
git add bwpdiy/web/static/editor.html bwpdiy/web/static/editor.css bwpdiy/web/static/editor-core.js bwpdiy/web/static/editor-cards.js bwpdiy/web/static/editor-battle.js bwpdiy/web/static/editor-main.js tests/test_web.py tests/test_web_projects.py
git commit -m "feat(界面): 新增独立对局预览页"
git push
```

---

### Task 5: 全局布局编辑新组件

**Files:**
- Modify: `bwpdiy/web/static/editor-layout.js`
- Modify: `bwpdiy/web/static/editor.css`
- Test: `tests/test_web.py`、`tests/test_layout.py`

**Interfaces:**
- Consumes: `elements.burst/right_top/defeated` 和现有预览 API。
- Produces: 六类型爆能样例输入、对局右上组件样例下拉、气绝/永久样例开关，以及对应拖拽和右栏参数。

- [x] **Step 1: 写布局交互失败测试**

Node 测试断言：普通类型左栏含爆能；实体类型含右上组件、气绝倒计时；选择 burst 后右栏编辑 `offset/icon_size/num_offset/font_size/stroke_width/sign_offset/group_offset/sign_size_plus/sign_size_minus`；实体 counter 不显示符号参数。

布局样例请求分别包含：

```javascript
{card: {burst: -10}}
{state: {energy: 3}}
{state: {defeated_countdown: 'infinity', energy: 3}}
```

- [x] **Step 2: 运行失败测试**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_web.py -k "layout and (burst or counter or entity)"`
Expected: 因控件和样例状态尚未加入而 FAIL。

- [x] **Step 3: 实现布局控件和拖拽**

扩展 `DISP`、元素列表和 `buildProps`。burst 拖拽把画布点换算为 `offset = 点 - level.pos`；right_top/defeated 直接编辑 `pos`。六类型卡牌内容增加带符号 burst；实体样例增加 none/energy/countdown、数值、气绝和永久开关，修改只刷新样例，不调用 `markDirty()`。

实体布局预览在切换样例时保留布局工作副本；所有新元素继续按 3 倍 CSS 显示和原生坐标反算。更新元素顺序为等级、卡图内窗、力量、生命、战力、护甲、右上组件、气绝倒计时。

- [x] **Step 4: 运行布局与完整前端测试**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_web.py tests/test_layout.py`
Expected: PASS；三份实体默认布局仍一致，保存/还原只影响布局，不保存样例状态。

- [x] **Step 5: 提交并推送**

```bash
git add bwpdiy/web/static/editor-layout.js bwpdiy/web/static/editor.css tests/test_web.py tests/test_layout.py
git commit -m "feat(布局): 支持爆能与气绝组件调参"
git push
```

---

### Task 6: 文档、精简与 1.8.0 全量验收

**Files:**
- Modify: `bwpdiy/__init__.py`、`bwpdiy/changelog.py`
- Modify: `README.md`、`AGENTS.md`、`docs/terminology.md`
- Modify: `docs/superpowers/specs/2026-09-14-bwpdiy-design.md`
- Modify: `docs/integration.md`、`bwpdiy/web/static/editor.html`
- Test: `tests/test_main.py`、`tests/test_web.py`

**Interfaces:**
- Produces: 1.8.0 对外集成字段、GUI 使用说明和默认布局变更提示；不生成发布包。

- [x] **Step 1: 更新版本与文档**

`__version__ = "1.8.0"`。changelog 首条使用：

```python
"<b>本次更新更改了全局布局配置，用户可能需要重新手动调整本地配置。</b>"
```

其余条目简述对局预览、能量/倒计时/永久气绝、爆能和五色校准。集成文档明确 `burst` 不持久化、实体三个新字段及互斥/永久规则；术语表登记 right_top/defeated/burst/infinity；README 与主设计移除旧常驻小卡和能量大图标缺失表述。使用说明改为新对局页流程。

- [x] **Step 2: 做本批次删除清单审查**

检查旧实体预览函数、DOM、CSS 和事件是否全部移除；检查 stat/burst 数字块、counter 数字/边界准备是否复用而非复制；不精简状态/schema/路径/并发/缓存一致性/绘制顺序测试。确认没有意外修改 `library/`、正式版 `$HOME/.bwpdiy/layout.json` 或用户 assets/legacy 删除。

- [x] **Step 3: 运行全量自动验证**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q
git diff --check
```

Expected: 全部测试 PASS，diff 无空白错误。对全部 JS 执行 `node --check`（由现有 web 测试覆盖时仍逐一核对脚本引用）。

- [x] **Step 4: 真实服务端到端验收**

用隔离 HOME 和开发端口启动源码服务，实际选择一张普通卡、一张形态/觉醒和一张主要式神：检查样式可选范围、爆能 -10、能量 0、普通倒计时、气绝+能量、永久 `∞`、数字/勾玉换色和两种导出；调整全局布局新组件并还原，返回卡牌库确认原条目和未保存内容保留。最后通过 `/api/shutdown` 正常结束，不残留后台服务或冒烟文件。

- [x] **Step 5: 提交并推送**

```bash
git add bwpdiy/__init__.py bwpdiy/changelog.py README.md AGENTS.md docs/terminology.md docs/integration.md docs/superpowers/specs/2026-09-14-bwpdiy-design.md docs/superpowers/plans/2026-11-01-battle-preview.md bwpdiy/web/static/editor.html tests/test_main.py tests/test_web.py
git commit -m "feat(发布准备): 完成1.8.0对局预览功能"
git push
```
