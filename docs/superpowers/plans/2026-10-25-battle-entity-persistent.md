# 对局式神常驻预览与实时拖拽 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 1.7.0 中提供 96×144 常驻对局式神预览、按真实牌框透明窗修正卡图偏移、完整内窗布局，以及松开鼠标前平滑且精确的拖拽渲染。

**Architecture:** 实体渲染继续独立于普通卡类型；布局增加版本化迁移。普通卡静态绘制命令/层序列和缩放中间图使用有界缓存，前端三预览通道分离并用 `requestAnimationFrame` 调度鼠标预览，不在浏览器复制合成算法。

**Tech Stack:** Python 3.13、Pillow、FastAPI、vanilla JavaScript、pytest、Node `--check`、Edge + Playwright。

## Global Constraints

- 唯一设计口径：`docs/superpowers/specs/2026-10-25-battle-entity-persistent-design.md`；所有未发布内容版本统一为 1.7.0，本计划不打包发布。
- 实体框体 96×144，默认内窗 84×132、中心 `[48,72]`；最终 PNG 仍紧致裁剪。
- y 修正 = 来源偏移映射 + 可选 `(256-frame_cy)×entity_w/512` + 布局 `offset_y`；x 不做框窗修正。
- `power/health` 非负且 0 显示；`combat_power/shield` 正负切图标、0 隐藏；默认数字偏移分别 6px/5px。
- render 不 import store/web；路径与 `ARTWORK_MAX_PIXELS=64,000,000` 安全约束不得削弱，缓存必须有界且结果逐像素一致。
- 实体状态不置脏；主卡/头像/实体请求通道独立；出厂布局变化的 changelog 首条保留加粗提示。
- 中文 conventional commit，每次 commit 后 push；主上下文最终亲跑全量测试与真实浏览器。

---

### Task 1: 96×144 实体渲染、透明窗修正与布局迁移

**Files:**
- Modify: `bwpdiy/render/entity.py`
- Modify: `bwpdiy/render/layout.py`
- Modify: `assets/layout.json`
- Modify: `bwpdiy/render/default_layout.json`
- Modify: `bwpdiy/web/app.py`
- Modify: `tests/test_entity_render.py`
- Modify: `tests/test_layout.py`
- Modify: `tests/test_web.py`
- Modify: `tests/test_web_projects.py`

**Interfaces:**
- Keeps: `render_entity(card, state, assets_dir, layout=None, crop=True, info=None)`。
- Produces: `frame_art_window_center(frame: Image.Image) -> tuple[float,float]`，供实体按最大封闭透明窗求中心。
- Layout: `version=2`；`art_window={center:[48,72],width:84,height:132,frame_center:True,offset_y:0}`；`elements` 沿用现有五项。

- [ ] **Step 1: 先写失败测试**

```python
def test_entity_native_size_96(assets_dir, sample_art):
    card = {"type":"式神","name":"样例","_base_dir":str(sample_art.parent),
            "artwork":{"images":[{"path":sample_art.name}]}}
    assert render_entity(card, {}, assets_dir, crop=False).size == (96, 144)


def test_entity_frame_window_correction(assets_dir, sample_art, monkeypatch):
    monkeypatch.setattr("bwpdiy.render.entity.frame_art_window_center", lambda frame: (255, 169.5))
    captured = {}
    def capture(img, target, offset_x, offset_y, scale, cover_base):
        captured.update(target=target, x=offset_x, y=offset_y)
        return fit_artwork(img, target, offset_x, offset_y, scale, cover_base)
    monkeypatch.setattr("bwpdiy.render.entity.fit_artwork", capture)
    card = {"type":"式神","name":"样例","_base_dir":str(sample_art.parent),
            "artwork":{"images":[{"path":sample_art.name,"offset_y":8}]}}
    layout = deepcopy(_DEFAULT_LAYOUT)
    layout["art_window"]["offset_y"] = 2
    render_entity(card, {}, assets_dir, layout=layout)
    assert captured["target"] == (84, 132)
    assert captured["y"] == 8 * 84 / 512 + (256 - 169.5) * 84 / 512 + 2
```

