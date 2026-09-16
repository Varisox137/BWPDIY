# M1.5 布局配置系统 + Web 配置工具 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把硬编码的 layout.py 常量升级为「按卡牌类型的可编辑布局配置（assets/layout.json）+ 多边形文本区 + 元素化渲染」，并交付 Web 布局配置工具（bwpdiy/web 首个页面，M3 编辑器的骨架），用户可在浏览器中拖拽调整元素锚点与多边形顶点并实时预览。

**Architecture:** 布局数据与渲染逻辑分离：renderer 从 layout.json（缺省回退包内 default_layout.json）读取「元素表 + 命名文本区」，pipeline 按卡牌类型遍历渲染。Web 工具 = FastAPI 后端（布局读写 + 样卡预览渲染）+ 单页 vanilla JS 前端（canvas 拖拽）。

**Tech Stack:** Python 3.12+ / Pillow（render 层唯一第三方依赖；布局解析用 stdlib json）/ FastAPI + uvicorn（仅 web 层）/ vanilla JS 无构建 / pytest + httpx（TestClient 依赖，随 fastapi 已有）。

## Global Constraints

- render 层只依赖 **Pillow + stdlib**（布局用 `json`，不得引入 yaml/fastapi）；不得 import bwpdiy.store / bwpdiy.web。
- 布局配置：`assets/layout.json`（用户定稿，不入库——已确认？**否：入库**，作为工具的出厂布局；见 Task 1 说明）——实际决定：**`assets/layout.json` 入 git**（它是渲染出厂配置，非用户创作数据）。包内 `bwpdiy/render/default_layout.json` 作为缺省回退（BWPro 裸调用无 assets/layout.json 时也能渲染），两者初始内容一致。
- 布局 schema（按 6 卡牌类型各一套）：
  ```json
  {
    "<类型>": {
      "elements": { "<元素名>": <元素定义>, ... },
      "text_regions": { "<区域名>": <区域定义>, ... }
    }
  }
  ```
  元素定义按 kind：
  - `{"kind":"level_badge","pos":[x,y],"base_size":72,"star_size":60,"num_size":40}`（card 有 level 才渲染）
  - `{"kind":"rarity_flank","pos":[cx,y],"gap":16,"size":24}`（card 有 rarity 才渲染；**两个稀有度标对称布置于卡名两侧**：x = cx ± (卡名渲染宽度/2 + gap + size/2)，卡名较长时自然外移；pos 的 y 与卡名行中心一致）
  - `{"kind":"faction","pos":[x,y],"size":44}`（card 有 faction 且派系有对应资源色才渲染）
  - `{"kind":"stat","field":"power","icon":"ll","pos":[x,y],"icon_size":32,"num_offset":[dx,dy],"font_size":30,"signed":false,"icon_neg":"pj"}`（card 有 field 字段才渲染；signed=true 显示正负号；num_offset 为数字中心相对图标中心的偏移；**icon_neg 可选**：值 < 0 时换用该图标——战斗牌护甲为负即显示破甲贴图）
  区域定义：`{"polygon":[[x,y],...≥3点],"font_range":[max,min],"wrap":true|false,"font":"name"|"desc"}`。
- 正负号规则：战斗牌与法术觉醒牌的数值 signed=true，其余类型 signed=false。
- 文本区渲染映射（pipeline 固定）：`name`←card["name"]；`desc`←card.get("description")；`footer`←card.get("footer") 或 `f"{card.get('shikigami', card['name'])}-{card['type']}"`，card 有 `special_type` 时再追加 `f"/{special_type}"`（footer 区域存在才渲染）。卡名/描述/脚注均居中，描述逐行居中。
- **文本避让（obstacles）**：wrap 文本区排版时，激活的 stat 元素（field 存在于 card）作为障碍矩形参与逐行求宽——与该行 y 带相交的障碍物从所在侧收窄可用区间（末尾几行自然减少字数，参照官方卡「往昔之日」）。障碍矩形 = `[pos.x-icon_size/2, pos.y-icon_size/2, pos.x+icon_size/2+abs(num_offset.x)+font_size*1.5, pos.y+icon_size/2]`。
- 多边形排版：字号从 font_range[0] 递减到 [1]；每行中线 y 与多边形求交线区间得可用宽度，贪心填词、行内在交线区间居中；排不下换更小字号；wrap=false 单行收缩字号（宽度=各行 y 处交线最大宽度）。
- 默认布局初值（512 画布，据官方参考卡 307×546 换算，用户最终用 GUI 定稿）：见 Task 1 的 default_layout.json 完整内容。
- render_card 签名扩展为 `render_card(card, assets_dir, layout=None)`（第三参可选，布局覆盖，默认 None=按 assets/包内加载）——向后兼容，BWPro 调用不变。
- 测试命令（Windows Git Bash）：`PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`；迭代期只跑受影响文件。
- 中文 conventional commit；每次 commit 后 `git push`。
- 术语同步：新增「布局配置/元素/文本区/多边形排版/footer」条目进 docs/terminology.md（Task 1）；README 进度与 AGENTS.md 随 Task 6 更新。

## 文件结构

```
bwpdiy/render/
├── default_layout.json   # Task 1：包内缺省布局
├── layout.py             # Task 1：重写为布局加载器（删旧常量）
├── geometry.py           # Task 2：多边形扫描线求交（纯函数）
├── text.py               # Task 2：重写为多边形排版
├── badges.py             # Task 3：重写为 render_element（元素定义驱动）
├── pipeline.py           # Task 3：改造（按类型元素表/文本区渲染，footer）
assets/layout.json        # Task 1：出厂布局（入 git）
bwpdiy/web/
├── app.py                # Task 4：create_app + API
├── sample_cards.py       # Task 4：六类型预览样卡数据
└── static/layout.html    # Task 5：配置页（内联 JS）
bwpdiy/__main__.py        # Task 4：改为 uvicorn 启动 web app
tests/
├── test_layout.py        # Task 1
├── test_geometry.py      # Task 2
├── test_text.py          # Task 2：重写
├── test_badges.py        # Task 3：重写
├── test_pipeline.py      # Task 3：随接口微调
└── test_web.py           # Task 4
```

---

### Task 1: 布局 schema + 默认配置 + 布局加载器（layout.py 重写）

**Files:**
- Create: `bwpdiy/render/default_layout.json`
- Create: `assets/layout.json`（内容与 default 一致）
- Modify: `bwpdiy/render/layout.py`（整体重写，删除旧常量）
- Modify: `pyproject.toml`（hatch 包数据包含 *.json）
- Test: `tests/test_layout.py`
- Modify: `docs/terminology.md`（新增布局条目）

**Interfaces:**
- Consumes: `AssetLibrary`（Task 1 of M1）
- Produces:
  - `layout.load_layouts(assets_dir: Path) -> dict`：优先 `<assets_dir>/layout.json`，缺失回退包内 `default_layout.json`；返回完整 6 类型 dict
  - `layout.get_type_layout(layouts: dict, card_type: str) -> dict`：返回 `{"elements": {...}, "text_regions": {...}}`；未知类型抛 `ValueError(f"布局缺失: {card_type}")`
  - 布局 dict 结构见 Global Constraints 的 schema

- [ ] **Step 1: 写失败测试**

`tests/test_layout.py`：

```python
import json
from pathlib import Path

import pytest

from bwpdiy.render import layout

TYPES = ["式神", "战斗", "法术", "形态", "幻境", "协战"]


def test_default_layout_covers_all_types():
    layouts = layout.load_layouts(Path("不存在的目录"))
    for t in TYPES:
        tl = layout.get_type_layout(layouts, t)
        assert "elements" in tl and "text_regions" in tl
        assert tl["text_regions"]["name"]["wrap"] is False
        assert tl["text_regions"]["desc"]["wrap"] is True
        for region in tl["text_regions"].values():
            assert len(region["polygon"]) >= 3
            assert region["font"] in ("name", "desc")


def test_assets_layout_takes_precedence(tmp_path):
    custom = {t: {"elements": {}, "text_regions": {}} for t in TYPES}
    custom["战斗"]["elements"]["rarity"] = {"kind": "rarity_flank", "pos": [1, 2], "gap": 16, "size": 24}
    (tmp_path / "layout.json").write_text(json.dumps(custom, ensure_ascii=False), encoding="utf-8")
    layouts = layout.load_layouts(tmp_path)
    assert layouts["战斗"]["elements"]["rarity"]["pos"] == [1, 2]


def test_unknown_type_raises():
    layouts = layout.load_layouts(Path("不存在的目录"))
    with pytest.raises(ValueError, match="布局缺失"):
        layout.get_type_layout(layouts, "不存在")


def test_expected_elements_per_type():
    layouts = layout.load_layouts(Path("不存在的目录"))
    assert set(layouts["式神"]["elements"]) == {"faction", "power", "health"}
    assert set(layouts["战斗"]["elements"]) == {"level", "rarity", "power", "shield"}
    assert set(layouts["法术"]["elements"]) == {"level", "rarity", "power", "health"}
    assert set(layouts["形态"]["elements"]) == {"level", "rarity", "power", "health"}
    assert set(layouts["幻境"]["elements"]) == {"level", "rarity", "durability"}
    assert set(layouts["协战"]["elements"]) == {"level", "rarity"}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_layout.py -q`
