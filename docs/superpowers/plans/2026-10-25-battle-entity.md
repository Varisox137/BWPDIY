# 对局式神小卡 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为式神、形态和觉醒卡增加 64×96 对局式神小卡的临时实时预览、全局布局和 PNG 导出，不改动来源卡数据。

**Architecture:** 新增纯 PIL `render_entity` 与独立「对局式神」布局段；Web 只增加无持久化预览接口。前端卡牌库临时模式和全局布局模式分开，复用现有预览响应、资源缓存与布局画布，但不复用普通卡牌 stat 分派。

**Tech Stack:** Python 3.13、Pillow、FastAPI、vanilla JavaScript、pytest、Node `--check`、本机 Edge + Playwright 冒烟。

## Global Constraints

- 设计事实来源：`docs/superpowers/specs/2026-10-25-battle-entity-design.md`；版本保持 1.6.3，不打包发布。
- 来源资格仅为 `type in {"式神", "形态"}` 或 `evolve is True`；不新增 CARD_TYPES、不修改项目存储和版本模型。
- 框体原生 64×96；`power/health` 非负且 0 显示；`combat_power/shield` 按正负切图标、0 隐藏，负数画绝对值。
- 卡图只继承 `offset_x/offset_y/rotate`；`state.art_scale` 独立替换来源 scale，以原画尺寸作 cover 基准，默认 1.0。
- `render` 不得 import `store/web`；卡图路径必须留在服务端指定 `_base_dir` 内，保留像素上限。
- 出厂布局变化必须在 changelog 1.6.3 首条加粗提示；每次 commit 后 push，全量测试由主上下文亲跑。

---

### Task 1: 独立对局式神渲染器

**Files:**
- Modify: `bwpdiy/render/artwork.py`
- Modify: `bwpdiy/render/pipeline.py`
- Create: `bwpdiy/render/entity.py`
- Modify: `bwpdiy/render/__init__.py`
- Create: `tests/test_entity_render.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Produces: `entity_eligible(card: dict) -> bool`、`validate_entity_state(state: dict) -> dict`、`render_entity(card: dict, state: dict, assets_dir: Path, layout: dict | None = None, crop: bool = True, info: dict | None = None) -> Image.Image`。
- Produces: `artwork_ref(card: dict) -> dict` 与 `load_card_artwork(card: dict, library: AssetLibrary) -> tuple[tuple[int, int], Image.Image]`，供普通卡和实体共用。
- Consumes: 现有 `fit_artwork`、`get_library`、`_paste_element`、`_render_digits`。

- [ ] **Step 1: 写渲染失败测试**

```python
def test_entity_native_size_and_zero_stats(assets_dir, sample_art):
    card = {"type": "式神", "name": "样例", "level": 2,
            "_base_dir": str(sample_art.parent),
            "artwork": {"images": [{"path": sample_art.name}]}}
    state = {"power": 0, "health": 0, "combat_power": 0, "shield": 0}
    image = render_entity(card, state, assets_dir, crop=False)
    assert image.size == (64, 96)
    assert image.mode == "RGBA"


def test_entity_signed_modifiers_pick_icons(assets_dir, sample_art, monkeypatch):
    card = {"type": "形态", "name": "样例", "_base_dir": str(sample_art.parent),
            "artwork": {"images": [{"path": sample_art.name}]}}
    lib = get_library(assets_dir)
    names = []
    original = lib.icon
    monkeypatch.setattr(lib, "icon", lambda name: names.append(name) or original(name))
    render_entity(card, {"combat_power": -2, "shield": 3}, assets_dir)
    assert "weak" in names and "shield" not in names
```

另写参数化测试：`combat_power` 正/负/0、`shield` 正/负/0；`art_scale=2` 与来源 `scale=99` 同时存在时仍按 2 渲染；偏移和旋转沿用来源；六色等级；`crop=True` 非空紧致 bbox；布尔、负数力量、非法等级/颜色/缩放抛 `ValueError`；越界卡图抛 `ValueError`。

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_entity_render.py -q`
Expected: FAIL，原因是 `bwpdiy.render.entity` 尚不存在。

- [ ] **Step 3: 提取共享卡图加载并实现实体渲染**

`artwork.py` 新增以下两个函数，普通 `pipeline.py` 改为调用它们，保持现有异常文本和路径安全行为：