另覆盖 `frame_center=False`、自定义内窗、全部16框的最大连通窗（`form_red` 中心应约168.5而非联合bbox的247）、非法内窗面积、旧布局只迁移一次、version 2 不缩放、旧默认数字10→6与9→5、自定义值仅×1.5。

- [ ] **Step 2: 确认测试因新功能缺失而失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_entity_render.py tests/test_layout.py -q`
Expected: FAIL，仍为64×96且无 `art_window/version`。

- [ ] **Step 3: 实现框体、透明窗与迁移**

`frame_art_window_center` 使用 alpha 128、边缘 flood fill 和剩余透明连通区域面积最大者；无封闭窗时抛 `ValueError("牌框缺少封闭卡图窗")`。按 `TYPE_FRAME_CODE[card["type"]]` 与实际框品加载并归一化牌框，缓存16种静态分析结果。

`render_entity` 从 `art_window.center/width/height` 计算内窗左上角，并调用：

```python
ratio = art_window["width"] / 512
offset_y = ref["offset_y"] * ratio + art_window.get("offset_y", 0)
if art_window.get("frame_center", True):
    offset_y += (256 - frame_cy) * ratio
art = fit_artwork(rotated, (width, height), ref["offset_x"] * ratio,
                  offset_y, state["art_scale"], cover_base=original)
```

内窗为有限正数且面积不超过64M。`layout.py` 在加载时先补独立段，再迁移无版本实体段；`version=2` 只做默认深补全，不重复缩放。`_DEFAULT_LAYOUT` 与两份 JSON 同步为新尺寸和新数字锚点。`put_layout` 接受实体 `version/art_window`，校验其形状和数值，普通类型规则不变。

- [ ] **Step 4: 运行受影响测试**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_entity_render.py tests/test_layout.py tests/test_web.py tests/test_web_projects.py -q`
Expected: PASS；既有数值/路径/API安全用例不回归。

- [ ] **Step 5: 提交并推送**

```bash
git add bwpdiy/render/entity.py bwpdiy/render/layout.py assets/layout.json bwpdiy/render/default_layout.json bwpdiy/web/app.py tests/test_entity_render.py tests/test_layout.py tests/test_web.py tests/test_web_projects.py
git commit -m "feat(对局式神): 调整96像素布局并按真实牌框透明窗修正偏移"
git push
```

### Task 2: 静态绘制命令/层序列与缩放卡图有界缓存

**Files:**
- Modify: `bwpdiy/render/artwork.py`
- Modify: `bwpdiy/render/pipeline.py`
- Modify: `tests/test_artwork.py`
- Modify: `tests/test_pipeline.py`

**Interfaces:**
- Produces: `fit_artwork_cached(img, target_size, offset_x=0, offset_y=0, scale=1.0, cover_base=None) -> Image.Image`，输入图像按只读处理。
- Produces: 普通卡内部静态绘制命令/层序列缓存，按原顺序重放；公开 `render_card` 签名与输出不变。

- [ ] **Step 1: 写缓存等价和复用失败测试**

```python
def test_fit_artwork_cached_reuses_resize(sample_art, monkeypatch):
    source = Image.open(sample_art).convert("RGBA")
    original = Image.Image.resize
    calls = []
    def counted(self, size, resample=None, *args, **kwargs):
        calls.append(size)
        return original(self, size, resample, *args, **kwargs)
    monkeypatch.setattr(Image.Image, "resize", counted)
    a = fit_artwork_cached(source, (512,512), 0, 0, 1)
    b = fit_artwork_cached(source, (512,512), 20, 0, 1)
    assert list(a.getdata()) == list(fit_artwork(source,(512,512),0,0,1).getdata())
    assert list(b.getdata()) == list(fit_artwork(source,(512,512),20,0,1).getdata())
    assert len(calls) == 1
```

普通卡测试用 spy 统计 `_render_digits` 调用：同一张卡只改 `offset_x/offset_y` 时第二次不重复文本/静态层绘制，输出与无缓存逐像素一致；改变描述、数值、框品或布局必须生成新静态层；含 `_duo` 或其他不可序列化内部数据时安全绕过。缓存条目和总缩放像素均有上限，线程锁不得覆盖慢速 PIL 操作。