Expected: FAIL（layout 模块无 load_layouts）

- [ ] **Step 3: 实现**

`bwpdiy/render/default_layout.json`（初值据官方参考卡换算；`assets/layout.json` 复制同内容）：

```json
{
  "式神": {
    "elements": {
      "faction": {"kind": "faction", "pos": [256, 318], "size": 44},
      "power": {"kind": "stat", "field": "power", "icon": "ll", "pos": [160, 485], "icon_size": 32, "num_offset": [22, 0], "font_size": 30, "signed": false},
      "health": {"kind": "stat", "field": "health", "icon": "sm", "pos": [360, 485], "icon_size": 32, "num_offset": [22, 0], "font_size": 30, "signed": false}
    },
    "text_regions": {
      "name": {"polygon": [[140, 336], [372, 336], [372, 380], [140, 380]], "font_range": [36, 16], "wrap": false, "font": "name"},
      "desc": {"polygon": [[130, 386], [382, 386], [382, 466], [130, 466]], "font_range": [22, 12], "wrap": true, "font": "desc"},
      "footer": {"polygon": [[150, 472], [362, 472], [362, 496], [150, 496]], "font_range": [14, 10], "wrap": false, "font": "desc"}
    }
  },
  "战斗": {
    "elements": {
      "level": {"kind": "level_badge", "pos": [120, 65], "base_size": 72, "star_size": 60, "num_size": 40},
      "rarity": {"kind": "rarity_flank", "pos": [256, 358], "gap": 16, "size": 24},
      "power": {"kind": "stat", "field": "power+", "icon": "ll", "pos": [160, 485], "icon_size": 32, "num_offset": [22, 0], "font_size": 30, "signed": true},
      "shield": {"kind": "stat", "field": "shield+", "icon": "hj", "icon_neg": "pj", "pos": [360, 485], "icon_size": 32, "num_offset": [22, 0], "font_size": 30, "signed": true}
    },
    "text_regions": {
      "name": {"polygon": [[140, 336], [372, 336], [372, 380], [140, 380]], "font_range": [36, 16], "wrap": false, "font": "name"},
      "desc": {"polygon": [[130, 386], [382, 386], [382, 466], [130, 466]], "font_range": [22, 12], "wrap": true, "font": "desc"},
      "footer": {"polygon": [[150, 472], [362, 472], [362, 496], [150, 496]], "font_range": [14, 10], "wrap": false, "font": "desc"}
    }
  },
  "法术": {
    "elements": {
      "level": {"kind": "level_badge", "pos": [120, 65], "base_size": 72, "star_size": 60, "num_size": 40},
      "rarity": {"kind": "rarity_flank", "pos": [256, 358], "gap": 16, "size": 24},
      "power": {"kind": "stat", "field": "power+", "icon": "ll", "pos": [160, 485], "icon_size": 32, "num_offset": [22, 0], "font_size": 30, "signed": true},
      "health": {"kind": "stat", "field": "health+", "icon": "sm", "pos": [360, 485], "icon_size": 32, "num_offset": [22, 0], "font_size": 30, "signed": true}
    },
    "text_regions": {
      "name": {"polygon": [[140, 336], [372, 336], [372, 380], [140, 380]], "font_range": [36, 16], "wrap": false, "font": "name"},
      "desc": {"polygon": [[130, 386], [382, 386], [382, 466], [130, 466]], "font_range": [22, 12], "wrap": true, "font": "desc"},
      "footer": {"polygon": [[150, 472], [362, 472], [362, 496], [150, 496]], "font_range": [14, 10], "wrap": false, "font": "desc"}
    }
  },
  "形态": {
    "elements": {
      "level": {"kind": "level_badge", "pos": [120, 65], "base_size": 72, "star_size": 60, "num_size": 40},
      "rarity": {"kind": "rarity_flank", "pos": [256, 358], "gap": 16, "size": 24},
      "power": {"kind": "stat", "field": "power", "icon": "ll", "pos": [160, 485], "icon_size": 32, "num_offset": [22, 0], "font_size": 30, "signed": false},
      "health": {"kind": "stat", "field": "health", "icon": "sm", "pos": [360, 485], "icon_size": 32, "num_offset": [22, 0], "font_size": 30, "signed": false}
    },
    "text_regions": {
      "name": {"polygon": [[140, 336], [372, 336], [372, 380], [140, 380]], "font_range": [36, 16], "wrap": false, "font": "name"},
      "desc": {"polygon": [[130, 386], [382, 386], [382, 466], [130, 466]], "font_range": [22, 12], "wrap": true, "font": "desc"},
      "footer": {"polygon": [[150, 472], [362, 472], [362, 496], [150, 496]], "font_range": [14, 10], "wrap": false, "font": "desc"}
    }
  },
  "幻境": {
    "elements": {
      "level": {"kind": "level_badge", "pos": [120, 65], "base_size": 72, "star_size": 60, "num_size": 40},
      "rarity": {"kind": "rarity_flank", "pos": [256, 358], "gap": 16, "size": 24},
      "durability": {"kind": "stat", "field": "durability", "icon": "nj", "pos": [360, 485], "icon_size": 32, "num_offset": [22, 0], "font_size": 30, "signed": false}
    },
    "text_regions": {
      "name": {"polygon": [[140, 336], [372, 336], [372, 380], [140, 380]], "font_range": [36, 16], "wrap": false, "font": "name"},
      "desc": {"polygon": [[130, 386], [382, 386], [382, 466], [130, 466]], "font_range": [22, 12], "wrap": true, "font": "desc"},
      "footer": {"polygon": [[150, 472], [362, 472], [362, 496], [150, 496]], "font_range": [14, 10], "wrap": false, "font": "desc"}
    }
  },
  "协战": {
    "elements": {
      "level": {"kind": "level_badge", "pos": [120, 65], "base_size": 72, "star_size": 60, "num_size": 40},
      "rarity": {"kind": "rarity_flank", "pos": [256, 358], "gap": 16, "size": 24}
    },
    "text_regions": {
      "name": {"polygon": [[140, 336], [372, 336], [372, 380], [140, 380]], "font_range": [36, 16], "wrap": false, "font": "name"},
      "desc": {"polygon": [[130, 386], [382, 386], [382, 466], [130, 466]], "font_range": [22, 12], "wrap": true, "font": "desc"},
      "footer": {"polygon": [[150, 472], [362, 472], [362, 496], [150, 496]], "font_range": [14, 10], "wrap": false, "font": "desc"}
    }
  }
}
```

`bwpdiy/render/layout.py`（整体替换，旧常量全部删除）：

```python
"""布局配置加载：assets/layout.json 优先，缺省回退包内 default_layout.json。

布局 schema 见 docs/terminology.md「布局配置」。
"""

import json
from pathlib import Path

_DEFAULT = Path(__file__).with_name("default_layout.json")


def load_layouts(assets_dir: Path) -> dict:
    """加载完整布局表（6 类型）。assets_dir/layout.json 优先，缺失回退包内默认。"""
    path = Path(assets_dir) / "layout.json"
    if not path.is_file():
        path = _DEFAULT
    return json.loads(path.read_text(encoding="utf-8"))


def get_type_layout(layouts: dict, card_type: str) -> dict:
    """取单类型布局 {"elements": ..., "text_regions": ...}。"""
    if card_type not in layouts:
        raise ValueError(f"布局缺失: {card_type}")
    return layouts[card_type]
```