```python
def artwork_ref(card: dict) -> dict:
    images = card.get("artwork", {}).get("images") or [{}]
    ref = dict(images[0])
    ref.setdefault("path", f"{card.get('id', card['name'])}.png")
    for key, default in (("offset_x", 0), ("offset_y", 0),
                         ("scale", 1.0), ("rotate", 0)):
        ref.setdefault(key, default)
    return ref


def load_card_artwork(card: dict, library) -> tuple[tuple[int, int], Image.Image]:
    ref = artwork_ref(card)
    base_dir = Path(card.get("_base_dir", "."))
    path = Path(ref["path"])
    path = path if path.is_absolute() else base_dir / path
    try:
        path.resolve().relative_to(base_dir.resolve())
    except ValueError:
        raise ValueError(f"卡图路径越出基准目录: {ref['path']}") from None
    if not path.is_file():
        raise FileNotFoundError(f"卡图缺失: {path}")
    return library.artwork(path, ref["rotate"])
```

`entity.py` 以 64×96 RGBA 画布绘制圆角内窗和三层描边；`validate_entity_state` 返回仅含合法键的规范化副本。卡图在内窗绘制，偏移按 `内窗宽 / 512` 等比换算，缩放只取 `state["art_scale"]`：

```python
scale_xy = inner_size[0] / 512
original, rotated = load_card_artwork(card, lib)
art = fit_artwork(rotated, inner_size,
                  ref["offset_x"] * scale_xy, ref["offset_y"] * scale_xy,
                  state["art_scale"], cover_base=original)
```

数值组件复用 `_paste_element` 和 `_render_digits`：力量/生命从 `stats/` 读取，战力/乏力从 `icons/combat_power.png`、`icons/weak.png` 读取，护甲/破甲从 `stats/combat_shield.png`、`stats/combat_fragile_2.png` 读取。等级只叠 `level_base` 与 `level_num`，不画觉醒星。`info["crop_origin"]` 按最终 bbox 左上角回填。

- [ ] **Step 4: 运行渲染与既有普通卡回归**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_entity_render.py tests/test_pipeline.py tests/test_badges.py -q`
Expected: PASS；普通卡输出与共享卡图提取前一致。

- [ ] **Step 5: 提交并推送**

```bash
git add bwpdiy/render tests/test_entity_render.py tests/test_pipeline.py
git commit -m "feat(渲染): 新增64像素对局式神小卡独立渲染器"
git push
```

### Task 2: 独立布局段与只读预览 API

**Files:**
- Modify: `assets/layout.json`
- Modify: `bwpdiy/render/default_layout.json`
- Modify: `bwpdiy/render/layout.py`
- Modify: `bwpdiy/web/app.py`
- Modify: `tests/test_layout.py`
- Modify: `tests/test_web.py`
- Modify: `tests/test_web_projects.py`

**Interfaces:**
- Consumes: Task 1 的 `render_entity`、`entity_eligible`、`validate_entity_state`。
- Produces: `POST /api/entity-preview`，body `{project?, card, state, layout?}`，返回 PNG 与 `X-Crop-Offset`。
- Produces: `layouts["对局式神"] = {"elements": {}}` 的元素表结构，无 `text_regions`。

- [ ] **Step 1: 写布局与 API 失败测试**

```python
def test_entity_layout_backfilled(tmp_path):
    (tmp_path / "layout.json").write_text('{"式神": {"elements": {}, "text_regions": {}}}',
                                           encoding="utf-8")
    layouts = load_layouts(tmp_path)
    assert layouts["对局式神"]["elements"]["level"]["pos"] == [32, 88]


def test_entity_layout_preview(client):
    response = client.post("/api/entity-preview", json={
        "card": {"type": "形态", "name": "样例"},
        "state": {"level": 3, "level_color": "cyan", "power": 2,
                  "health": 5, "combat_power": -1, "shield": 4},
    })
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert "x-crop-offset" in response.headers
```

项目测试增加：式神/形态/觉醒均 200、普通战斗 422、非法 state 和 bool 422、请求 `_base_dir` 不被信任、目录外图拒绝、缺图回退、请求前后 yaml 字节不变。既有 `test_put_layout_partial_types` 的补段预期加入「对局式神」。

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_layout.py tests/test_web.py tests/test_web_projects.py -q`
Expected: FAIL，缺「对局式神」布局与 `/api/entity-preview`。

- [ ] **Step 3: 添加默认布局和旧配置补齐**

两份布局 JSON 增加相同独立段，初值如下，后续以真实小卡人工微调：

