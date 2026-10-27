# 对局式神布局预览调整 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对局式神布局预览以 3 倍显示，完整保留框外元素并紧致裁剪，同时固定元素顺序和验证六色等级标。

**Architecture:** 后端在 `render_entity` 中按实际元素边界扩展透明工作画布，框体仍先按 96×144 渲染，再与平移后的元素合成并统一裁剪。前端只调整布局页显示倍率、固定样卡颜色及列表顺序，不改变导出尺寸或坐标系。

**Tech Stack:** Python 3、Pillow、FastAPI、原生 JavaScript、pytest、Node.js 语法检查。

## Global Constraints

- 用户已选择将当前 `assets/layout.json` 的对局式神布局同步为出厂默认：Task 1 同步 `bwpdiy/render/default_layout.json` 与 `entity._DEFAULT_LAYOUT`，三份配置一致并纳入提交；不得改坏其他卡牌类型布局。
- 正常未越界渲染保持原有像素结果；`crop_origin` 始终使用原 96×144 卡面坐标系。
- 等级标继续使用黄、青、紫、红、蓝、棕六色，不增加新资源。
- 不修改 `legacy/`，不增加依赖。

---

### Task 1: 框外元素完整渲染与紧致裁剪

**Files:**
- Modify: `bwpdiy/render/entity.py`
- Test: `tests/test_entity_render.py`

**Interfaces:**
- Consumes: 现有 `render_entity(card, state, assets_dir, layout=None, crop=True, info=None)`。
- Produces: 同一函数签名；越界元素纳入最终 alpha 裁剪范围，`info["crop_origin"]` 可为负数。

- [ ] **Step 1: 写越界等级标回归测试**

在 `tests/test_entity_render.py` 增加测试：默认渲染先断言原图一致；再把等级标移到底边之外，断言输出高度大于默认紧致图、底边存在非透明像素，且 `crop_origin` 与原卡面坐标一致。

```python
def test_entity_crop_keeps_level_overflow(assets_dir, sample_art):
    card = make_card(sample_art)
    baseline = render_entity(card, {}, assets_dir)
    layout = deepcopy(_DEFAULT_LAYOUT)
    layout["elements"]["level"]["pos"] = [48, 160]
    info = {}
    cropped = render_entity(card, {}, assets_dir, layout=layout, info=info)
    assert cropped.height > baseline.height
    assert info["crop_origin"][1] == 0
    assert cropped.getchannel("A").getbbox()[3] == cropped.height
```

使用现有 `deepcopy` 导入；若文件尚无该导入则从 `copy` 导入。默认一致性沿用现有 `test_entity_crop_is_tight_and_reports_origin`，不重复造测试。

- [ ] **Step 2: 运行测试并确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_entity_render.py -k overflow`

Expected: 新测试 FAIL，旧固定 96×144 工作画布提前裁掉越界等级标。

- [ ] **Step 3: 实现动态工作画布**

在 `entity.py` 增加私有边界辅助函数：等级标取底座与勾玉两个中心/尺寸矩形；数值标取图标矩形和 `_render_digits` 实际图片按现有 round 规则落点的矩形；禁用元素及数值为 0 的战力/护甲不占边界。合并 `(0, 0, 96, 144)` 后用 `floor/ceil` 得到工作范围。

`render_entity` 保持现有卡图与 `_render_frame` 逻辑，随后按以下结构合成：

```python
left, top, right, bottom = _entity_work_bounds(lib, elements, state)
frame = canvas
canvas = Image.new("RGBA", (right - left, bottom - top), (0, 0, 0, 0))
canvas.alpha_composite(frame, (-left, -top))

def shifted(elem):
    return {**elem, "pos": [elem["pos"][0] - left, elem["pos"][1] - top]}

# 按原顺序调用 _render_level/_render_stat，传入 shifted(elements[field])；
# 最终仍用 alpha>10 求 bbox，info["crop_origin"]=(left+bbox[0], top+bbox[1])。
```

`crop=False` 返回扩展后的未裁剪工作画布；既有未越界布局的范围仍是 `(0, 0, 96, 144)`。

- [ ] **Step 4: 运行实体渲染测试**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_entity_render.py`

Expected: 全部 PASS，包括六色、默认尺寸、卡图映射及越界裁剪。

- [ ] **Step 5: 提交并推送**

```bash
git add bwpdiy/render/entity.py tests/test_entity_render.py docs/superpowers/plans/2026-10-26-entity-layout-overflow.md
git commit -m "fix(对局式神): 保留布局元素的框外渲染"
git push
```

### Task 2: 布局页三倍预览、顺序与颜色样卡

**Files:**
- Modify: `bwpdiy/web/static/editor.html`
- Modify: `tests/test_web.py`
- Modify: `AGENTS.md`
- Modify: `docs/superpowers/specs/2026-10-26-entity-layout-overflow-design.md`（仅勾选实施状态如需）

**Interfaces:**
- Consumes: `/api/entity-preview` 的紧致 PNG 与 `X-Crop-Offset`。
- Produces: 布局页 CSS 3 倍显示；样卡请求含 `level_color: "cyan"`；列表顺序为等级、卡图内窗、力量、生命、战力、护甲。

- [ ] **Step 1: 更新前端回归测试**

把 `test_entity_layout_preview_native_size_and_scaled_mouse` 的模拟显示矩形改为 288×432，期望样式改为 `288px`/`432px`，鼠标样本保持映射到 `[48,72]`，请求体增加 `level_color: "cyan"`。新增或扩展 `buildLists` Node 测试，使用乱序元素字典并断言：

```javascript
assert.deepStrictEqual(items.map(x => x.textContent),
  ['等级', '卡图内窗', '力量', '生命', '战力', '护甲']);
```

- [ ] **Step 2: 运行前端测试并确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_web.py -k "entity_layout_preview_native_size or entity_layout"`

Expected: 旧 4 倍样式、默认黄色请求或旧的按 x 排序断言失败。

- [ ] **Step 3: 实施前端调整**

`handleLayoutPreviewResponse` 中把 `entityLayoutMode ? 4 : 1` 改为 `entityLayoutMode ? 3 : 1`。`refreshEntityLayoutPreview` 的 state 增加 `level_color: 'cyan'`。`buildLists` 在 `entityLayoutMode` 时显式遍历 `['level','power','health','combat_power','shield']`，并保留 `art_window` 在等级之后；普通六类型继续原有排序逻辑。

- [ ] **Step 4: 更新项目说明**

把 `AGENTS.md` 对局式神条目中的“布局小卡仅 CSS 放大”明确为“布局小卡 CSS 3 倍显示；元素可越出 96×144 框体并按联合可见边界裁剪”。不改动用户布局数值。

- [ ] **Step 5: 运行完整验证**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q
sed -n '/<script>/,/<\/script>/p' bwpdiy/web/static/editor.html | sed '1d;$d' > /tmp/editor.js
node --check /tmp/editor.js
git diff --check
```

Expected: 全量测试 PASS，JS 无语法错误，diff 无空白错误。

- [ ] **Step 6: 浏览器实测并重启试用服务**

保留现有服务于 8630；代码重载后确认 `/api/version` 为 1.7.0。实测 3 倍布局预览、等级标越界完整显示、力量/生命/战力/护甲顺序及黄色勾玉；不保存覆盖用户布局。

- [ ] **Step 7: 提交并推送**

```bash
git add bwpdiy/web/static/editor.html tests/test_web.py AGENTS.md docs/superpowers
git commit -m "fix(编辑器): 调整对局式神布局预览"
git push
```