`pyproject.toml` 的 `[tool.hatch.build.targets.wheel]` 下加一行确保 json 入包：

```toml
[tool.hatch.build.targets.wheel]
packages = ["bwpdiy"]
artifacts = ["bwpdiy/render/default_layout.json"]
```

`docs/terminology.md`「数据与组织」表追加：

```markdown
| 布局配置 | `assets/layout.json`（出厂值入 git）+ 包内 `bwpdiy/render/default_layout.json` 回退；按 6 卡牌类型各一套「元素表 + 命名文本区」 |
| 元素 | 布局中的可定位渲染单元，kind ∈ level_badge / rarity_flank（卡名两侧对称双标，随卡名宽度外移）/ faction / stat（图标+数字一组，num_offset 相对偏移，signed 控制正负号，icon_neg 负值换贴图） |
| 文本区 | 命名多边形区域（name/desc/footer），逐行扫描线求宽、行内居中、字号递减适配；footer = “式神名-类型[/子类型]”小字；激活的 stat 元素作为障碍矩形参与 desc 逐行收窄（文本避让） |
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_layout.py -q`
Expected: 4 passed

- [ ] **Step 5: 全量回归**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`
Expected: 旧测试因 layout 常量删除而失败（test_badges/test_text 引用旧常量）——**允许本步红**，Task 2/3 重写后转绿；确认只有 import 错误类失败。

- [ ] **Step 6: Commit**

```bash
git add bwpdiy/render/default_layout.json assets/layout.json bwpdiy/render/layout.py pyproject.toml tests/test_layout.py docs/terminology.md
git commit -m "feat(render): 布局配置 schema 与加载器——layout.json 元素表+命名文本区"
git push
```

---

### Task 2: 多边形文本排版（geometry.py + text.py 重写）

**Files:**
- Create: `bwpdiy/render/geometry.py`
- Modify: `bwpdiy/render/text.py`（整体重写）
- Test: `tests/test_geometry.py`、`tests/test_text.py`（整体重写）

**Interfaces:**
- Consumes: `AssetLibrary.font`（M1 Task 1）
- Produces:
  - `geometry.polygon_x_span(polygon: list[list[float]], y: float) -> tuple[float, float] | None`：水平扫描线 y 与多边形交点的 x 区间；无交返回 None
  - `geometry.polygon_y_range(polygon) -> tuple[float, float]`
  - `geometry.clamp_span_by_obstacles(span: tuple[float, float], y: float, half_h: float, obstacles: list[tuple[float, float, float, float]]) -> tuple[float, float] | None`：障碍矩形 (x0,y0,x1,y1) 与行 y 带 [y-half_h, y+half_h] 相交时，按障碍物中心相对 span 中心的方向收窄 span（左侧障碍抬左界、右侧障碍压右界，留 4px 间隙）；收窄后宽度 ≤ 0 返回 None
  - `text.fit_in_region(text: str, region: dict, lib: AssetLibrary, obstacles: list | None = None) -> tuple[FreeTypeFont, list[tuple[str, float, float]]] | None`：返回 (字体, [(行文本, 行中心x, 行中心y)])；排不下返回 None
  - `text.draw_region(canvas, lib, text: str, region: dict, obstacles: list | None = None, fill=TEXT_FILL) -> Image.Image`：fit_in_region 失败时按最小字号强排（截断超出部分不特殊处理）
  - `text.TEXT_FILL = (60, 45, 30, 255)`

- [ ] **Step 1: 写失败测试**

`tests/test_geometry.py`：

```python
from bwpdiy.render.geometry import polygon_x_span, polygon_y_range

RECT = [[100, 100], [300, 100], [300, 200], [100, 200]]
TRIANGLE = [[100, 200], [300, 200], [200, 100]]  # 顶点在上的三角


def test_rect_span():
    assert polygon_x_span(RECT, 150) == (100.0, 300.0)


def test_rect_outside():
    assert polygon_x_span(RECT, 50) is None
    assert polygon_x_span(RECT, 250) is None


def test_triangle_span_narrows_upward():
    low = polygon_x_span(TRIANGLE, 175)
    high = polygon_x_span(TRIANGLE, 125)
    assert low and high
    assert (low[1] - low[0]) > (high[1] - high[0])
    assert abs((low[0] + low[1]) / 2 - 200) < 1e-6  # 关于 x=200 对称


def test_y_range():
    assert polygon_y_range(TRIANGLE) == (100, 200)


def test_clamp_span_by_obstacles():
    from bwpdiy.render.geometry import clamp_span_by_obstacles
    span = (100.0, 300.0)
    # 左侧障碍（数值标在左下）：抬左界
    left_obs = [(110.0, 140.0, 150.0, 170.0)]
    assert clamp_span_by_obstacles(span, 150, 12, left_obs) == (154.0, 300.0)
    # 右侧障碍：压右界
    right_obs = [(250.0, 140.0, 290.0, 170.0)]
    assert clamp_span_by_obstacles(span, 150, 12, right_obs) == (100.0, 246.0)
    # y 带不相交：不受影响
    assert clamp_span_by_obstacles(span, 100, 12, left_obs) == span
    # 双侧挤压到无宽度：None
    both = [(110.0, 140.0, 190.0, 170.0), (210.0, 140.0, 290.0, 170.0)]
    assert clamp_span_by_obstacles((150.0, 200.0), 150, 12, both) is None
```

`tests/test_text.py`（整体替换旧文件）：

```python
from PIL import Image

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.text import TEXT_FILL, draw_region, fit_in_region


def canvas():
    return Image.new("RGBA", (512, 512), (0, 0, 0, 0))


def rect_region(x0, y0, x1, y1, **kw):
    region = {"polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
              "font_range": [36, 12], "wrap": True, "font": "desc"}
    region.update(kw)
    return region


def test_fit_rect_single_line(assets_dir):
    lib = AssetLibrary(assets_dir)
    font, lines = fit_in_region("短句", rect_region(100, 100, 400, 200), lib)
    assert len(lines) == 1
    text, cx, cy = lines[0]
    assert text == "短句" and abs(cx - 250) < 1e-6


def test_fit_wraps_and_shrinks(assets_dir):
    lib = AssetLibrary(assets_dir)
    long = "这是一段非常非常长的描述文本需要换行并且缩小字号才能排下" * 3
    font, lines = fit_in_region(long, rect_region(100, 100, 300, 300), lib)
    assert len(lines) > 1 and font.size < 36


def test_fit_nowrap_single_line(assets_dir):
    lib = AssetLibrary(assets_dir)
    region = rect_region(100, 100, 400, 160, wrap=False, font="name")
    font, lines = fit_in_region("卡牌名", region, lib)
    assert len(lines) == 1


def test_fit_triangle_centers_per_line(assets_dir):
    lib = AssetLibrary(assets_dir)
    region = {"polygon": [[100, 300], [400, 300], [250, 100]],
              "font_range": [24, 12], "wrap": True, "font": "desc"}
    font, lines = fit_in_region("三角区域排版测试文本内容", region, lib)
    assert len(lines) >= 1
    for _, cx, _ in lines:
        assert abs(cx - 250) < 1e-6  # 对称三角，每行中心都在 x=250