```json
"对局式神": {
  "elements": {
    "level": {"kind": "level_badge", "pos": [32, 88], "base_size": 18, "num_size": 14, "num_offset": [0, 0]},
    "power": {"kind": "stat", "field": "power", "pos": [10, 82], "icon_size": 16, "num_offset": [0, 10], "font_size": 14, "stroke_width": 1},
    "health": {"kind": "stat", "field": "health", "pos": [54, 82], "icon_size": 16, "num_offset": [0, 10], "font_size": 14, "stroke_width": 1},
    "combat_power": {"kind": "stat", "field": "combat_power", "pos": [10, 62], "icon_size": 14, "num_offset": [0, 9], "font_size": 12, "stroke_width": 1},
    "shield": {"kind": "stat", "field": "shield", "pos": [54, 62], "icon_size": 14, "num_offset": [0, 9], "font_size": 12, "stroke_width": 1}
  }
}
```

`load_layouts()` 对用户文件缺段统一补「对局式神」「机制」；`_normalize_size_fields()` 遍历和写回都跳过这两个独立段。`put_layout()` 对「对局式神」只要求 `elements` 为 dict，不要求 `text_regions`。

- [ ] **Step 4: 实现只读预览接口**

项目预览用 `_with_artwork_fallback(card, library_dir / project / "images")`；无项目的布局预览强制包内 `sample_art.png`，忽略所有外部路径与 `_` 键。显式布局只接受对象并传给 `render_entity`，缺省用 `get_type_layout(load_layouts(assets_dir), "对局式神")`。

```python
img = render_entity(card, state, assets_dir, layout=entity_layout, info=info)
buf = BytesIO()
img.save(buf, "PNG")
ox, oy = info["crop_origin"]
return Response(buf.getvalue(), media_type="image/png",
                headers={"X-Crop-Offset": f"{ox},{oy}"})
```

所有校验/渲染错误按现有 API 口径转为 422；项目不存在仍走现有 404，不吞异常。

- [ ] **Step 5: 运行布局和 Web 测试**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_layout.py tests/test_web.py tests/test_web_projects.py -q`
Expected: PASS。

- [ ] **Step 6: 提交并推送**

```bash
git add assets/layout.json bwpdiy/render/default_layout.json bwpdiy/render/layout.py bwpdiy/web/app.py tests/test_layout.py tests/test_web.py tests/test_web_projects.py
git commit -m "feat(接口): 增加对局式神独立布局与临时预览接口"
git push
```

### Task 3: 卡牌库临时预览与导出

**Files:**
- Modify: `bwpdiy/web/static/editor.html`
- Modify: `tests/test_web.py`

**Interfaces:**
- Consumes: `POST /api/entity-preview`。
- Produces: 前端 `entityEligible(card)`、`makeEntityState(card)`、`setEntityField(key, value)`、`enterEntityMode()`、`exitEntityMode()`、`entityPreview()`、`exportEntity()`。

- [ ] **Step 1: 写前端纯函数失败测试**

沿用 `tests/test_web.py` 的 `_extract_js()`/`_run_node()`：

```javascript
assert(entityEligible({type: '式神'}));
assert(entityEligible({type: '形态'}));
assert(entityEligible({type: '法术', evolve: true}));
assert(!entityEligible({type: '战斗'}));
const source = {type: '法术', evolve: true, 'power+': 3, level: 2};
const state = makeEntityState(source);
assert(state.level === 2 && state.power === 0 && state.art_scale === 1);
setEntityField('power', 4);
assert(state.power === 4 && cDirty === false);
```

- [ ] **Step 2: 运行 Node 测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_web.py -q`
Expected: FAIL，实体函数未定义。

- [ ] **Step 3: 实现独立临时模式**

`buildForm()` 在 `entityMode` 时分派 `buildEntityForm()`；普通表单只为合格卡显示「对局式神」。初始化严格按设计：`power/health` 仅继承非负整数，`combat_power/shield=0`、`art_scale=1`，觉醒增量不转身材。

```javascript
function setEntityField(key, value) {
  entityState[key] = value;
  scheduleEntityPreview();
}

function entityEligible(card) {
  return !!card && (card.type === '式神' || card.type === '形态' || card.evolve === true);
}
```

实体表单只含等级、六色勾玉、对局缩放、力量、生命、战力/乏力、护甲/破甲、返回与导出。预览请求带 `{project: curProject, card: formData, state: entityState}`，复用 `cPreviewSeq/cHandlePreviewResponse`；`artMouseChannel()` 在实体模式返回 `null`，头像预览隐藏。`selectCard()`、`clearCard()`、`tryShowTab()` 先退出实体模式；不清来源 `cDirty`，不调用 `afterEdit`。导出直接下载同接口 Blob，文件名 `<安全卡名>_对局.png`。