- [ ] **Step 2: 确认测试失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_artwork.py tests/test_pipeline.py -q`
Expected: FAIL，cached入口不存在且静态层仍重复绘制。

- [ ] **Step 3: 实现缓存且保持合成次序**

`fit_artwork_cached` 使用源对象身份、尺寸、目标尺寸、scale、cover_base 为键，缓存值同时持有源图防 id 复用；只缓存 resize 结果，offset 每次重新 crop。使用 OrderedDict + RLock，缓存总像素≤64M，慢速 resize 在锁外完成，直接 `fit_artwork` 的可变输入语义不变。

将 `render_card` 中牌框之后的静态绘制记录为命令/层序列，不生成单一静态覆盖层。缓存键为资源路径、实际合并布局、剥离 `artwork/layout` 后的可序列化卡牌数据；`_duo` 或其他不可序列化内部数据无法安全键控时跳过。每帧仍重新计算卡图轮廓并叠加牌框，再将静态绘制命令按原顺序重放到当前画布，保持旧管线逐像素一致，最终描述/数值层级与裁剪不变。命令序列最多 8 条，重放前不修改缓存内容。

- [ ] **Step 4: 运行缓存和普通卡回归**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_artwork.py tests/test_pipeline.py tests/test_badges.py tests/test_keyword_highlight.py tests/test_entity_render.py -q`
Expected: PASS，缓存/无缓存像素一致。

- [ ] **Step 5: 提交并推送**

```bash
git add bwpdiy/render/artwork.py bwpdiy/render/pipeline.py tests/test_artwork.py tests/test_pipeline.py
git commit -m "perf(渲染): 缓存静态卡面层与缩放卡图中间图"
git push
```

### Task 3: 常驻子预览、独立通道与内窗布局编辑

**Files:**
- Modify: `bwpdiy/web/static/editor.html`
- Modify: `tests/test_web.py`

**Interfaces:**
- Consumes: 现有 `/api/entity-preview` 和 Task 1 的 `art_window`。
- Produces: `#c-subpreviews > #c-portrait + #c-entity`；独立 `cEntityTimer/cEntitySeq/cEntityUrl`；无 `entityMode`。
- Produces: 布局 `art_window` 的选择、拖拽与 `center/width/height/frame_center/offset_y` 控件。

- [ ] **Step 1: 重写前端失败测试**

Node 测试断言：式神DOM顺序为 portrait→entity，形态只有entity，普通战斗隐藏子预览；`buildForm()` 追加实体控件且不清空普通字段；实体字段不置脏；切卡重新初始化、清卡取消请求并释放URL；主卡与实体使用不同seq/timer/url，慢响应交错不互改；删除进入/返回/entityMode分支。

布局测试断言 `art_window` 可 pick/drag，编辑 `center` 只改实体段，`frame_center` 为布尔开关，`offset_y` 实时刷新；96×144原生图CSS放大后鼠标仍按比例反算。

- [ ] **Step 2: 确认测试失败并检查语法**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_web.py -q`
Expected: FAIL，旧entityMode与DOM不满足新断言。

- [ ] **Step 3: 实现常驻预览和独立响应处理**

普通表单直接调用 `appendEntityForm(div)`；`selectCard` 初始化state，`clearCard` 清理三通道。`cPreviewProject/cPreviewForm` 同时调度实体，实体响应只写 `#c-entity`。主图/头像逻辑不再含entityMode守卫，强制刷新覆盖全部可见通道。中栏使用纵向滚动，子预览flex居中并留间距。

布局用统一 `layoutRegions()` 在实体模式返回 `{"art_window": layout.art_window}`，使绿色框/pick/drag复用；`buildProps` 对该区域使用专用五项控件，不提供desc文本属性。其他类型仍读 `text_regions`，不新增普通文本区。