def test_draw_region_renders_pixels(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = draw_region(canvas(), lib, "渲染测试", rect_region(100, 100, 400, 200))
    assert sum(1 for p in img.getdata() if p[3] > 0) > 50


def test_obstacles_narrow_bottom_lines(assets_dir):
    # 底部左右有数值标障碍：长描述末尾几行可用宽度应变窄（行数增多或末行更短）
    lib = AssetLibrary(assets_dir)
    text = "这是一段用于验证障碍避让的长描述文本，需要排很多行才能放下。" * 2
    region = rect_region(100, 100, 400, 400)
    obstacles = [(100.0, 350.0, 160.0, 400.0), (340.0, 350.0, 400.0, 400.0)]
    font, lines = fit_in_region(text, region, lib, obstacles=obstacles)
    assert lines is not None
    bottom = [l for l in lines if l[2] > 350]
    top = [l for l in lines if l[2] < 300]
    assert bottom and top
    assert max(font.getlength(l[0]) for l in bottom) < max(font.getlength(l[0]) for l in top)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py tests/test_text.py -q`
Expected: FAIL（geometry 不存在；text 接口已变）

- [ ] **Step 3: 实现**

`bwpdiy/render/geometry.py`：

```python
"""多边形几何：水平扫描线求交（文本区排版用）。"""


def polygon_x_span(polygon: list[list[float]], y: float) -> tuple[float, float] | None:
    """水平线 y 与多边形交点的 x 区间；无交（或仅切于顶点）返回 None。

    采用标准扫描线规则：边 (y1<=y<y2) 计入，避免顶点重复计数。
    """
    xs: list[float] = []
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if y1 == y2:
            continue
        if min(y1, y2) <= y < max(y1, y2):
            xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    if len(xs) < 2:
        return None
    xs.sort()
    return xs[0], xs[-1]


def polygon_y_range(polygon: list[list[float]]) -> tuple[float, float]:
    ys = [p[1] for p in polygon]
    return min(ys), max(ys)


def clamp_span_by_obstacles(span: tuple[float, float], y: float, half_h: float,
                            obstacles: list[tuple[float, float, float, float]],
                            gap: float = 4.0) -> tuple[float, float] | None:
    """行 y 带 [y-half_h, y+half_h] 与障碍矩形相交时按侧收窄 span；无宽度返回 None。"""
    left, right = span
    center = (left + right) / 2
    for x0, y0, x1, y1 in obstacles:
        if y1 < y - half_h or y0 > y + half_h:
            continue
        if (x0 + x1) / 2 < center:
            left = max(left, x1 + gap)
        else:
            right = min(right, x0 - gap)
    if right - left <= 0:
        return None
    return left, right
```

`bwpdiy/render/text.py`（整体替换）：

```python
"""文本层：多边形文本区排版（扫描线求宽、行内居中、字号递减适配）。"""

from PIL import Image, ImageDraw, ImageFont

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.geometry import (clamp_span_by_obstacles, polygon_x_span,
                                    polygon_y_range)

TEXT_FILL = (60, 45, 30, 255)

_LINE_GAP = 6


def _line_height(font: ImageFont.FreeTypeFont) -> float:
    box = font.getbbox("国Ag")
    return box[3] - box[1] + _LINE_GAP


def _layout_at_size(text: str, font: ImageFont.FreeTypeFont,
                    polygon: list[list[float]], wrap: bool,
                    obstacles: list | None = None):
    """按给定字号在多边形内排版，成功返回 [(行, cx, cy)]，失败返回 None。"""
    obstacles = obstacles or []
    y_top, y_bottom = polygon_y_range(polygon)
    lh = _line_height(font)

    def span_at(y: float):
        span = polygon_x_span(polygon, y)
        if span is None:
            return None
        if obstacles:
            span = clamp_span_by_obstacles(span, y, lh / 2, obstacles)
        return span

    if not wrap:
        y = (y_top + y_bottom) / 2
        span = span_at(y)
        if span is None or font.getlength(text) > span[1] - span[0]:
            return None
        return [(text, (span[0] + span[1]) / 2, y)]
    lines: list[tuple[str, float, float]] = []
    current = ""
    y = y_top + lh / 2
    paragraphs = text.split("\n")
    for pi, paragraph in enumerate(paragraphs):
        for ch in paragraph:
            trial = current + ch
            span = span_at(y)
            width = (span[1] - span[0]) if span else 0.0
            if current and font.getlength(trial) > width:
                lines.append((current, (span[0] + span[1]) / 2, y))
                y += lh
                if y + lh / 2 > y_bottom:
                    return None
                current = ch
            else:
                current = trial
        if pi < len(paragraphs) - 1 or current:
            span = span_at(y)
            if span is None:
                return None
            lines.append((current, (span[0] + span[1]) / 2, y))
            current = ""
            if pi < len(paragraphs) - 1:
                y += lh
                if y + lh / 2 > y_bottom:
                    return None
    return lines or None


def fit_in_region(text: str, region: dict, lib: AssetLibrary,
                  obstacles: list | None = None):
    """字号从大到小适配，返回 (font, lines)；最小字号仍排不下时返回 None。"""
    max_size, min_size = region["font_range"]
    for size in range(max_size, min_size - 1, -1):
        font = lib.font(region["font"], size)
        lines = _layout_at_size(text, font, region["polygon"], region["wrap"], obstacles)
        if lines is not None:
            return font, lines
    return None


def draw_region(canvas: Image.Image, lib: AssetLibrary, text: str,
                region: dict, obstacles: list | None = None,
                fill=TEXT_FILL) -> Image.Image:
    fitted = fit_in_region(text, region, lib, obstacles)
    if fitted is None:
        font = lib.font(region["font"], region["font_range"][1])
        lines = _layout_at_size(text, font, region["polygon"], region["wrap"], obstacles)
        if lines is None:  # 单行 nowrap 超宽：居中强排
            y0, y1 = polygon_y_range(region["polygon"])
            cx = sum(p[0] for p in region["polygon"]) / len(region["polygon"])
            lines = [(text, cx, (y0 + y1) / 2)]
        fitted = (font, lines)
    font, lines = fitted
    out = canvas.copy()
    draw = ImageDraw.Draw(out)
    for line, cx, cy in lines:
        draw.text((cx, cy), line, font=font, anchor="mm", fill=fill)
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_geometry.py tests/test_text.py -q`
Expected: 5 + 6 passed

- [ ] **Step 5: Commit**

```bash
git add bwpdiy/render/geometry.py bwpdiy/render/text.py tests/test_geometry.py tests/test_text.py
git commit -m "feat(render): 多边形文本区排版——扫描线求宽/行内居中/字号递减"
git push
```

---

### Task 3: 元素渲染（badges.py 重写）+ pipeline 改造

**Files:**
- Modify: `bwpdiy/render/badges.py`（整体重写）
- Modify: `bwpdiy/render/pipeline.py`（元素表/文本区驱动）
- Test: `tests/test_badges.py`（整体重写）、`tests/test_pipeline.py`（微调）

**Interfaces:**
- Consumes: `AssetLibrary`、`common.paste_centered`、`layout.get_type_layout`、`text.draw_region`、`text.fit_in_region`
- Produces:
  - `badges.render_element(canvas, lib, name: str, elem: dict, card: dict, ctx: dict | None = None) -> Image.Image`：按 elem["kind"] 分派；渲染条件不满足（缺 level/rarity/faction/field）时原样返回 canvas。`ctx["name_width"]` 供 rarity_flank 计算外移量（pipeline 用 name 区适配后的字体测得）
  - `badges.stat_obstacle(elem: dict) -> tuple[float, float, float, float]`：stat 元素的障碍矩形（公式见 Global Constraints）
  - `render_card(card, assets_dir, layout: dict | None = None) -> Image.Image`（第三参为单类型布局覆盖 {"elements","text_regions"}）
  - 文本区映射：`name`←card["name"]、`desc`←card.get("description")（排版时传入激活 stat 元素的障碍矩形）、`footer`←card.get("footer") 或 `f"{card.get('shikigami', card['name'])}-{card['type']}"`，有 `special_type` 再追加 `/{special_type}`

- [ ] **Step 1: 写失败测试**

`tests/test_badges.py`（整体替换）：

```python
from PIL import Image

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.badges import render_element


def canvas():
    return Image.new("RGBA", (512, 512), (0, 0, 0, 0))


def opaque(img):
    return sum(1 for p in img.getdata() if p[3] > 0)


def test_level_badge(assets_dir):
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "level_badge", "pos": [120, 65], "base_size": 72, "star_size": 60, "num_size": 40}
    img = render_element(canvas(), lib, "level", elem, {"level": 2, "evolve": True})
    assert img.getpixel((120, 65))[3] > 0
    # 无 level 字段：跳过
    assert render_element(canvas(), lib, "level", elem, {}) == canvas() or \
        opaque(render_element(canvas(), lib, "level", elem, {})) == 0


def test_rarity_flank_symmetric(assets_dir):
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "rarity_flank", "pos": [256, 358], "gap": 16, "size": 24}
    # 卡名越宽，两标越外移：比较短名/长名 ctx 下右标位置的像素差异
    narrow = render_element(canvas(), lib, "rarity", elem, {"rarity": "SSR"}, {"name_width": 40})
    wide = render_element(canvas(), lib, "rarity", elem, {"rarity": "SSR"}, {"name_width": 160})
    assert opaque(narrow) > 0 and opaque(wide) > 0
    # 右标中心 x = 256 + name_width/2 + 16 + 12：宽名时右标右侧应有像素而窄名时没有
    assert wide.getpixel((256 + 80 + 16 + 24, 358))[3] > 0
    assert narrow.getpixel((256 + 80 + 16 + 24, 358))[3] == 0
    # 无 rarity：跳过
    assert opaque(render_element(canvas(), lib, "rarity", elem, {})) == 0


