# v1.8.3 语义排版 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为卡牌描述增加 `smart` / `wrap` / `off` 三态排版，并在智能模式实现纯关键字首行与条件类候选断行。

**Architecture:** `render/text.py` 负责可见文本解析、候选生成和评分；`render/pipeline.py` 仅在大卡描述入口传入卡牌模式，机制保持原路径。`store/schema.py` 和现有无构建前端增加同一枚举，旧数据及 BWPro 缺省均为 `smart`。

**Tech Stack:** Python 3、Pillow、FastAPI、原生 JavaScript、pytest、Node `--check` / 现有 Node 回归测试。

## Global Constraints

- 不改写原始描述、存档或全局布局；不新增依赖。
- 首行仅识别白名单纯能力短句；突袭、坚守、鼓舞、爆能、运势等带后续效果的能力排除。
- 条件类自动断行前的上一行宽度须达到可用宽度的 35%；字号优先、行数次之。
- `text_layout` 缺省为 `smart`；`wrap` 保持本轮前行为；`off` 仅显式换行且使用最大字号。
- GUI 控件只在「扩展功能」开启时显示，隐藏时保留已保存值；机制不支持该字段。
- render 不得 import store/web；前端保持经典脚本与现有全局词法顺序。

---

### Task 1: 文本排版核心

**Files:**
- Modify: `bwpdiy/render/text.py`
- Test: `tests/test_text.py`

**Interfaces:**
- Produces: `draw_region(..., text_layout="wrap")`、`fit_in_region(..., text_layout="wrap")`；`smart` 生成语义候选，`wrap` 单候选旧行为，`off` 固定最大字号并只按显式换行。
- Internal: 自动断点使用独立 item kind，不与用户显式 `\n` 混淆；候选评分返回 `(行数, 行宽不均衡度, -语义断行数, 候选序号)`，越小越优。

- [ ] **Step 1: 写首行识别与排除项失败测试**

```python
@pytest.mark.parametrize("prefix", ["贯通，连击。", "[[瞬发]]，不消耗鬼火。"])
def test_smart_layout_separates_pure_keyword_sentence(assets_dir, prefix):
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 100, 400, 300)
    _, lines = fit_in_region(prefix + "对敌方战斗区式神造成2点伤害。", region, lib,
                             text_layout="smart")
    assert lines[0][0] == prefix.replace("[[", "").replace("]]", "")[:-1]
    assert "。" not in lines[0][0]
    assert len(lines) > 1

@pytest.mark.parametrize("prefix", ["突袭。", "坚守。", "鼓舞。", "爆能2。", "运势4。"])
def test_smart_layout_does_not_separate_followup_abilities(assets_dir, prefix):
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 100, 400, 300)
    _, lines = fit_in_region(prefix + "随后触发对应效果。", region, lib,
                             text_layout="smart")
    assert lines[0][0] != prefix[:-1]
```

- [ ] **Step 2: 运行首行测试并确认因不支持参数而失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_text.py -k "smart_layout" -q`
Expected: FAIL（`text_layout` 参数尚不存在）。

- [ ] **Step 3: 实现三态入口、首行解析和候选断行**

在 `text.py` 增加集中白名单与 `TEXT_LAYOUT_MODES = ("smart", "wrap", "off")`。智能模式先把开头纯能力短句的末尾 `。` 删除并插入强制断行，再为最多 4 个段内 `条件：` / `增强：` / `响应：` / `觉醒：` 生成换行组合。解析基于现有 `parse_items`，保留高亮和图标 item。

扩展 `_layout_at_size` 的段落拆分以识别自动断点；自动断点收尾时，用 `_line_width(current, font, icon_w) >= 0.35 * available_width` 验收上一行。`_fit` 在同一字号、同一居中点上移量下评价所有候选，先最少行数，再最小均衡惩罚，再较完整语义断行。关键字首行不参与均衡惩罚。

`off` 使用独立显式行排版：最大字号、仅 `\n` 分段、逐行水平居中与整体竖直居中，不调用自动换行、字号递减或障碍掩膜。

- [ ] **Step 4: 补候选比较、35% 阈值及三态测试**

```python
def test_text_layout_wrap_disables_only_semantic_layout(assets_dir):
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 100, 400, 300)
    text = "贯通，连击。随后造成2点伤害。"
    _, smart = fit_in_region(text, region, lib, text_layout="smart")
    _, wrap = fit_in_region(text, region, lib, text_layout="wrap")
    assert smart[0][0] == "贯通，连击"
    assert wrap != smart

def test_text_layout_off_uses_explicit_lines_and_max_font(assets_dir):
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 100, 180, 300)
    font, lines = fit_in_region("甲乙丙丁\n戊己", region, lib, text_layout="off")
    assert font.size == 36
    assert [line[0] for line in lines] == ["甲乙丙丁", "戊己"]

def test_conditional_break_requires_previous_line_35_percent(assets_dir):
    # 用真实字体宽度构造 34% 与 36% 两个边界，直接比较候选是否被接受。
    lib = AssetLibrary(assets_dir)
    font = lib.font("desc", 36)
    assert font.getlength("甲") > 0