- [ ] **Step 4: 运行Web测试与JS检查**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_web.py -q`
Run: `sed -n '/<script>/,/<\/script>/p' bwpdiy/web/static/editor.html | sed '1d;$d' > /tmp/editor.js && node --check /tmp/editor.js`
Expected: PASS，Node退出0。

- [ ] **Step 5: 提交并推送**

```bash
git add bwpdiy/web/static/editor.html tests/test_web.py
git commit -m "feat(编辑器): 常驻对局式神预览并开放卡图内窗布局"
git push
```

### Task 4: 动画帧拖拽、1.7.0 文档与端到端验收

**Files:**
- Modify: `bwpdiy/web/static/editor.html`
- Modify: `bwpdiy/__init__.py`
- Modify: `bwpdiy/changelog.py`
- Modify: `docs/terminology.md`
- Modify: `docs/superpowers/specs/2026-10-25-battle-entity-design.md`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `tests/test_web.py`
- Modify: `tests/test_main.py`

**Interfaces:**
- Consumes: Task 2 的精确缓存和 Task 3 的三独立预览通道。
- Produces: 每通道 `scheduleMousePreview(channel)` / `flushMousePreview(channel)`，channel ∈ `art/entity/portrait`。

- [ ] **Step 1: 写动画帧与版本失败测试**

用可控 `requestAnimationFrame` 桩：连续20次 `afterMouseEdit('art')` 只排队一帧、执行时取最新偏移；art/entity/portrait 可各自排队且互不取消；`mouseup` 取消待执行帧并立即调用最终预览；普通输入仍保持原防抖。断言 `__version__ == "1.7.0"` 且 changelog 只有1.7.0而没有未发布的1.6.3段。

- [ ] **Step 2: 确认测试失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_web.py tests/test_main.py -q`
Expected: FAIL，仍为60ms计时器和1.6.3。

- [ ] **Step 3: 实现逐通道动画帧调度**

```javascript
const mousePreviewFrames = {art: 0, entity: 0, portrait: 0};
function scheduleMousePreview(channel) {
  if (mousePreviewFrames[channel]) return;
  mousePreviewFrames[channel] = requestAnimationFrame(() => {
    mousePreviewFrames[channel] = 0;
    flushMousePreview(channel);
  });
}
```

`afterMouseEdit` 保留即时数值/脏标记/撤回快照，art同时调度主卡和常驻实体，portrait只调度头像；`flushMousePreview` 先取消该通道待执行帧，再调用真实最终预览。`mouseup` 对实际拖拽通道强制flush，旧响应仍由各自seq丢弃。

- [ ] **Step 4: 更新版本和文档**

`__version__` 改为1.7.0，changelog 将原1.6.3全部条目移入1.7.0并追加常驻96×144、透明窗修正、内窗布局和实时拖拽；首条保留加粗布局提示。术语/README/AGENTS更新尺寸、常驻交互、缓存上限和版本；前版设计标明哪些尺寸与切换交互已被新设计取代。使用说明补一句拖拽中即可实时查看。

- [ ] **Step 5: 主上下文全量验证**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`
Run: `sed -n '/<script>/,/<\/script>/p' bwpdiy/web/static/editor.html | sed '1d;$d' > /tmp/editor.js && node --check /tmp/editor.js`
Expected: 全量PASS，Node退出0。

- [ ] **Step 6: 主上下文真实浏览器验收**

启动1.7.0服务，用隔离项目分别检查：式神“头像左/实体右”、形态仅实体、觉醒资格；96×144原生导出；不同框品下大卡卡图窗居中与实体修正一致；力量/生命数字在图标内；art_window拖拽/开关/额外y；连续mousemove未松开即收到多次真实预览且最终图与表单偏移一致；三通道慢响应不串图。检查实际PNG后删除临时项目、脚本和日志。

- [ ] **Step 7: 精简复查、提交并推送**

删除本轮不再使用的entityMode代码、重复响应helper和无效测试，不删除路径/输入/时序安全校验；复查缓存键与文档一致性。

```bash
git add bwpdiy docs tests README.md AGENTS.md
git commit -m "feat(对局式神): 完成1.7.0常驻预览与平滑实时拖拽"
git push
```