def test_faction(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = render_element(canvas(), lib, "faction",
                         {"kind": "faction", "pos": [256, 318], "size": 44}, {"faction": "红莲"})
    assert opaque(img) > 0
    # 无相：跳过
    assert opaque(render_element(canvas(), lib, "faction",
                                 {"kind": "faction", "pos": [256, 318], "size": 44},
                                 {"faction": "无相"})) == 0


def test_stat_signed_and_offset(assets_dir):
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "power+", "icon": "ll", "pos": [160, 485],
            "icon_size": 32, "num_offset": [22, 0], "font_size": 30, "signed": True}
    img = render_element(canvas(), lib, "power", elem, {"power+": 1})
    assert opaque(img) > 100  # 图标+数字两处像素
    # 缺字段跳过
    assert opaque(render_element(canvas(), lib, "power", elem, {})) == 0


def test_stat_icon_neg(assets_dir):
    from bwpdiy.render.badges import stat_obstacle
    lib = AssetLibrary(assets_dir)
    elem = {"kind": "stat", "field": "shield+", "icon": "hj", "icon_neg": "pj",
            "pos": [360, 485], "icon_size": 32, "num_offset": [22, 0],
            "font_size": 30, "signed": True}
    pos_img = render_element(canvas(), lib, "shield", elem, {"shield+": 1})
    neg_img = render_element(canvas(), lib, "shield", elem, {"shield+": -1})
    assert list(pos_img.getdata()) != list(neg_img.getdata())  # 负值换用破甲贴图
    # stat_obstacle 矩形公式
    x0, y0, x1, y1 = stat_obstacle(elem)
    assert x0 == 360 - 16 and y0 == 485 - 16
    assert x1 > 360 + 16 and y1 == 485 + 16
```

`tests/test_pipeline.py` 微调：`make_card` 不变；新增：

```python
def test_render_with_layout_override(assets_dir, sample_art):
    from bwpdiy.render.layout import load_layouts, get_type_layout
    layouts = load_layouts(assets_dir)
    tl = get_type_layout(layouts, "法术")
    tl["elements"]["rarity"]["pos"] = [200, 200]
    card = {"type": "法术", "name": "sample_art", "rarity": "R",
            "_base_dir": str(sample_art.parent)}
    img = render_card(card, assets_dir, layout=tl)
    assert img.mode == "RGBA"


def test_footer_rendered(assets_dir, sample_art):
    card = {"type": "战斗", "name": "sample_art", "shikigami": "测试式神",
            "level": 1, "rarity": "N", "_base_dir": str(sample_art.parent)}
    img = render_card(card, assets_dir)  # footer = "测试式神-战斗"，不炸即过
    assert img.mode == "RGBA"


def test_footer_with_special_type(assets_dir, sample_art):
    card = {"type": "法术", "name": "sample_art", "shikigami": "测试式神",
            "special_type": "惊雷", "level": 1, "rarity": "N",
            "_base_dir": str(sample_art.parent)}
    img = render_card(card, assets_dir)  # footer = "测试式神-法术/惊雷"，不炸即过
    assert img.mode == "RGBA"


def test_desc_avoids_stat_obstacles(assets_dir, sample_art):
    # 左右下有数值贴图的战斗牌 + 长描述：排版须避让（不炸且出图）
    card = {"type": "战斗", "name": "sample_art", "shikigami": "测试式神",
            "level": 1, "rarity": "N", "power+": 2, "shield+": -1,
            "description": "这是一段相当长的描述文本，用来验证末端行避开数值贴图的排版行为是否正常工作。" * 2,
            "_base_dir": str(sample_art.parent)}
    img = render_card(card, assets_dir)
    assert img.mode == "RGBA"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_badges.py tests/test_pipeline.py -q`
Expected: FAIL（badges 接口已变 / pipeline 未实现 layout 参数）

- [ ] **Step 3: 实现**

`bwpdiy/render/badges.py`（整体替换）：

```python
"""元素渲染：按布局元素定义渲染 等级标/稀有度双标/派系标/数值标。"""

from PIL import Image, ImageDraw

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.common import paste_centered

FACTION_COLOR = {
    "红莲": "red",
    "苍叶": "green",
    "青岚": "blue",
    "紫岩": "purple",
    # 无相：无派系标，跳过
}


def stat_obstacle(elem: dict) -> tuple[float, float, float, float]:
    """stat 元素的障碍矩形（文本避让用，公式见 Global Constraints）。"""
    x, y = elem["pos"]
    half = elem["icon_size"] / 2
    return (x - half, y - half,
            x + half + abs(elem["num_offset"][0]) + elem["font_size"] * 1.5,
            y + half)


def render_element(canvas: Image.Image, lib: AssetLibrary, name: str,
                   elem: dict, card: dict, ctx: dict | None = None) -> Image.Image:
    """渲染单个布局元素；渲染条件不满足时原样返回 canvas。"""
    kind = elem["kind"]
    if kind == "level_badge":
        if card.get("level") is None:
            return canvas
        out = paste_centered(canvas, lib.level_base(), elem["pos"],
                             (elem["base_size"], elem["base_size"]))
        if card.get("evolve", False):
            out = paste_centered(out, lib.level_star(), elem["pos"],
                                 (elem["star_size"], elem["star_size"]))
        return paste_centered(out, lib.level_num("brown", card["level"]),
                              elem["pos"], (elem["num_size"], elem["num_size"]))
    if kind == "rarity_flank":
        if not card.get("rarity"):
            return canvas
        cx, y = elem["pos"]
        name_width = (ctx or {}).get("name_width", 0)
        offset = name_width / 2 + elem["gap"] + elem["size"] / 2
        mark = lib.rarity(card["rarity"])
        out = paste_centered(canvas, mark, (cx - offset, y),
                             (elem["size"], elem["size"]))
        return paste_centered(out, mark, (cx + offset, y),
                              (elem["size"], elem["size"]))
    if kind == "faction":
        color = FACTION_COLOR.get(card.get("faction", ""))
        if color is None:
            return canvas
        return paste_centered(canvas, lib.faction(color), elem["pos"],
                              (elem["size"], elem["size"]))
    if kind == "stat":
        field = elem["field"]
        if field not in card:
            return canvas
        value = card[field]
        icon = elem["icon"]
        if value < 0 and elem.get("icon_neg"):
            icon = elem["icon_neg"]  # 负值换贴图（护甲→破甲）
        out = paste_centered(canvas, lib.icon(icon, "l"), elem["pos"],
                             (elem["icon_size"], elem["icon_size"]))
        text = f"{value:+d}" if elem.get("signed") else str(value)
        pos = elem["pos"]
        num_pos = (pos[0] + elem["num_offset"][0], pos[1] + elem["num_offset"][1])
        out = out.copy()
        draw = ImageDraw.Draw(out)
        draw.text(num_pos, text, font=lib.font("name", elem["font_size"]),
                  anchor="mm", fill=(255, 255, 255, 255),
                  stroke_width=2, stroke_fill=(0, 0, 0, 220))
        return out
    raise ValueError(f"未知元素 kind: {kind}")