- [ ] **Step 4: 运行 Web/JS 检查**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_web.py -q`
Run: `sed -n '/<script>/,/<\/script>/p' bwpdiy/web/static/editor.html | sed '1d;$d' > /tmp/editor.js && node --check /tmp/editor.js`
Expected: pytest PASS，Node 无输出且退出 0。

- [ ] **Step 5: 提交并推送**

```bash
git add bwpdiy/web/static/editor.html tests/test_web.py
git commit -m "feat(编辑器): 增加对局式神临时预览与导出"
git push
```

### Task 4: 全局布局编辑、文档与端到端验收

**Files:**
- Modify: `bwpdiy/web/static/editor.html`
- Modify: `bwpdiy/changelog.py`
- Modify: `docs/terminology.md`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `tests/test_web.py`

**Interfaces:**
- Consumes: Task 2 的独立布局段和无项目实体预览；Task 3 的卡牌库模式。
- Produces: 全局布局「对局式神」页；`entityLayoutMode` 与 `mechLayoutMode/cardLayoutMode` 互斥。

- [ ] **Step 1: 写布局模式隔离测试**

Node 测试断言：选择实体布局后 `typeLayout() === layouts['对局式神']`；`syncElemField()` 不改其他六类型；`selectType()`/`selectMechLayout()` 退出实体模式；还原全部包含「对局式神」；实体等级属性不显示觉醒星参数。

- [ ] **Step 2: 运行测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_web.py -q`
Expected: FAIL，尚无 `entityLayoutMode` 和实体布局入口。

- [ ] **Step 3: 接入现有布局画布**

`buildTypes()` 像「机制」一样单独追加「对局式神」，绝不加入 `TYPES`。新增 `selectEntityLayout()` 与 `refreshEntityLayoutPreview()`；布局样卡固定包内图，状态使用 `level=2, power=2, health=5, combat_power=1, shield=-1` 以显示全部组件。`refreshPreview()` 优先分派实体；`draw()/pick()/buildProps()` 复用 stat/level 元素，实体等级隐藏 `star_size/star_offset`，无文本区时保持空表。

`syncElemField()`、`syncRegionField()`、`propagateFromCurrentType()` 在实体模式禁止跨类型传播；`restoreLayout(true)` 覆盖 `[...TYPES, '对局式神', '机制']`。布局画布以 CSS 放大 64px 小卡但鼠标坐标按实际比例反算，导出 PNG 不放大。

- [ ] **Step 4: 更新文档和更新说明**

changelog 1.6.3 首条加入：

```python
"<b>本次更新更改了全局布局配置，用户可能需要重新手动调整本地配置。</b>",
"新增式神/形态/觉醒卡的「对局式神」临时预览：64px 小卡、六色勾玉、力量/生命及战力/乏力/护甲/破甲，可独立缩放卡图并导出 PNG",
```

术语表登记 `entity/render_entity/art_scale`、64×96 框体、四个数值口径、独立布局段和临时状态边界；AGENTS 更新渲染入口与布局段；README 只加简短功能项，不记录冗长历史。

- [ ] **Step 5: 全量自动验证**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`
Run: `sed -n '/<script>/,/<\/script>/p' bwpdiy/web/static/editor.html | sed '1d;$d' > /tmp/editor.js && node --check /tmp/editor.js`
Expected: 全量 PASS，Node 退出 0。

- [ ] **Step 6: 真实浏览器与视觉验收**

启动开发服务，使用 `uv run --with playwright python` 和本机 Edge：创建隔离项目与一张式神卡，进入「对局式神」，依次输入 `combat_power=-2`、`shield=3`、修改 `art_scale`，验证实时图变化；返回后来源卡不新增脏标记；再进入并下载 `<卡名>_对局.png`。将下载图复制到 `.smoke_tmp/entity.png` 并用 ReadMediaFile 检查 64px 清晰度、框体、勾玉和四角组件。另进入全局布局页拖动一个元素，确认只修改实体段。临时项目、截图和日志用完删除。

- [ ] **Step 7: 精简复查、提交并推送**

检查本轮 diff，删除只为测试预留的重复分支和无用 helper，不削弱路径/输入校验；确认文档不再描述旧方案。然后：

```bash
git add bwpdiy/web/static/editor.html bwpdiy/changelog.py docs/terminology.md AGENTS.md README.md tests/test_web.py
git commit -m "feat(布局): 完成对局式神布局编辑与使用说明"
git push
```
