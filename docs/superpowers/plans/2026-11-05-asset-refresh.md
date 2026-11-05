# 美术资源更新与对局特殊状态 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 接入本批新美术资源，以位图数字替换字体数字，并为卡牌/机制提供内嵌派系样式和大卡特殊状态预览。

**Architecture:** 保留现有纯 PIL 渲染管线与 Web 编辑器，只在 `AssetLibrary` 扩展新资源入口，在既有元素渲染器中替换数字实现并增加 `status` 元素。布局坐标、原生缩放、墨迹间距、临时预览状态和 BWPro 的颜色契约保持兼容。

**Tech Stack:** Python 3.13、Pillow、FastAPI、原生 JavaScript、pytest、Node.js 语法检查。

## Global Constraints

- 设计依据：`docs/superpowers/specs/2026-11-05-asset-refresh-design.md`。
- 测试命令：`PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`；迭代期只跑本任务受影响文件。
- 数值最多 10 位；内部数字颜色仍为 `white/red/green/purple/yellow`，只有文件名把 `yellow` 映射为 `orange`。
- 对局小卡战力/乏力使用 `icons/combat_power.png` 与 `icons/weak.png`，不得切换到 stats 大图。
- `level_4_*`、`level_3_4_*` 不接引用；机制 seal 不提供 shown；赏金大角标不实现。
- 旧 `stroke_width` 可留在配置中但不再影响位图数字，不迁移其他布局键。
- 用户素材已在工作区，禁止覆盖其内容；只新增 `orange_minus.png`、`purple_plus.png`、`purple_minus.png` 三枚合成符号。
- 每次提交只暂存本任务文件并立即 `git push`；最终全量测试由主上下文亲跑。

---

### Task 1: 新资源入口、稀有度回退与八色勾玉

**Files:**
- Modify: `bwpdiy/render/assets.py:45-76`
- Modify: `bwpdiy/render/text.py:52-66`
- Modify: `bwpdiy/render/mech.py:318-327`
- Modify: `bwpdiy/render/entity.py:29`
- Modify: `bwpdiy/store/schema.py:31-37,176-277`
- Modify: `bwpdiy/web/static/editor-core.js:29-36`
- Test: `tests/test_assets.py`, `tests/test_entity_render.py`, `tests/test_store.py`, `tests/test_text.py`
- Assets: `assets/icons/`, `assets/levels/`, `assets/rarity/`, `assets/stats/`, `assets/badges/`, `assets/mech/`

**Interfaces:**
- Produces: `AssetLibrary.number(color: str, name: str) -> Image.Image`，读取 `numbers/<color>_<name>.png`。
- Produces: `AssetLibrary.badge(name: str) -> Image.Image`，读取 `badges/badge_<name>.png`。
- Produces: 八色集合 `yellow/cyan/purple/red/blue/brown/greyblue/orange`；`AssetLibrary.sign(name)` 暂时保留并转调 `number("white", name)`。

- [ ] **Step 1: 写资源与颜色的失败测试**

在 `tests/test_assets.py` 增加：

```python
def test_new_number_badge_and_reinforce_fallback(assets_dir):
    lib = AssetLibrary(assets_dir)
    assert lib.number("white", "0").size == (36, 64)
    assert lib.number("orange", "plus").mode == "RGBA"
    assert lib.badge("shown").size == (64, 64)
    assert lib.rarity("SR", "reinforce") is lib.rarity("SR")
    assert lib.icon("bounty").mode == "RGBA"
```

在 `tests/test_entity_render.py` 增加：

```python
def test_entity_accepts_greyblue_and_orange_level_colors():
    for color in ("greyblue", "orange"):
        assert validate_entity_state({"level_color": color})["level_color"] == color
```

在 `tests/test_store.py` 对 `{**SHIKIGAMI, "level_color": "greyblue"}` 与 `"orange"` 断言 `validate_card(...) == []`，并补 `ICON_CODES["sj"] == "bounty"`。