```

`bwpdiy/render/pipeline.py` 改动点（保留既有结构，替换布局相关部分）：

- 删除 `from bwpdiy.render import layout`（若存在）与对 badges 旧函数（add_level_badge/add_rarity/add_faction/add_stats）的 import，改为：
  ```python
  from bwpdiy.render.badges import render_element, stat_obstacle
  from bwpdiy.render.layout import get_type_layout, load_layouts
  from bwpdiy.render.text import draw_region, fit_in_region
  ```
- 签名改 `def render_card(card: dict, assets_dir: Path, layout: dict | None = None) -> Image.Image:`
- 卡图/牌框/蒙版合成逻辑不变；其后改为：
  ```python
  type_layout = layout if layout is not None else get_type_layout(load_layouts(Path(assets_dir)), card_type)
  regions = type_layout["text_regions"]
  # 先测卡名宽度（rarity_flank 外移量依据；排不下按 0）
  name_fit = fit_in_region(card["name"], regions["name"], lib)
  ctx = {"name_width": name_fit[0].getlength(card["name"]) if name_fit else 0}
  for elem_name, elem in type_layout["elements"].items():
      canvas = render_element(canvas, lib, elem_name, elem, card, ctx)
  canvas = draw_region(canvas, lib, card["name"], regions["name"])
  if card.get("description") and "desc" in regions:
      obstacles = [stat_obstacle(e) for e in type_layout["elements"].values()
                   if e["kind"] == "stat" and e["field"] in card]
      canvas = draw_region(canvas, lib, card["description"], regions["desc"],
                           obstacles=obstacles)
  if "footer" in regions:
      footer = card.get("footer")
      if not footer:
          footer = f"{card.get('shikigami', card['name'])}-{card_type}"
          if card.get("special_type"):
              footer += f"/{card['special_type']}"
      canvas = draw_region(canvas, lib, footer, regions["footer"])
  ```
- 删除 `_STAT_KEYS` 与旧的 stats 分支、旧的 draw_name/draw_description 调用。

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_badges.py tests/test_pipeline.py -q`
Expected: 全过

- [ ] **Step 5: 全量回归 + Commit**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全绿（旧 test_badges/test_text 已在 Task 2/3 重写）

```bash
git add bwpdiy/render/badges.py bwpdiy/render/pipeline.py tests/test_badges.py tests/test_pipeline.py
git commit -m "feat(render): 元素化渲染与管线布局驱动——render_element+文本区映射+layout 覆盖参数"
git push
```

---

### Task 4: Web 配置工具后端（FastAPI）

**Files:**
- Create: `bwpdiy/web/app.py`
- Create: `bwpdiy/web/sample_cards.py`
- Modify: `bwpdiy/__main__.py`（uvicorn 启动）
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `render_card`、`layout.load_layouts`
- Produces:
  - `create_app(assets_dir: Path, static_dir: Path | None = None) -> FastAPI`
  - `GET /api/layout` → 当前完整布局 json（assets/layout.json 或默认回退）
  - `PUT /api/layout` → body 为完整布局 dict，写回 `<assets_dir>/layout.json`（UTF-8、ensure_ascii=False、indent=2），返回 {"ok": true}
  - `POST /api/preview` → body `{"type": "<类型>", "layout": {"elements":..,"text_regions":..}}`，用内置样卡数据 + 提交的布局渲染，返回 PNG（image/png）；类型未知 400，渲染异常 422（detail=异常消息）
  - `GET /` 与 `GET /layout` → static/layout.html
  - `SAMPLE_CARDS: dict[str, dict]`（六类型样卡，artwork 指向 tests/fixtures/sample_art.png 的绝对路径）

- [ ] **Step 1: 写失败测试**

`tests/test_web.py`：

```python
import pytest
from fastapi.testclient import TestClient

from bwpdiy.web.app import create_app


@pytest.fixture()
def client(assets_dir):
    return TestClient(create_app(assets_dir))


def test_get_layout(client):
    r = client.get("/api/layout")
    assert r.status_code == 200
    assert "战斗" in r.json()


def test_put_layout_roundtrip(client, assets_dir, tmp_path):
    r = client.get("/api/layout")
    layouts = r.json()
    layouts["战斗"]["elements"]["rarity"]["pos"] = [200, 200]
    r = client.put("/api/layout", json=layouts)
    assert r.status_code == 200 and r.json()["ok"]
    assert client.get("/api/layout").json()["战斗"]["elements"]["rarity"]["pos"] == [200, 200]


def test_preview_png(client):
    from bwpdiy.render.layout import load_layouts, get_type_layout
    tl = get_type_layout(load_layouts(client.app.state.assets_dir), "战斗")
    r = client.post("/api/preview", json={"type": "战斗", "layout": tl})
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert len(r.content) > 10000


def test_preview_bad_type(client):
    r = client.post("/api/preview", json={"type": "不存在", "layout": {"elements": {}, "text_regions": {}}})
    assert r.status_code == 400
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_web.py -q`
Expected: FAIL（bwpdiy.web.app 不存在）

- [ ] **Step 3: 实现**

`bwpdiy/web/sample_cards.py`：

```python
"""布局配置工具的预览样卡（六类型）。"""

from pathlib import Path

_ART = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "sample_art.png"

SAMPLE_CARDS: dict[str, dict] = {
    "式神": {"type": "式神", "name": "绯焰剑士", "faction": "红莲", "power": 3, "health": 4,
            "description": "当绯焰剑士攻击时，若本回合你已使用过战斗牌，本次攻击获得+1力量。"},
    "战斗": {"type": "战斗", "name": "裂地斩", "level": 1, "rarity": "R", "shikigami": "绯焰剑士",
            "power+": 1, "shield+": 1, "description": "获得贯通。"},
    "法术": {"type": "法术", "name": "觉醒·绯焰剑士", "level": 2, "rarity": "SR", "evolve": True,
            "shikigami": "绯焰剑士",
            "description": "觉醒：当绯焰剑士攻击时，若本回合你已使用过战斗牌，本次攻击获得+2力量与贯通；每回合第一次使用战斗牌后，随机对一个敌方式神造成2点伤害。"},
    "形态": {"type": "形态", "name": "炎凰之姿", "level": 3, "rarity": "SSR", "shikigami": "绯焰剑士",
            "power": 2, "health": 2, "description": "己方回合开始时，对所有敌方式神造成1点伤害。绯焰剑士气绝时，此形态不移除。"},
    "幻境": {"type": "幻境", "name": "熔岩幻境", "rarity": "N", "shikigami": "绯焰剑士",
            "durability": 6, "description": "回合结束时，获得1点鬼火。"},
    "协战": {"type": "协战", "name": "双刃协击", "rarity": "R", "shikigami": "绯焰剑士",
            "description": "协战：使本回合下一次攻击获得+1力量。"},
}

for _card in SAMPLE_CARDS.values():
    _card["_base_dir"] = str(_ART.parent)
    _card["artwork"] = {"images": [{"path": _ART.name}]}
```

`bwpdiy/web/app.py`：

```python
"""FastAPI 编辑器服务（当前含布局配置工具 API）。"""

import json
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response

from bwpdiy.render.layout import get_type_layout, load_layouts
from bwpdiy.render.pipeline import TYPE_FRAME_CODE, render_card
from bwpdiy.web.sample_cards import SAMPLE_CARDS

_STATIC = Path(__file__).parent / "static"


def create_app(assets_dir: Path, static_dir: Path | None = None) -> FastAPI:
    assets_dir = Path(assets_dir)
    static_dir = Path(static_dir) if static_dir else _STATIC
    app = FastAPI(title="BWPDIY")
    app.state.assets_dir = assets_dir

    @app.get("/")
    @app.get("/layout")
    def layout_page():
        return FileResponse(static_dir / "layout.html")

    @app.get("/api/layout")
    def get_layout():
        return JSONResponse(load_layouts(assets_dir))

    @app.put("/api/layout")
    async def put_layout(request: dict):
        path = assets_dir / "layout.json"
        path.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True}

    @app.post("/api/preview")
    async def preview(request: dict):
        card_type = request.get("type")
        if card_type not in TYPE_FRAME_CODE:
            raise HTTPException(400, f"未知卡牌类型: {card_type}")
        card = dict(SAMPLE_CARDS[card_type])
        try:
            img = render_card(card, assets_dir, layout=request["layout"])
        except Exception as e:
            raise HTTPException(422, f"渲染失败: {e}") from e
        buf = BytesIO()
        img.save(buf, "PNG")
        return Response(buf.getvalue(), media_type="image/png")

    return app
```

`bwpdiy/__main__.py`（整体替换）：

```python
"""python -m bwpdiy：启动编辑器 WebGUI（默认 http://127.0.0.1:8630）。"""

import sys


def main() -> int:
    import uvicorn

    from bwpdiy.web.app import create_app

    app = create_app("assets")
    uvicorn.run(app, host="127.0.0.1", port=8630)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_web.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add bwpdiy/web/app.py bwpdiy/web/sample_cards.py bwpdiy/__main__.py tests/test_web.py
git commit -m "feat(web): 布局配置工具后端——布局读写/样卡预览 API 与服务入口"
git push
```