```

- [ ] **Step 5: 跑文本与高亮定向回归**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_text.py tests/test_keyword_highlight.py -q`
Expected: PASS；既有标点、图标、显式换行测试不变。

- [ ] **Step 6: 提交文本核心**

```bash
git add bwpdiy/render/text.py tests/test_text.py
git commit -m "feat(排版): 添加三态文本布局与语义候选"
git push
```

### Task 2: 渲染与存档集成

**Files:**
- Modify: `bwpdiy/render/pipeline.py`
- Modify: `bwpdiy/store/schema.py`
- Test: `tests/test_store.py`
- Test: `tests/test_keyword_highlight.py`

**Interfaces:**
- Consumes: Task 1 的 `text_layout` 参数。
- Produces: 卡牌可选 `text_layout: smart|wrap|off`；缺省 `smart`；机制白名单仍拒绝它。

- [ ] **Step 1: 写管线缺省、模式覆盖和 schema 失败测试**

```python
def test_card_text_layout_schema_round_trip():
    for mode in ("smart", "wrap", "off"):
        assert validate_card({**FIGHT, "text_layout": mode}) == []
    assert any("text_layout" in e for e in validate_card({**FIGHT, "text_layout": "auto"}))
    assert any("白名单" in e for e in validate_mechanism(_mech(text_layout="smart")))
```

管线测试 monkeypatch `pipeline.draw_region`，分别渲染缺省、`wrap`、`off` 卡，断言收到的模式为 `smart` / `wrap` / `off`，并断言传入的描述字符串未被修改。

- [ ] **Step 2: 运行测试并确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_store.py tests/test_keyword_highlight.py -k "text_layout" -q`
Expected: FAIL（字段与管线传参尚未接入）。

- [ ] **Step 3: 实现最小集成**

`schema.py` 增加同名枚举常量、`_COMMON_FIELDS` 字段与逐项校验；`pipeline.py` 仅在现有大卡 `draw_region` 调用追加：

```python
text_layout=card.get("text_layout", "smart")
```

不修改机制调用、实体小卡或卡牌描述内容。

- [ ] **Step 4: 跑集成与渲染定向回归**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_store.py tests/test_keyword_highlight.py tests/test_pipeline.py tests/test_pipeline_components.py -q`
Expected: PASS。

- [ ] **Step 5: 提交集成**

```bash
git add bwpdiy/render/pipeline.py bwpdiy/store/schema.py tests/test_store.py tests/test_keyword_highlight.py
git commit -m "feat(卡牌): 接入三态描述排版配置"
git push
```

### Task 3: 扩展功能控件、版本与文档

**Files:**
- Modify: `bwpdiy/web/static/editor-cards.js`
- Modify: `bwpdiy/web/static/editor.html`
- Modify: `bwpdiy/__init__.py`
- Modify: `bwpdiy/changelog.py`
- Modify: `AGENTS.md`
- Modify: `docs/terminology.md`
- Modify: `docs/superpowers/specs/2026-09-14-bwpdiy-design.md`
- Test: `tests/test_web.py`（现有 Node 拼接真实脚本测试）

**Interfaces:**
- Produces: 卡牌右栏「自动排版」单选框，值与显示顺序为 `smart=智能`、`wrap=仅换行`、`off=关闭`，位于描述输入框上方且仅 `extOptions.marker` 时显示。

- [ ] **Step 1: 写前端白名单和控件失败测试**

沿用现有 Node 拼接真实脚本测试，断言 `validateCardJS` 接受三种模式、拒绝非法值；DOM 测试在扩展功能开/关时重建表单，断言选择器显隐、当前值及切换后的 `formData.text_layout`。缺省 `smart` 时删除字段以保持 YAML 稀疏。

- [ ] **Step 2: 运行前端测试并确认失败**

Run: 执行项目现有对应 Node 测试命令，或 `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_web.py -k "text_layout" -q`
Expected: FAIL（控件与白名单尚未实现）。

- [ ] **Step 3: 实现控件和校验**

在 `buildForm` 的内嵌派系样式之后、描述 textarea 之前插入 `selRowC`；选项值用 `smart/wrap/off`，显示用 `智能/仅换行/关闭`。切换时 `smart` 删除字段，其余写字段并调用 `afterEdit()`。把 `text_layout` 加入 `validateCardJS` 白名单和枚举校验。

- [ ] **Step 4: 更新版本、更新说明与持久文档**

版本改为 `1.8.3`；changelog 新增简短条目，不添加全局布局变更警告。使用说明解释三态和智能规则；`AGENTS.md`、术语表与主设计文档记录字段、缺省、排除项和 35% 阈值。同步实施计划勾选状态，不改动出厂布局 JSON。

- [ ] **Step 5: 验证交付物**

Run: `for f in bwpdiy/web/static/editor-*.js; do node --check "$f"; done`
Run: 受影响的文本、schema、管线、Web 与前端定向测试。
Run: `git diff --check`
Expected: 全部通过；按用户要求不机械重复全量 pytest 或 GUI 冒烟。

- [ ] **Step 6: 提交并推送 1.8.3**

```bash
git add bwpdiy tests docs AGENTS.md
git commit -m "feat(排版): 发布1.8.3智能描述排版"
git push
```