- [ ] **Step 2: 跑测试确认失败原因**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_assets.py tests/test_entity_render.py tests/test_store.py tests/test_text.py`
Expected: 新用例因缺少 `number/badge`、新颜色或 bounty 映射而失败；旧 signs/reinforce 路径也可能已因用户素材删除而失败。

- [ ] **Step 3: 实现最小资源映射**

```python
def rarity(self, rarity: str, variant: str = "norm") -> Image.Image:
    if rarity == "N":
        return self._img("rarity/N.png")
    rel = f"rarity/{rarity}_{variant}.png"
    if not (self.root / rel).is_file():
        rel = f"rarity/{rarity}.png"
    return self._img(rel)

def number(self, color: str, name: str) -> Image.Image:
    return self._img(f"numbers/{color}_{name}.png")

def badge(self, name: str) -> Image.Image:
    return self._img(f"badges/badge_{name}.png")

def sign(self, name: str) -> Image.Image:
    return self.number("white", name)
```

`ICON_CODES` 增加 `"sj": "bounty"`；机制角标改为 `lib.badge(badge)`。entity、store 和前端 `LEVEL_COLORS` 同步加入 `greyblue/orange`，前端显示名分别为灰蓝、橙。不要改 `entity._stat_icon`，它继续使用 `lib.icon("combat_power"/"weak")`。

- [ ] **Step 4: 跑资源与文本测试**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_assets.py tests/test_entity_render.py tests/test_store.py tests/test_text.py`
Expected: 除尚未接入位图数字的测试外均通过；若旧 signs 用例失败，将其改为 `lib.number("white", "plus"/"minus")` 后重跑。

- [ ] **Step 5: 提交并推送**

```bash
git add assets/icons assets/levels assets/rarity assets/stats assets/badges assets/mech bwpdiy/render/assets.py bwpdiy/render/text.py bwpdiy/render/mech.py bwpdiy/render/entity.py bwpdiy/store/schema.py bwpdiy/web/static/editor-core.js tests/test_assets.py tests/test_entity_render.py tests/test_store.py tests/test_text.py
git commit -m "feat(资源): 接入新图标与八色勾玉"
git push
```

### Task 2: 位图数字、符号与永久气绝

**Files:**
- Create: `scripts/build_number_signs.py`
- Create: `assets/numbers/orange_minus.png`, `assets/numbers/purple_plus.png`, `assets/numbers/purple_minus.png`
- Modify: `bwpdiy/render/badges.py:61-294,348-424`
- Modify: `bwpdiy/render/entity.py:315-415`
- Modify: `bwpdiy/web/static/editor-layout.js:788-843`
- Test: `tests/test_badges.py`, `tests/test_entity_render.py`, `tests/test_pipeline.py`, `tests/test_render_size.py`, `tests/test_web.py`
- Assets: `assets/numbers/`, deleted `assets/signs/`, deleted `assets/ref/`

**Interfaces:**
- Consumes: Task 1 的 `AssetLibrary.number(color, name)`。
- Produces: `_render_digits(text: str, lib: AssetLibrary, font_size: int, color: str = "white", gap: float = 3) -> Image.Image`。
- Produces: `_render_infinity(lib: AssetLibrary, font_size: int) -> Image.Image`。
- Produces: `_render_sign(lib, name, size, color)`，按颜色读取对应位图符号，不再程序 tint。

- [ ] **Step 1: 写位图尺寸、颜色和间距失败测试**

在 `tests/test_badges.py` 增加真实资源测试：

```python
def test_bitmap_digits_use_assets_scale_and_ink_gap(assets_dir):
    lib = AssetLibrary(assets_dir)
    one = _render_digits("1", lib, 64, "white")
    bbox = lib.number("white", "1").getchannel("A").getbbox()
    assert one.size == (bbox[2] - bbox[0], bbox[3] - bbox[1])
    yellow = _render_digits("1", lib, 64, "yellow")
    orange = _render_digits("1", lib, 64, "orange")
    assert yellow.tobytes() == orange.tobytes()
    pair = _render_digits("41", lib, 64, "white")
    assert pair.height == one.height and pair.width > one.width
```