---

### Task 5: Web 配置工具前端（layout.html）

**Files:**
- Create: `bwpdiy/web/static/layout.html`（内联 CSS+JS 单文件）
- Test: 无自动化新测试（后端 API 已由 Task 4 覆盖；本任务验收=手动冒烟：起服务、页面可用、拖拽/保存/预览正常）

**Interfaces:**
- Consumes: `GET /api/layout`、`PUT /api/layout`、`POST /api/preview`（Task 4）
- Produces: `/layout` 页面：
  - 顶部：6 类型 tab；右侧按钮「预览」「保存」
  - 左栏：元素列表 + 文本区列表（点击选中）
  - 中栏：canvas 显示预览图 + 覆盖层（元素锚点=圆点、stat 数字点=小方点、多边形顶点=方块、多边形描边）；拖拽移动；点击选中
  - 右栏：属性面板——元素：pos x/y、kind 相关字段（size/icon_size/num_offset/font_size/signed/icon）；文本区：选中顶点的 x/y、font_range、wrap、font；「添加顶点」「删除顶点」按钮

- [ ] **Step 1: 实现 layout.html**

单文件结构（实现者按此完整实现，允许组织方式微调但功能不得缺）：

```html
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>BWPDIY 布局配置</title>
<style>
  body { font-family: sans-serif; margin: 0; display: flex; height: 100vh; }
  #sidebar, #props { width: 220px; padding: 8px; overflow-y: auto; background: #f3efe8; }
  #main { flex: 1; display: flex; flex-direction: column; align-items: center; background: #3a3a3a; }
  #preview { margin-top: 12px; cursor: crosshair; background: #222; }
  .tab { padding: 4px 10px; margin: 2px; cursor: pointer; border: 1px solid #999; background: #fff; }
  .tab.active { background: #d9b96a; }
  .item { padding: 3px 6px; cursor: pointer; }
  .item.active { background: #d9b96a; }
  #props label { display: block; font-size: 12px; margin-top: 6px; }
  #props input, #props select { width: 90px; }
  button { margin: 4px; }
</style>
</head>
<body>
<div id="sidebar">
  <div id="types"></div>
  <h4>元素</h4><div id="elems"></div>
  <h4>文本区</h4><div id="regions"></div>
</div>
<div id="main">
  <div>
    <button id="btn-preview">预览</button>
    <button id="btn-save">保存</button>
    <span id="status"></span>
  </div>
  <canvas id="preview" width="512" height="512"></canvas>
</div>
<div id="props"></div>
<script>
// 状态
const TYPES = ["式神","战斗","法术","形态","幻境","协战"];
let layouts = null;          // 完整布局 dict（/api/layout）
let curType = "战斗";
let sel = null;              // {kind:'element'|'region'|'vertex', name, vi?}
const canvas = document.getElementById('preview');
const ctx = canvas.getContext('2d');
let previewImg = null;

// 初始化
async function boot() {
  layouts = await (await fetch('/api/layout')).json();
  buildTypes(); selectType('战斗');
}
function typeLayout() { return layouts[curType]; }

// 顶部类型 tab
function buildTypes() {
  const div = document.getElementById('types');
  div.innerHTML = '';
  for (const t of TYPES) {
    const b = document.createElement('button');
    b.textContent = t; b.className = 'tab';
    b.onclick = () => selectType(t);
    div.appendChild(b);
  }
}
function selectType(t) {
  curType = t; sel = null;
  document.querySelectorAll('.tab').forEach(b =>
    b.classList.toggle('active', b.textContent === t));
  buildLists(); buildProps(); refreshPreview();
}

// 左栏列表
function buildLists() {
  const tl = typeLayout();
  const ed = document.getElementById('elems'); ed.innerHTML = '';
  for (const name of Object.keys(tl.elements)) {
    const d = document.createElement('div');
    d.textContent = name; d.className = 'item';
    d.onclick = () => { sel = {kind:'element', name}; refreshSel(); };
    ed.appendChild(d);
  }
  const rd = document.getElementById('regions'); rd.innerHTML = '';
  for (const name of Object.keys(tl.text_regions)) {
    const d = document.createElement('div');
    d.textContent = name; d.className = 'item';
    d.onclick = () => { sel = {kind:'region', name}; refreshSel(); };
    rd.appendChild(d);
  }
}
function refreshSel() {
  document.querySelectorAll('.item').forEach(d =>
    d.classList.toggle('active', sel && d.textContent === sel.name));
  buildProps(); draw();
}

// 预览
async function refreshPreview() {
  const r = await fetch('/api/preview', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({type: curType, layout: typeLayout()}),
  });
  const status = document.getElementById('status');
  if (!r.ok) { status.textContent = '预览失败: ' + (await r.json()).detail; return; }
  status.textContent = '';
  const blob = await r.blob();
  const img = new Image();
  img.onload = () => { previewImg = img; draw(); };
  img.src = URL.createObjectURL(blob);
}

// 画布绘制：预览图拉伸铺满 512 画布 + 覆盖层
function draw() {
  ctx.clearRect(0, 0, 512, 512);
  if (previewImg) ctx.drawImage(previewImg, 0, 0, 512, 512);
  const tl = typeLayout();
  for (const [name, e] of Object.entries(tl.elements)) {
    handle(e.pos, sel && sel.name === name ? '#ff4' : '#0ff');
    if (e.kind === 'stat') {
      const np = [e.pos[0] + e.num_offset[0], e.pos[1] + e.num_offset[1]];
      handle(np, sel && sel.name === name ? '#ff4' : '#f8f', 4, true);
    }
  }
  for (const [name, r] of Object.entries(tl.text_regions)) {
    ctx.strokeStyle = sel && sel.name === name ? '#ff4' : '#4f4';
    ctx.beginPath();
    r.polygon.forEach(([x, y], i) => i ? ctx.lineTo(x, y) : ctx.moveTo(x, y));
    ctx.closePath(); ctx.stroke();
    r.polygon.forEach(([x, y], vi) =>
      handle([x, y], sel && sel.kind === 'vertex' && sel.name === name && sel.vi === vi ? '#ff4' : '#4f4', 5, true));
  }
}
function handle([x, y], color, s = 6, square = false) {
  ctx.fillStyle = color;
  if (square) ctx.fillRect(x - s/2, y - s/2, s, s);
  else { ctx.beginPath(); ctx.arc(x, y, s, 0, 7); ctx.fill(); }
}

// 拖拽
let drag = null;
canvas.addEventListener('mousedown', ev => {
  const [mx, my] = mousePos(ev);
  drag = pick(mx, my);
  if (drag) { sel = drag.sel; refreshSel(); }
});
canvas.addEventListener('mousemove', ev => {
  if (!drag) return;
  const [mx, my] = mousePos(ev);
  drag.set(Math.round(mx), Math.round(my));
  buildProps(); draw();
});
canvas.addEventListener('mouseup', () => { if (drag) { drag = null; refreshPreview(); } });
function mousePos(ev) {
  const r = canvas.getBoundingClientRect();
  return [ev.clientX - r.left, ev.clientY - r.top];
}
function pick(mx, my) {
  const tl = typeLayout();
  const near = (x, y) => Math.hypot(mx - x, my - y) < 8;
  for (const [name, e] of Object.entries(tl.elements)) {
    if (e.kind === 'stat') {
      const nx = e.pos[0] + e.num_offset[0], ny = e.pos[1] + e.num_offset[1];
      if (near(nx, ny)) return { sel: {kind:'element', name},
        set: (x, y) => { e.num_offset = [x - e.pos[0], y - e.pos[1]]; } };
    }
    if (near(...e.pos)) return { sel: {kind:'element', name}, set: (x, y) => { e.pos = [x, y]; } };
  }
  for (const [name, r] of Object.entries(tl.text_regions)) {
    for (let vi = 0; vi < r.polygon.length; vi++) {
      if (near(...r.polygon[vi])) return { sel: {kind:'vertex', name, vi},
        set: (x, y) => { r.polygon[vi] = [x, y]; } };
    }
  }
  return null;
}

// 右栏属性面板
function buildProps() {
  const div = document.getElementById('props');
  div.innerHTML = '';
  if (!sel) { div.textContent = '点击元素/文本区/顶点以编辑'; return; }
  const tl = typeLayout();
  if (sel.kind === 'element') {
    const e = tl.elements[sel.name];
    div.appendChild(title(`${sel.name} (${e.kind})`));
    numRow(div, 'x', e.pos[0], v => { e.pos[0] = v; draw(); });
    numRow(div, 'y', e.pos[1], v => { e.pos[1] = v; draw(); });
    if (e.kind === 'stat') {
      numRow(div, 'icon_size', e.icon_size, v => e.icon_size = v);
      numRow(div, 'num_dx', e.num_offset[0], v => { e.num_offset[0] = v; draw(); });
      numRow(div, 'num_dy', e.num_offset[1], v => { e.num_offset[1] = v; draw(); });
      numRow(div, 'font_size', e.font_size, v => e.font_size = v);
      checkRow(div, 'signed', e.signed, v => e.signed = v);
      selRow(div, 'icon', ['ll','sm','hj','nj','pj','zl','fl','sj','nl'], e.icon, v => e.icon = v);
      selRow(div, 'icon_neg', ['（无）','ll','sm','hj','nj','pj','zl','fl','sj','nl'], e.icon_neg || '（无）',
             v => { if (v === '（无）') delete e.icon_neg; else e.icon_neg = v; });
    }
    if (e.kind === 'rarity_flank') {
      numRow(div, 'gap', e.gap, v => e.gap = v);
      numRow(div, 'size', e.size, v => e.size = v);
    }
    if (e.kind === 'faction')
      numRow(div, 'size', e.size, v => e.size = v);
    if (e.kind === 'level_badge') {
      numRow(div, 'base_size', e.base_size, v => e.base_size = v);
      numRow(div, 'star_size', e.star_size, v => e.star_size = v);
      numRow(div, 'num_size', e.num_size, v => e.num_size = v);
    }
  } else {
    const r = tl.text_regions[sel.name];
    div.appendChild(title(`${sel.name} 文本区`));
    if (sel.kind === 'vertex') {
      numRow(div, 'x', r.polygon[sel.vi][0], v => { r.polygon[sel.vi][0] = v; draw(); });
      numRow(div, 'y', r.polygon[sel.vi][1], v => { r.polygon[sel.vi][1] = v; draw(); });
    }
    numRow(div, 'font_max', r.font_range[0], v => r.font_range[0] = v);
    numRow(div, 'font_min', r.font_range[1], v => r.font_range[1] = v);
    checkRow(div, 'wrap', r.wrap, v => r.wrap = v);
    selRow(div, 'font', ['name','desc'], r.font, v => r.font = v);
    const add = document.createElement('button');
    add.textContent = '添加顶点';
    add.onclick = () => {
      const c = centroid(r.polygon);
      r.polygon.push([Math.round(c[0] + 10), Math.round(c[1] + 10)]);
      draw();
    };
    const del = document.createElement('button');
    del.textContent = '删除选中顶点';
    del.onclick = () => {
      if (sel.kind === 'vertex' && r.polygon.length > 3) {
        r.polygon.splice(sel.vi, 1); sel = {kind:'region', name: sel.name}; refreshSel();
      }
    };
    div.appendChild(add); div.appendChild(del);
  }
}
function title(t) { const h = document.createElement('h4'); h.textContent = t; return h; }
function numRow(div, label, val, set) {
  const l = document.createElement('label');
  l.textContent = label + ' ';
  const i = document.createElement('input');
  i.type = 'number'; i.value = val;
  i.onchange = () => set(parseInt(i.value, 10));
  l.appendChild(i); div.appendChild(l);
}
function checkRow(div, label, val, set) {
  const l = document.createElement('label');
  l.textContent = label + ' ';
  const i = document.createElement('input');
  i.type = 'checkbox'; i.checked = val;
  i.onchange = () => set(i.checked);
  l.appendChild(i); div.appendChild(l);
}
function selRow(div, label, opts, val, set) {
  const l = document.createElement('label');
  l.textContent = label + ' ';
  const s = document.createElement('select');
  for (const o of opts) {
    const op = document.createElement('option');
    op.value = op.textContent = o;
    if (o === val) op.selected = true;
    s.appendChild(op);
  }
  s.onchange = () => set(s.value);
  l.appendChild(s); div.appendChild(l);
}
function centroid(poly) {
  return [poly.reduce((a, p) => a + p[0], 0) / poly.length,
          poly.reduce((a, p) => a + p[1], 0) / poly.length];
}

// 保存
document.getElementById('btn-save').onclick = async () => {
  const r = await fetch('/api/layout', {method: 'PUT',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(layouts)});
  document.getElementById('status').textContent = r.ok ? '已保存' : '保存失败';
};
document.getElementById('btn-preview').onclick = refreshPreview;
boot();
</script>
</body>
</html>
```

- [ ] **Step 2: 手动冒烟**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m bwpdiy &
curl -s http://127.0.0.1:8630/api/layout | head -c 200
curl -s -X POST http://127.0.0.1:8630/api/preview -H "Content-Type: application/json" -d @<(python -c "import json;print(json.dumps({'type':'战斗','layout':json.load(open('assets/layout.json',encoding='utf-8'))['战斗']}))") -o /tmp/preview.png && file /tmp/preview.png
kill %1
```

Expected: /api/layout 返回 json；preview 返回 PNG。页面交互部分在 Task 6 由用户实测。

- [ ] **Step 3: 全量测试 + Commit**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q
git add bwpdiy/web/static/layout.html
git commit -m "feat(web): 布局配置页——类型切换/拖拽锚点与多边形顶点/属性面板/预览保存"
git push
```

---

### Task 6: 用户定稿布局 + 文档同步

**Files:**
- Modify: `assets/layout.json`（用户在 GUI 中定稿，由工具写回）
- Modify: `README.md`（进度勾选 M1/M1.5、新增 `python -m bwpdiy` 用法与 /layout 页说明）
- Modify: `AGENTS.md`（布局配置纪律：layout.json 改动须用工具或经视觉确认）
- Test: 无新增

- [ ] **Step 1: 用户用 GUI 定稿六类型布局**

起服务 `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m bwpdiy`，用户访问 http://127.0.0.1:8630/layout ，逐类型拖拽调整、保存。主协调者陪同处理工具 bug（若有走 fix loop）。

- [ ] **Step 2: 定稿后的 layout.json 同步到包内默认**

```bash
cp assets/layout.json bwpdiy/render/default_layout.json
```

- [ ] **Step 3: 全量测试 + 渲染六类型样卡人工过目**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q
# 用 examples/ 下六个样卡 json 各渲染一张，ReadMediaFile 逐张复查
```

- [ ] **Step 4: Commit**

```bash
git add assets/layout.json bwpdiy/render/default_layout.json README.md AGENTS.md
git commit -m "feat(layout): 六类型布局定稿（Web 配置工具调整）+ 文档同步"
git push
```

---

## Self-Review 记录

- **Spec 覆盖**：设计（布局配置系统设计 §1-3）逐项对应 Task 1（schema/加载器/默认集）/ Task 2（多边形排版）/ Task 3（元素渲染+管线）/ Task 4-5（Web 工具）/ Task 6（用户定稿）。render_card 向后兼容（第三参可选）。
- **占位符扫描**：无 TBD；Task 5 前端为完整可实现的功能清单 + 结构代码，组织方式允许微调属有意留白（HTML 细节不影响接口）。
- **类型一致性**：`load_layouts/get_type_layout`（Task 1 定义，Task 3/4 消费）；`render_element(canvas, lib, name, elem, card)`（Task 3 定义并消费）；`draw_region(canvas, lib, text, region)`（Task 2 定义，Task 3 消费）；`create_app(assets_dir)`（Task 4 定义，__main__ 与测试消费）；`render_card(card, assets_dir, layout=None)`（Task 3，Task 4 消费）。旧 `_STAT_POSITIONS/add_stats/draw_name/draw_description/layout 常量` 全部在 Task 1-3 删除，无悬挂引用（Task 3 Step 3 明确删除点）。
- **风险记录**：Task 1 Step 5 允许中间态红（旧测试引用已删常量），Task 2/3 依次转绿——执行者须按顺序做，不要在 Task 1 停下来修旧测试。stat 数字字体固定用 name 字体（官方观感相近，GUI 可调大小）。幻境/协战框有效区比 xt 宽，footer/数值标 x 坐标为统一初值，用户定稿时按类型微调——这正是配置工具的存在意义。