为 `white_inf`、三色合成符号和原生 2 倍缩放分别断言尺寸、alpha 非空及 `yellow→orange` 映射。Node 测试断言 stat/burst/counter 右栏不再出现“描边宽度”。

- [ ] **Step 2: 跑测试确认旧接口不满足**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_badges.py tests/test_entity_render.py tests/test_render_size.py tests/test_web.py -k "bitmap or infinity or native or props"`
Expected: 因 `_render_digits` 新签名、位图 infinity 或描边控件仍存在而失败。

- [ ] **Step 3: 生成三枚缺失符号并目检**

新建 `scripts/build_number_signs.py`：读取 `white_plus/minus`，以对应颜色 `0.png` 的顶部、底部高亮像素均值作为渐变端色，调用现有 `_tint` 着色；plus 放入 27×64 画布，minus 放入 21×64 画布。核心函数：

```python
def make_sign(color, name, size):
    source = Image.open(NUMBERS / f"white_{name}.png").convert("RGBA")
    if source.size != size:
        canvas = Image.new("RGBA", size)
        canvas.alpha_composite(source, ((size[0]-source.width)//2,
                                        (size[1]-source.height)//2))
        source = canvas
    top, bottom = sample_gradient_endpoints(Image.open(NUMBERS / f"{color}_0.png"))
    _tint(source, top, bottom).save(NUMBERS / f"{color}_{name}.png")
```

`sample_gradient_endpoints` 对每行只统计 alpha≥200 且亮度>60 的像素，分别取最上/最下有内容行的 RGB 均值。运行脚本后必须用 `ReadMediaFile` 查看三枚 PNG，确认轮廓、渐变和画布尺寸。

- [ ] **Step 4: 替换数字实现**

增加内部映射和单字加载：

```python
_NUMBER_FILE_COLOR = {"yellow": "orange"}

def _number_image(lib, color, name, font_size):
    color = _NUMBER_FILE_COLOR.get(color, color)
    img = lib.number(color, name)
    height = max(1, round(font_size))
    img = img.resize((max(1, round(img.width * height / img.height)), height),
                     Image.Resampling.LANCZOS)
    bbox = img.getchannel("A").getbbox()
    return img.crop(bbox) if bbox else None
```

`_render_digits` 逐字调用 `_number_image`，保留现有 `_row_ink_extents` 最小墨迹间距拼接，不再接收 font/stroke，不再调用 `_render_ink/_tint`。entity 的调用改为 `lib, elem["font_size"]`；`white_inf` 走同一缩放函数。`_render_sign` 按当前颜色读取 `lib.number(mapped_color, name)`，保留裁 bbox 后 contain 到 sign_size 的规则。

删除 GUI 中 stat 的描边行，以及 burst/counter 的描边行；保留 JSON 中已有 `stroke_width` 但不再读取。同步修改所有 monkeypatch 的 `_render_digits/_render_infinity` 签名。

- [ ] **Step 5: 跑渲染与前端测试**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_badges.py tests/test_entity_render.py tests/test_pipeline.py tests/test_render_size.py tests/test_web.py`
Expected: 全部通过；不得通过回退字体规避缺失资源。

- [ ] **Step 6: 提交并推送**

```bash
git add assets/numbers assets/signs assets/ref scripts/build_number_signs.py bwpdiy/render/badges.py bwpdiy/render/entity.py bwpdiy/web/static/editor-layout.js tests/test_badges.py tests/test_entity_render.py tests/test_pipeline.py tests/test_render_size.py tests/test_web.py
git commit -m "feat(渲染): 切换五色位图数字与符号"
git push
```

### Task 3: 卡牌与机制的逐条目内嵌派系样式

**Files:**
- Modify: `bwpdiy/store/schema.py:39-130,156-173,176-277`
- Modify: `bwpdiy/render/text.py:133-164,330-417`
- Modify: `bwpdiy/render/pipeline.py:212-216`
- Modify: `bwpdiy/render/mech.py:265-347`
- Modify: `bwpdiy/web/static/editor-cards.js:969-1024,1330-1433`
- Modify: `bwpdiy/web/static/editor-mech.js:75-137`
- Modify: `bwpdiy/web/static/editor-core.js:147-170`
- Modify: `bwpdiy/web/static/editor.html` 的标记扩展说明
- Test: `tests/test_store.py`, `tests/test_text.py`, `tests/test_mech_render.py`, `tests/test_web.py`

**Interfaces:**
- Produces: 卡牌/机制可选 `inline_faction_style: 1|2|3`，缺省 1。
- Produces: `draw_region(..., inline_faction_style: int = 1)`；文本内部 `_icon_image/_icon_size/_icon_widths/_draw_styled_line` 同步增加同名关键字参数。

- [ ] **Step 1: 写样式持久化与渲染失败测试**

```python
def test_inline_faction_style_selects_variant(assets_dir, monkeypatch):
    lib = get_library(assets_dir)
    calls = []
    original = lib.icon
    monkeypatch.setattr(lib, "icon", lambda name: calls.append(name) or original(name))
    one = _icon_image("hl", lib, None, 1)
    three = _icon_image("hl", lib, "black", 3)
    assert calls == ["faction_red_1", "faction_red_3"]
    assert one.tobytes() != three.tobytes()
    with pytest.raises(ValueError, match="inline_faction_style"):
        _icon_image("hl", lib, None, 4)
```

store 测试断言卡牌和机制接受 1/3、拒绝 0/4/True；Node 测试断言只有 `extOptions.marker=true` 时出现“内嵌派系样式”。

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_store.py tests/test_text.py tests/test_mech_render.py tests/test_web.py -k "inline_faction"`
Expected: 因新参数、schema 字段或控件不存在而失败。

- [ ] **Step 3: 实现渲染与 schema 透传**

`_icon_image` 仅对派系代码改文件名，不再读取 `_black`：

```python
stem = ICON_CODES[code]
if stem.startswith("faction_"):
    if isinstance(inline_faction_style, bool) or inline_faction_style not in (1, 2, 3):
        raise ValueError("inline_faction_style 必须是 1、2 或 3")
    stem = f"{stem}_{inline_faction_style}"
img = lib.icon(stem)
```

将样式参数贯穿排版与绘制函数；`pipeline.draw_region` 传 `card.get("inline_faction_style", 1)`，mech 在 `_wrap_items/_icon_widths/_draw_styled_line` 三处传 `mech.get("inline_faction_style", 1)`。schema 把该字段加入 `_COMMON_FIELDS` 与 `_MECH_FIELDS`，复用 `FACTION_STYLES` 做严格整数校验。

- [ ] **Step 4: 实现前后端控件**

卡牌表单在描述前添加：

```javascript
if (extOptions.marker) selRowC(div, '内嵌派系样式', ['1', '2', '3'],
  String(formData.inline_faction_style ?? 1), v => {
    const style = parseInt(v, 10);
    if (style === 1) delete formData.inline_faction_style;
    else formData.inline_faction_style = style;
    afterEdit();
  });
```

机制表单用 `mechForm` 与 `setMechField` 写同样逻辑，缺省 1 时删除字段。前端 `allowedFieldsForType/validateCardJS/validateMechJS` 与 store 同步，标记扩展说明补该字段。

- [ ] **Step 5: 跑任务测试并提交**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_store.py tests/test_text.py tests/test_mech_render.py tests/test_web.py`
Expected: 全部通过。

```bash
git add bwpdiy/store/schema.py bwpdiy/render/text.py bwpdiy/render/pipeline.py bwpdiy/render/mech.py bwpdiy/web/static/editor-cards.js bwpdiy/web/static/editor-mech.js bwpdiy/web/static/editor-core.js bwpdiy/web/static/editor.html tests/test_store.py tests/test_text.py tests/test_mech_render.py tests/test_web.py
git commit -m "feat(文本): 支持逐条目内嵌派系样式"
git push
```

### Task 4: 大卡 status 渲染与布局后端

**Files:**
- Modify: `bwpdiy/render/assets.py`（仅补 badge 方法，若 Task 1 已完成则不改）
- Modify: `bwpdiy/render/badges.py:297-348`
- Modify: `bwpdiy/render/pipeline.py:301-314`
- Modify: `bwpdiy/render/layout.py:57-66`
- Modify: `bwpdiy/render/default_layout.json` 六类型 elements
- Test: `tests/test_layout.py`, `tests/test_pipeline.py`, `tests/test_pipeline_components.py`, `tests/test_web_projects.py`

**Interfaces:**
- Consumes: `AssetLibrary.badge(name)`。
- Produces: `kind="status"` 元素 `{offset:[x,y], icon_size:int}`；pipeline 注入 `_anchor=level.pos`。
- Produces: 临时卡牌字段 `status: None|"bless"|"eclipse"|"shown"`，无等级仍绘制，不进入 store schema。

- [ ] **Step 1: 写 status 失败测试**

```python
from PIL import ImageChops

@pytest.mark.parametrize("status", ["bless", "eclipse", "shown"])
def test_status_draws_at_level_anchor_without_card_level(assets_dir, sample_art, status):
    card = make_card(sample_art.parent, "法术", description="")
    card.pop("level", None)
    card["status"] = status
    layout = get_type_layout(load_layouts(assets_dir), "法术")
    empty = render_card(dict(card, status=None), assets_dir, layout=layout, crop=False)
    marked = render_card(card, assets_dir, layout=layout, crop=False)
    assert ImageChops.difference(marked.convert("RGB"), empty.convert("RGB")).getbbox() is not None
```

另测 `status=None` 不画、非法值抛 `ValueError`、移动 `level.pos` 后位移一致、六类型默认均含 status、旧配置补默认但不覆盖已有值。

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_layout.py tests/test_pipeline.py tests/test_pipeline_components.py -k "status or expected_elements"`
Expected: 因元素缺失或 kind 未实现而失败。

- [ ] **Step 3: 实现 status 元素与默认回填**

在 `render_element` 的 stat/burst 分支前加入：

```python
if kind == "status":
    value = card.get("status")
    if value is None:
        return canvas
    if value not in ("bless", "eclipse", "shown"):
        raise ValueError("特殊状态必须是 bless、eclipse、shown 或 None")
    anchor, offset = elem["_anchor"], elem.get("offset", [0, 0])
    pos = (anchor[0] + offset[0], anchor[1] + offset[1])
    return _paste_element(canvas, lib.badge(value), pos,
                          (elem["icon_size"], elem["icon_size"]))
```

pipeline 对 `("burst", "status")` 都注入 `_anchor`。六类型默认 elements 增加 `"status":{"kind":"status","offset":[0,-55],"icon_size":40}`。把 `_fill_burst_defaults` 泛化为 `_fill_element_defaults`，对 burst/status 分别补默认，保留已有自定义元素。测试辅助 `render_one/_anchor_box/_neighborhood` 同步支持 status，默认样例设 `status="bless"`。

- [ ] **Step 4: 跑后端测试并提交**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_layout.py tests/test_pipeline.py tests/test_pipeline_components.py tests/test_web_projects.py`
Expected: 全部通过。

```bash
git add bwpdiy/render/assets.py bwpdiy/render/badges.py bwpdiy/render/pipeline.py bwpdiy/render/layout.py bwpdiy/render/default_layout.json tests/test_layout.py tests/test_pipeline.py tests/test_pipeline_components.py tests/test_web_projects.py
git commit -m "feat(卡面): 增加特殊状态渲染元素"
git push
```

### Task 5: 对局预览与布局编辑器接入 status

**Files:**
- Modify: `bwpdiy/web/static/editor-battle.js:70-78,255-275`
- Modify: `bwpdiy/web/static/editor-layout.js:7-20,714-843`
- Modify: `bwpdiy/web/static/editor.html` 的使用说明
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: Task 4 的临时 `card.status` 与 status 布局元素。
- Produces: 大卡对局预览“特殊状态”单选；布局页 status 拖拽、offset 和 icon_size 编辑。

- [ ] **Step 1: 写 Node 失败测试**

扩展对局控件驱动：大卡状态初始为 `null`，选择 `shown` 后断言 `battleCardState.status === "shown"`、`formData.status === undefined`、布局脏标记不变、预览请求包含 status。布局测试仿照 burst 断言：元素列表含“特殊状态”，拖拽修改 `status.offset` 而非 `pos`，右栏只有偏移与图标尺寸，不出现数字/符号/描边参数。

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_web.py -k "status or battle_entity_controls or burst"`
Expected: 因下拉、拖拽或布局控件缺失而失败。

- [ ] **Step 3: 实现预览与布局交互**

`enterBattlePreview` 初始化：

```javascript
battleCardState.status = ['bless', 'eclipse', 'shown'].includes(formData.status)
  ? formData.status : null;
```

大卡表单在爆能后加入：

```javascript
battleSelectRow(div, '特殊状态', [['', '无'], ['bless', '加护'],
  ['eclipse', '蚀印'], ['shown', '已展示']], state.status || '',
  value => setBattleCardField('status', value || null));
```

布局页把 burst/status 的锚点计算、拖拽和 offset 属性合并为 `['burst','status'].includes(e.kind)`；status 单独只显示 `icon_size`，burst 保留数字与符号控件。`DISP` 增加 `status:'特殊状态'`，测试辅助同步。使用说明补三种状态仅临时预览。

- [ ] **Step 4: 跑前端测试并提交**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_web.py`
Expected: 全部通过；`node --check bwpdiy/web/static/editor-battle.js` 与 `editor-layout.js` 也通过。

```bash
git add bwpdiy/web/static/editor-battle.js bwpdiy/web/static/editor-layout.js bwpdiy/web/static/editor.html tests/test_web.py
git commit -m "feat(对局预览): 支持特殊状态选择与布局"
git push
```

### Task 6: 文档、精简与端到端验收

**Files:**
- Modify: `AGENTS.md`, `docs/terminology.md`, `docs/integration.md`
- Modify: `docs/superpowers/specs/2026-09-14-bwpdiy-design.md`
- Modify: `README.md`, `bwpdiy/changelog.py`（仅在确定发布版本后）
- Modify: `docs/asset-mapping-v1.0.md` 中仍描述旧路径的条目

- [ ] **Step 1: 清理旧引用并同步契约**

明确：reinforce 稀有度回退基础版、八色勾玉、`inline_faction_style`、位图数字的 font_size 口径、stroke_width 遗留无效、badges 新目录、status 临时字段、shown 不进机制、level 4/3_4 备用、战力乏力仍用 icons。不得保留“黄字程序渐变”“墨染自动 _black”“赏金小图标缺失”等旧描述。

- [ ] **Step 2: 做删除清单式精简**

搜索 `_render_ink`、旧 signs、`reinforce_R`、`_black`、旧 `_render_digits` 签名和 `lib.mech("badge_")`。删除只为旧字体数字服务的死代码与重复测试；schema、数值边界、路径安全、资源缺失和原生缩放断言不得删除。

- [ ] **Step 3: 真实 API 冒烟**

用隔离 HOME 启动开发服务，分别请求：

- 普通/墨染大卡，R/SR/SSR/N 与协战稀有度；
- 白/红/绿/紫/黄的多位带符号数字与 10 位上限；
- 1/2/3 内嵌派系的卡牌和机制；
- 无等级卡 + 三种 status；
- 小卡能量/倒计时 0/永久气绝与 2 倍原生尺寸。

保存输出到临时目录并逐张用媒体读取检查；结束服务，不修改正式 `$HOME/.bwpdiy/layout.json` 与 `library/`。

- [ ] **Step 4: 最终全量验证**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q
for file in bwpdiy/web/static/editor-*.js; do node --check "$file" || exit 1; done
git diff --check
git status --short
```

Expected: 全量 pytest 0 失败，JS 无语法错误，diff 无空白错误；工作区不含临时冒烟文件。

- [ ] **Step 5: 提交并推送文档收尾**

```bash
git add AGENTS.md README.md docs bwpdiy/changelog.py
git commit -m "docs(资源): 同步位图数字与特殊状态契约"
git push
```
