# M1 渲染管线（render）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `bwpdiy.render` 渲染核心库：输入卡牌 dict + assets 目录，输出 512×512 完整卡面 PNG（PIL），含卡图变换/蒙版/牌框/图标层/纯文本自动排版，并可用命令行渲染示例卡。

**Architecture:** 函数式管线，无全局状态。分层：资源加载（assets）→ 卡图处理（artwork）→ 图标层（badges）→ 文本层（text）→ 总装（pipeline）。坐标常量集中在 layout.py，便于视觉复查调优。

**Tech Stack:** Python 3.12+ / Pillow（render 层唯一第三方依赖）/ pytest。

## Global Constraints

- render 层**只依赖 Pillow**（CLI 用 stdlib json，不用 yaml）；不得 import `bwpdiy.store`/`bwpdiy.web`/fastapi。
- 卡面画布 **512×512 RGBA**（实测资源尺寸；设计文档 §4 的 307×546 系 legacy README 旧值，Task 1 修正）。
- 一期固定：牌框版型 `low`、框品 `norm`；等级数字颜色固定 `brown`（对局 4 色二期）。
- 资源命名（不得硬编码错）：`frames/frame_{zd|fs|xt|hj|xz}_{norm|blue|black|red}_{high|low}.png`、`masks/mask_{type}_low.png`、`levels/base.png|star.png|{blue|brown|cyan|purple|red|yellow}_{1|2|3}.png`、`rarity/{N|R|SR|SSR}.png`、`factions/{red|green|blue|purple}_{1|2|3}.png`、`icons/{fl|hj|ll|nj|nl|pj|sj|sm|zl}_{l|s}.png`、`fonts/田氏颜体大字库（卡牌名字体）.ttf`、`fonts/方正北魏楷书（卡牌描述字体）.ttf`。
- 蒙版只有 `_low` 变体；`frame_xz` 只有 `norm_low`——一期不涉及缺失组合。
- 类型→牌框代码：式神/形态→`xt`，战斗→`zd`，法术→`fs`，幻境→`hj`，协战→`xz`。
- 派系→资源色：红莲→red，苍叶→green，青岚→blue，紫岩→purple，无相→无派系标（跳过）。
- 术语以 `docs/terminology.md` 为准；字段缺省规则：`artwork` 整段可缺省，`path` 默认 `<card_id>.png`，offset 0/0、scale 1.0。
- 测试命令（Windows Git Bash）：`PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`；迭代期可只跑受影响文件。
- 中文 conventional commit；**每次 commit 后 `git push`**（失败不阻塞，汇报即可）。
- 坐标常量初值为实测估计值，**最终以 Task 6 用户视觉复查为准**。

## 实测资源事实（制定依据，实施时以此为准）

- 画布 512×512；牌框有效区（alpha>10 bbox）：xt x112–400/y4–511（288×507 ≈ 9:16），zd 287×512，fs 288×512，hj 308×503，xz 296×512——中央卡面接近官方竖版比例，四周透明。render_card 输出整画布 512×512（不裁剪，各类型有效区宽度不一，裁剪会使输出尺寸不一致），trim/缩放由调用方负责。
- `masks/{type}_bound.png` 为整卡面轮廓柔边剪影，legacy 代码中无任何引用，**渲染管线不使用**（保留在 assets/ 仅作存档）。
- 卡图蒙版区 bbox ≈ x 119–394, y 9–328（拱形顶、波浪底）。
- 文本区（牌框羊皮纸部分）≈ x 125–387, y 340–500。
- `levels/base.png` 64×64，`star.png` 126×127，等级数字 64×64（6 色），rarity 64×64（N.png 为 P 模式，加载需 convert RGBA），factions 200×200，icons 64(_l)/32(_s)。
- legacy 等级标参数：位置中心 (120,65)，base 72×72 → star 60×60（仅觉醒）→ 数字 40×40，实测观感正确（见 legacy/bwpCardDIY/output/test.png）。

## 文件结构

```
bwpdiy/render/
├── __init__.py      # 已存在，导出 render_card（不动）
├── common.py        # Task 1：paste_centered 等通用贴图工具
├── assets.py        # Task 1：AssetLibrary 资源加载+缓存
├── artwork.py       # Task 2：fit_artwork / apply_mask
├── layout.py        # Task 3：全部坐标/尺寸常量
├── badges.py        # Task 3：等级标/稀有度/派系/数值标
├── text.py          # Task 4：卡名+描述自动排版
├── pipeline.py      # Task 5：render_card 总装（改写现有骨架）
└── __main__.py      # Task 6：CLI 渲染单卡（json 输入）
tests/
├── conftest.py      # Task 1：ASSETS/FIXTURES 路径
├── fixtures/sample_art.png   # Task 1：自 legacy 复制的示例卡图
├── test_assets.py   # Task 1
├── test_artwork.py  # Task 2
├── test_badges.py   # Task 3
├── test_text.py     # Task 4
└── test_pipeline.py # Task 5
```

---

### Task 1: 资源加载层（common.py + assets.py）与尺寸修正

**Files:**
- Create: `bwpdiy/render/common.py`
- Create: `bwpdiy/render/assets.py`
- Create: `tests/conftest.py`
- Create: `tests/fixtures/sample_art.png`（复制自 legacy）
- Test: `tests/test_assets.py`
- Modify: `bwpdiy/render/pipeline.py`（CARD_SIZE 改 (512, 512)）
- Modify: `docs/superpowers/specs/2026-09-14-bwpdiy-design.md`（§4 输出尺寸 307×546 → 512×512）

**Interfaces:**
- Consumes: 无
- Produces:
  - `AssetLibrary(root: Path)`；方法 `.frame(type_code, variant='norm', splitter='low')`、`.mask(type_code, splitter='low')`（返回 'L' 模式）、`.level_base()`、`.level_star()`、`.level_num(color, n)`、`.rarity(r)`、`.faction(color, style=1)`、`.icon(name, size='l')` → 均返回 `PIL.Image.Image`（RGBA）；`.font(kind, size)`（kind ∈ {'name','desc'}）→ `ImageFont.FreeTypeFont`；资源不存在抛 `FileNotFoundError`（信息含完整路径）。
  - `common.paste_centered(canvas: Image.Image, img: Image.Image, center: tuple[int,int], size: tuple[int,int]|None = None) -> Image.Image`

- [ ] **Step 1: 复制测试卡图 fixture**

```bash
mkdir -p tests/fixtures
cp legacy/bwpCardDIY/test.png tests/fixtures/sample_art.png
ls -la tests/fixtures/
```

- [ ] **Step 2: 写失败测试**

`tests/conftest.py`：

```python
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture()
def assets_dir() -> Path:
    return ASSETS


@pytest.fixture()
def sample_art() -> Path:
    return FIXTURES / "sample_art.png"
```

`tests/test_assets.py`：

```python
import pytest
from PIL import Image, ImageFont

from bwpdiy.render.assets import AssetLibrary


def test_load_frame_and_mask(assets_dir):
    lib = AssetLibrary(assets_dir)
    frame = lib.frame("xt")
    assert frame.mode == "RGBA" and frame.size == (512, 512)
    mask = lib.mask("xt")
    assert mask.mode == "L" and mask.size == (512, 512)


def test_load_levels_and_rarity(assets_dir):
    lib = AssetLibrary(assets_dir)
    assert lib.level_base().mode == "RGBA"
    assert lib.level_star().mode == "RGBA"
    assert lib.level_num("brown", 2).mode == "RGBA"
    assert lib.rarity("SSR").mode == "RGBA"  # N.png 是 P 模式，必须 convert


def test_load_faction_and_icon(assets_dir):
    lib = AssetLibrary(assets_dir)
    assert lib.faction("red").mode == "RGBA"
    assert lib.icon("sm", "l").mode == "RGBA"


def test_load_fonts(assets_dir):
    lib = AssetLibrary(assets_dir)
    f = lib.font("name", 36)
    assert isinstance(f, ImageFont.FreeTypeFont) and f.size == 36
    assert lib.font("desc", 18).size == 18


def test_missing_resource_raises(assets_dir):
    lib = AssetLibrary(assets_dir)
    with pytest.raises(FileNotFoundError) as e:
        lib.frame("xx")
    assert "frame_xx_norm_low.png" in str(e.value)
```

- [ ] **Step 3: 跑测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_assets.py -q`
Expected: FAIL（`ModuleNotFoundError: bwpdiy.render.assets`）

- [ ] **Step 4: 实现 common.py 与 assets.py**

`bwpdiy/render/common.py`：

```python
"""通用贴图工具。"""

from PIL import Image


def paste_centered(canvas: Image.Image, img: Image.Image,
                   center: tuple[int, int],
                   size: tuple[int, int] | None = None) -> Image.Image:
    """把 img 缩放至 size 后按中心点 center 贴到 canvas 上（居中对齐），返回新图。"""
    if size is None:
        size = img.size
    resized = img.resize(size, Image.Resampling.LANCZOS).convert("RGBA")
    out = canvas.copy()
    out.paste(resized, (center[0] - size[0] // 2, center[1] - size[1] // 2), resized)
    return out
```

`bwpdiy/render/assets.py`：

```python
"""美术资源加载与缓存。"""

from pathlib import Path

from PIL import Image, ImageFont

FONT_FILES = {
    "name": "田氏颜体大字库（卡牌名字体）.ttf",
    "desc": "方正北魏楷书（卡牌描述字体）.ttf",
}


class AssetLibrary:
    """按命名约定加载 assets/ 资源，带内存缓存。

    图片以 RGBA 返回（蒙版为 L）；调用方只读使用（paste/resize 不修改原图）。
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self._cache: dict[tuple, object] = {}

    def _img(self, rel: str, mode: str = "RGBA") -> Image.Image:
        key = ("img", rel)
        if key not in self._cache:
            path = self.root / rel
            if not path.is_file():
                raise FileNotFoundError(f"美术资源缺失: {path}")
            self._cache[key] = Image.open(path).convert(mode)
        return self._cache[key]

    def frame(self, type_code: str, variant: str = "norm", splitter: str = "low") -> Image.Image:
        return self._img(f"frames/frame_{type_code}_{variant}_{splitter}.png")

    def mask(self, type_code: str, splitter: str = "low") -> Image.Image:
        return self._img(f"masks/mask_{type_code}_{splitter}.png", mode="L")

    def level_base(self) -> Image.Image:
        return self._img("levels/base.png")

    def level_star(self) -> Image.Image:
        return self._img("levels/star.png")

    def level_num(self, color: str, n: int) -> Image.Image:
        return self._img(f"levels/{color}_{n}.png")

    def rarity(self, rarity: str) -> Image.Image:
        return self._img(f"rarity/{rarity}.png")

    def faction(self, color: str, style: int = 1) -> Image.Image:
        suffix = "" if color == "blue" and style == 1 else f"_{style}"
        return self._img(f"factions/{color}{suffix}.png")

    def icon(self, name: str, size: str = "l") -> Image.Image:
        return self._img(f"icons/{name}_{size}.png")

    def font(self, kind: str, size: int) -> ImageFont.FreeTypeFont:
        assert kind in FONT_FILES, f"未知字体种类: {kind}"
        key = ("font", kind, size)
        if key not in self._cache:
            path = self.root / "fonts" / FONT_FILES[kind]
            if not path.is_file():
                raise FileNotFoundError(f"字体缺失: {path}")
            self._cache[key] = ImageFont.truetype(str(path), size)
        return self._cache[key]
```

注：`factions/blue.png` 无 `_1` 后缀（实测文件名），其余色为 `{color}_1.png`——上面 `faction()` 的 suffix 逻辑即为此。

同时把 `bwpdiy/render/pipeline.py` 中 `CARD_SIZE = (307, 546)` 改为 `CARD_SIZE = (512, 512)`；设计文档 §4「输出尺寸沿用资源原生尺寸（307×546）」改为「输出尺寸沿用资源原生尺寸（512×512）」。

- [ ] **Step 5: 跑测试确认通过**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_assets.py -q`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add bwpdiy/render/common.py bwpdiy/render/assets.py bwpdiy/render/pipeline.py tests/ docs/superpowers/specs/2026-09-14-bwpdiy-design.md
git commit -m "feat(render): 资源加载层 AssetLibrary 与贴图工具，修正卡面尺寸为 512×512"
git push
```

---

### Task 2: 卡图变换与蒙版（artwork.py）

**Files:**
- Create: `bwpdiy/render/artwork.py`
- Test: `tests/test_artwork.py`

**Interfaces:**
- Consumes: 无（纯 PIL 函数）
- Produces:
  - `fit_artwork(img: Image.Image, target_size: tuple[int,int], offset_x: float = 0, offset_y: float = 0, scale: float = 1.0) -> Image.Image` —— 等比缩放至覆盖 target_size（cover），再乘 scale，按"中心 + offset"裁剪为 target_size；offset 单位为输出像素，向右/下为正；越界自动钳制。
  - `apply_mask(img: Image.Image, mask: Image.Image, blur_radius: float = 1.0) -> Image.Image` —— 蒙版高斯平滑后作为 alpha 贴到 img。

- [ ] **Step 1: 写失败测试**

`tests/test_artwork.py`：

```python
from PIL import Image

from bwpdiy.render.artwork import apply_mask, fit_artwork


def make_art(w=800, h=600):
    return Image.new("RGBA", (w, h), (200, 100, 50, 255))


def test_fit_cover_and_size():
    out = fit_artwork(make_art(), (512, 512))
    assert out.size == (512, 512)
    # cover：800x600 → 缩放 512/600，宽 683 ≥ 512


def test_fit_scale_enlarges():
    # scale 放大后裁剪窗口左移空间变大，不报错且尺寸不变
    out = fit_artwork(make_art(), (512, 512), scale=1.5)
    assert out.size == (512, 512)


def test_fit_offset_shifts_window():
    # 用左右两半不同颜色的图验证 offset 平移裁剪窗口
    img = Image.new("RGBA", (1024, 512), (255, 0, 0, 255))
    for x in range(512, 1024):
        for y in range(512):
            img.putpixel((x, y), (0, 0, 255, 255))
    left = fit_artwork(img, (512, 512), offset_x=-256)
    right = fit_artwork(img, (512, 512), offset_x=256)
    assert left.getpixel((10, 256)) == (255, 0, 0, 255)
    assert right.getpixel((502, 256)) == (0, 0, 255, 255)


def test_fit_offset_clamped():
    out = fit_artwork(make_art(600, 600), (512, 512), offset_x=99999)
    assert out.size == (512, 512)  # 钳制不抛异常


def test_apply_mask_alpha():
    img = make_art(512, 512)
    mask = Image.new("L", (512, 512), 0)
    for y in range(100, 200):
        for x in range(100, 200):
            mask.putpixel((x, y), 255)
    out = apply_mask(img, mask, blur_radius=0)
    assert out.getpixel((150, 150))[3] == 255
    assert out.getpixel((10, 10))[3] == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_artwork.py -q`
Expected: FAIL（`ModuleNotFoundError: bwpdiy.render.artwork`）

- [ ] **Step 3: 实现 artwork.py**

`bwpdiy/render/artwork.py`：

```python
"""卡图（artwork）变换与蒙版裁切。"""

from PIL import Image, ImageFilter


def fit_artwork(img: Image.Image, target_size: tuple[int, int],
                offset_x: float = 0, offset_y: float = 0,
                scale: float = 1.0) -> Image.Image:
    """等比缩放至覆盖 target_size 后乘 scale，按 中心+offset 裁剪为 target_size。

    offset 单位为输出像素（右/下为正），越界钳制到可裁剪范围。
    """
    tw, th = target_size
    w, h = img.size
    cover = max(tw / w, th / h) * scale
    nw, nh = max(round(w * cover), 1), max(round(h * cover), 1)
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - tw) / 2 + offset_x
    top = (nh - th) / 2 + offset_y
    left = min(max(round(left), 0), max(nw - tw, 0))
    top = min(max(round(top), 0), max(nh - th, 0))
    return resized.crop((left, top, left + tw, top + th)).convert("RGBA")


def apply_mask(img: Image.Image, mask: Image.Image,
               blur_radius: float = 1.0) -> Image.Image:
    """蒙版高斯平滑（radius=1 沿用 legacy 观感）后作为 img 的 alpha。"""
    smoothed = mask.filter(ImageFilter.GaussianBlur(blur_radius))
    out = img.copy()
    out.putalpha(smoothed)
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_artwork.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add bwpdiy/render/artwork.py tests/test_artwork.py
git commit -m "feat(render): 卡图 cover 缩放/偏移裁剪与蒙版高斯平滑"
git push
```

---

### Task 3: 图标层（layout.py + badges.py）

**Files:**
- Create: `bwpdiy/render/layout.py`
- Create: `bwpdiy/render/badges.py`
- Test: `tests/test_badges.py`

**Interfaces:**
- Consumes: `AssetLibrary`（Task 1）、`common.paste_centered`（Task 1）
- Produces:
  - `layout` 模块常量（见下，Task 4/5 依赖 `NAME_BOX`/`DESC_BOX`/`NAME_FONT_RANGE`/`DESC_FONT_RANGE`/`LEVEL_POS` 等）
  - `add_level_badge(canvas, lib, level: int, evolve: bool = False, color: str = "brown") -> Image.Image`（level 为 None 时调用方跳过）
  - `add_rarity(canvas, lib, rarity: str) -> Image.Image`
  - `add_faction(canvas, lib, faction_color: str) -> Image.Image`
  - `add_stats(canvas, lib, stats: list[tuple[str, int]]) -> Image.Image` —— stats 为 (名称, 值) 列表，按预设位置绘制；正值加成带 `+` 号由调用方传入时决定（见 add_stats 实现，值 >0 且 `signed=True` 的类别才加号——简化为：调用方直接把要显示的字符串放进值里？否——保持数值，显示规则：`('power', 3)` → `3`，`('power+', 1)` → `+1`。即键名以 `+` 结尾表示加成显示带正负号。）

- [ ] **Step 1: 写失败测试**

`tests/test_badges.py`：

```python
from PIL import Image

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.badges import (add_faction, add_level_badge, add_rarity,
                                  add_stats)


def canvas():
    return Image.new("RGBA", (512, 512), (0, 0, 0, 0))


def alpha_at(img, x, y):
    return img.getpixel((x, y))[3]


def test_level_badge_three_layers(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = add_level_badge(canvas(), lib, level=2, evolve=True)
    assert alpha_at(img, 120, 65) > 0  # 等级标中心已有内容


def test_level_badge_without_evolve(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = add_level_badge(canvas(), lib, level=1, evolve=False)
    assert alpha_at(img, 120, 65) > 0


def test_rarity_and_faction(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = add_rarity(canvas(), lib, "SSR")
    img = add_faction(img, lib, "red")
    a = [p[3] for p in img.getdata()]
    assert sum(1 for v in a if v > 0) > 100  # 两处图标均落上像素


def test_stats_signed_and_plain(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = add_stats(canvas(), lib, [("power", 3), ("health", 4)])
    assert sum(1 for p in img.getdata() if p[3] > 0) > 0
    img2 = add_stats(canvas(), lib, [("power+", 1), ("shield+", -1)])
    assert sum(1 for p in img2.getdata() if p[3] > 0) > 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_badges.py -q`
Expected: FAIL（`ModuleNotFoundError: bwpdiy.render.badges`）

- [ ] **Step 3: 实现 layout.py 与 badges.py**

`bwpdiy/render/layout.py`（初值为实测估计，Task 6 视觉复查调优）：

```python
"""卡面布局常量（画布 512×512）。区域为 (x0, y0, x1, y1)。"""

CANVAS_SIZE = (512, 512)

# 等级标（三层叠加，同一中心点）
LEVEL_POS = (120, 65)
LEVEL_BASE_SIZE = (72, 72)
LEVEL_STAR_SIZE = (60, 60)
LEVEL_NUM_SIZE = (40, 40)

# 稀有度标：右上角，与等级标对称
RARITY_POS = (392, 65)
RARITY_SIZE = (48, 48)

# 派系标（式神）：顶部中央
FACTION_POS = (256, 40)
FACTION_SIZE = (40, 40)

# 数值标：底部左右角（式神力量/生命；战斗加成；幻境耐久居中）
STAT_LEFT_POS = (145, 478)
STAT_RIGHT_POS = (367, 478)
STAT_CENTER_POS = (256, 478)
STAT_FONT_SIZE = 30

# 文本区
NAME_BOX = (130, 340, 382, 382)
DESC_BOX = (130, 388, 382, 495)
NAME_FONT_RANGE = (36, 16)   # (最大, 最小)
DESC_FONT_RANGE = (22, 12)
TEXT_FILL = (60, 45, 30, 255)        # 深棕（羊皮纸底色上）
```

`bwpdiy/render/badges.py`：

```python
"""图标层：等级标 / 稀有度标 / 派系标 / 数值标。"""

from PIL import Image, ImageDraw

from bwpdiy.render import layout
from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.common import paste_centered

# 数值标位置：键名 → 锚点；（键名以 + 结尾表示加成，显示带正负号）
_STAT_POSITIONS = {
    "power": layout.STAT_LEFT_POS,
    "health": layout.STAT_RIGHT_POS,
    "power+": layout.STAT_LEFT_POS,
    "shield+": layout.STAT_RIGHT_POS,
    "durability": layout.STAT_CENTER_POS,
}


def add_level_badge(canvas: Image.Image, lib: AssetLibrary, level: int,
                    evolve: bool = False, color: str = "brown") -> Image.Image:
    """等级标三层叠加：底座 → 觉醒星（仅觉醒）→ 等级数字。"""
    out = paste_centered(canvas, lib.level_base(), layout.LEVEL_POS, layout.LEVEL_BASE_SIZE)
    if evolve:
        out = paste_centered(out, lib.level_star(), layout.LEVEL_POS, layout.LEVEL_STAR_SIZE)
    return paste_centered(out, lib.level_num(color, level), layout.LEVEL_POS, layout.LEVEL_NUM_SIZE)


def add_rarity(canvas: Image.Image, lib: AssetLibrary, rarity: str) -> Image.Image:
    return paste_centered(canvas, lib.rarity(rarity), layout.RARITY_POS, layout.RARITY_SIZE)


def add_faction(canvas: Image.Image, lib: AssetLibrary, faction_color: str) -> Image.Image:
    return paste_centered(canvas, lib.faction(faction_color), layout.FACTION_POS, layout.FACTION_SIZE)


def add_stats(canvas: Image.Image, lib: AssetLibrary,
              stats: list[tuple[str, int]]) -> Image.Image:
    """数值标：白字黑边。键名以 + 结尾的显示正负号（+1 / -1），其余显示绝对值。"""
    out = canvas.copy()
    draw = ImageDraw.Draw(out)
    font = lib.font("name", layout.STAT_FONT_SIZE)
    for key, value in stats:
        pos = _STAT_POSITIONS[key]
        text = f"{value:+d}" if key.endswith("+") else str(value)
        draw.text(pos, text, font=font, anchor="mm",
                  fill=(255, 255, 255, 255), stroke_width=2,
                  stroke_fill=(0, 0, 0, 220))
    return out
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_badges.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add bwpdiy/render/layout.py bwpdiy/render/badges.py tests/test_badges.py
git commit -m "feat(render): 图标层——等级标三层/稀有度/派系/数值标与布局常量"
git push
```

---

### Task 4: 文本排版（text.py）

**Files:**
- Create: `bwpdiy/render/text.py`
- Test: `tests/test_text.py`

**Interfaces:**
- Consumes: `AssetLibrary.font`（Task 1）、`layout.NAME_BOX/DESC_BOX/NAME_FONT_RANGE/DESC_FONT_RANGE/TEXT_FILL`（Task 3）
- Produces:
  - `draw_name(canvas, lib, name: str) -> Image.Image` —— 单行，字号从大到小收至适应 NAME_BOX 宽度，水平居中、垂直居中
  - `draw_description(canvas, lib, text: str) -> Image.Image` —— 逐字符贪心换行，字号从大到小试至整体适应 DESC_BOX，逐行水平居中
  - `layout_lines(text: str, font, max_width: int) -> list[str]` —— 纯函数，按字测量换行（便于单测）；`\n` 强制换行

- [ ] **Step 1: 写失败测试**

`tests/test_text.py`：

```python
from PIL import Image, ImageFont

from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.text import draw_description, draw_name, layout_lines


def canvas():
    return Image.new("RGBA", (512, 512), (0, 0, 0, 0))


def test_layout_lines_wraps(assets_dir):
    lib = AssetLibrary(assets_dir)
    font = lib.font("desc", 22)
    lines = layout_lines("这是一段很长很长的描述文本用来测试自动换行功能是否正常", font, 120)
    assert len(lines) >= 3
    for line in lines:
        assert font.getlength(line) <= 120 + 1


def test_layout_lines_explicit_newline(assets_dir):
    lib = AssetLibrary(assets_dir)
    font = lib.font("desc", 22)
    assert layout_lines("甲\n乙", font, 9999) == ["甲", "乙"]


def test_draw_name_fits_and_renders(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = draw_name(canvas(), lib, "测试卡名")
    assert sum(1 for p in img.getdata() if p[3] > 0) > 50


def test_draw_name_shrinks_long_name(assets_dir):
    lib = AssetLibrary(assets_dir)
    img = draw_name(canvas(), lib, "这是一个非常非常非常长的卡名")
    assert sum(1 for p in img.getdata() if p[3] > 0) > 50  # 不抛异常、有像素


def test_draw_description_autofit(assets_dir):
    lib = AssetLibrary(assets_dir)
    long_text = "造成3点伤害。" * 30
    img = draw_description(canvas(), lib, long_text)
    assert sum(1 for p in img.getdata() if p[3] > 0) > 100
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_text.py -q`
Expected: FAIL（`ModuleNotFoundError: bwpdiy.render.text`）

- [ ] **Step 3: 实现 text.py**

`bwpdiy/render/text.py`：

```python
"""文本层：卡名与描述文本的自动排版（从大到小试字号、自动换行、逐行居中）。"""

from PIL import Image, ImageDraw, ImageFont

from bwpdiy.render import layout
from bwpdiy.render.assets import AssetLibrary


def layout_lines(text: str, font: ImageFont.FreeTypeFont,
                 max_width: int) -> list[str]:
    """逐字符贪心换行；\\n 强制换行。"""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        current = ""
        for ch in paragraph:
            if current and font.getlength(current + ch) > max_width:
                lines.append(current)
                current = ch
            else:
                current += ch
        lines.append(current)
    return lines


def _fit(box: tuple[int, int, int, int], kind: str,
         font_range: tuple[int, int], lib: AssetLibrary,
         wrap: bool, text: str):
    """从大到小试字号，返回 (font, lines)。wrap=False 时不换行（卡名）。"""
    x0, y0, x1, y1 = box
    max_w, max_h = x1 - x0, y1 - y0
    max_size, min_size = font_range
    for size in range(max_size, min_size - 1, -1):
        font = lib.font(kind, size)
        lines = layout_lines(text, font, max_w) if wrap else [text]
        line_h = font.getbbox("国Ag")[3] - font.getbbox("国Ag")[1] + 4
        if wrap and line_h * len(lines) > max_h:
            continue
        if not wrap and font.getlength(text) > max_w:
            continue
        return font, lines
    font = lib.font(kind, min_size)
    lines = layout_lines(text, font, max_w) if wrap else [text]
    return font, lines


def _draw_lines(canvas: Image.Image, box, font, lines, fill) -> Image.Image:
    out = canvas.copy()
    draw = ImageDraw.Draw(out)
    x0, y0, x1, y1 = box
    line_h = font.getbbox("国Ag")[3] - font.getbbox("国Ag")[1] + 4
    total_h = line_h * len(lines)
    y = y0 + (y1 - y0 - total_h) / 2
    for line in lines:
        draw.text(((x0 + x1) / 2, y + line_h / 2), line, font=font,
                  anchor="mm", fill=fill)
        y += line_h
    return out


def draw_name(canvas: Image.Image, lib: AssetLibrary, name: str) -> Image.Image:
    font, lines = _fit(layout.NAME_BOX, "name", layout.NAME_FONT_RANGE,
                       lib, wrap=False, text=name)
    return _draw_lines(canvas, layout.NAME_BOX, font, lines, layout.TEXT_FILL)


def draw_description(canvas: Image.Image, lib: AssetLibrary,
                     text: str) -> Image.Image:
    font, lines = _fit(layout.DESC_BOX, "desc", layout.DESC_FONT_RANGE,
                       lib, wrap=True, text=text)
    return _draw_lines(canvas, layout.DESC_BOX, font, lines, layout.TEXT_FILL)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_text.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add bwpdiy/render/text.py tests/test_text.py
git commit -m "feat(render): 卡名/描述纯文本自动排版（试字号+贪心换行+逐行居中）"
git push
```

---

### Task 5: 管线总装（pipeline.py）

**Files:**
- Modify: `bwpdiy/render/pipeline.py`（改写现有骨架，保留 `render_card(card, assets_dir)` 签名与 `CARD_SIZE`）
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: 前 4 个任务全部接口
- Produces:
  - `render_card(card: dict, assets_dir: Path) -> Image.Image`（512×512 RGBA）
  - card dict 契约（M1 渲染字段；缺省规则同 Global Constraints）：
    - 必需：`type`（六类型之一）、`name`
    - 可选：`description`、`level`（缺省跳过等级标）、`evolve`（默认 False）、`rarity`、`faction`（中文派系名）、`power`/`health`（式神、形态）、`power+`/`shield+`（战斗加成，键名直接如此）、`durability`（幻境）、`artwork.images[0].{path,offset_x,offset_y,scale}`
    - `_base_dir`（可选 str/Path）：artwork 相对路径的解析基准，缺省为 cwd；M2 store 层注入
  - 模块常量：`TYPE_FRAME_CODE`、`FACTION_COLOR`

- [ ] **Step 1: 写失败测试**

`tests/test_pipeline.py`：

```python
import pytest

from bwpdiy.render import render_card


def make_card(fixtures, type_, **kw):
    card = {
        "type": type_,
        "name": "测试卡",
        "description": "测试描述文本。",
        "_base_dir": str(fixtures),
        "artwork": {"images": [{"path": "sample_art.png"}]},
    }
    card.update(kw)
    return card


@pytest.mark.parametrize("kw", [
    {"type": "式神", "faction": "红莲", "power": 3, "health": 4},
    {"type": "战斗", "level": 1, "rarity": "R", "power+": 1, "shield+": 1},
    {"type": "法术", "level": 2, "rarity": "SR", "evolve": True},
    {"type": "形态", "level": 3, "rarity": "SSR", "power": 2, "health": 2},
    {"type": "幻境", "rarity": "N", "durability": 6},
    {"type": "协战", "rarity": "R"},
])
def test_render_all_types(assets_dir, sample_art, kw):
    card = make_card(sample_art.parent, kw.pop("type"), **kw)
    img = render_card(card, assets_dir)
    assert img.size == (512, 512) and img.mode == "RGBA"


def test_render_minimal_card(assets_dir, sample_art):
    # artwork 缺省 path → <name>.png 不存在时应抛 FileNotFoundError 而非其他异常
    card = {"type": "法术", "name": "sample_art", "_base_dir": str(sample_art.parent)}
    img = render_card(card, assets_dir)
    assert img.size == (512, 512)


def test_render_missing_artwork_raises(assets_dir):
    card = {"type": "法术", "name": "不存在", "artwork": {"images": [{"path": "nope.png"}]}}
    with pytest.raises(FileNotFoundError):
        render_card(card, assets_dir)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_pipeline.py -q`
Expected: FAIL（`NotImplementedError: M1 待实现`）

- [ ] **Step 3: 实现 pipeline.py**

`bwpdiy/render/pipeline.py`（整体替换）：

```python
"""卡面渲染管线总装。

合成顺序（自底向上，术语见 docs/terminology.md）：
牌框 frame → 卡图 artwork（蒙版裁切）→ 等级标 → 稀有度标 → 派系标 →
数值标 → 卡名 → 描述文本。
一期固定：版型 low、框品 norm、等级数字 brown。
"""

from pathlib import Path

from PIL import Image

from bwpdiy.render import layout
from bwpdiy.render.artwork import apply_mask, fit_artwork
from bwpdiy.render.assets import AssetLibrary
from bwpdiy.render.badges import (add_faction, add_level_badge, add_rarity,
                                  add_stats)
from bwpdiy.render.text import draw_description, draw_name

CARD_SIZE = (512, 512)

TYPE_FRAME_CODE = {
    "式神": "xt",   # 式神卡外观形状同形态牌
    "形态": "xt",
    "战斗": "zd",
    "法术": "fs",
    "幻境": "hj",
    "协战": "xz",
}

FACTION_COLOR = {
    "红莲": "red",
    "苍叶": "green",
    "青岚": "blue",
    "紫岩": "purple",
    # 无相：无派系标，跳过
}

_STAT_KEYS = ("power", "health", "power+", "shield+", "durability")


def _artwork_ref(card: dict) -> dict:
    images = card.get("artwork", {}).get("images") or [{}]
    ref = dict(images[0])
    ref.setdefault("path", f"{card.get('id', card['name'])}.png")
    ref.setdefault("offset_x", 0)
    ref.setdefault("offset_y", 0)
    ref.setdefault("scale", 1.0)
    return ref


def render_card(card: dict, assets_dir: Path) -> Image.Image:
    """渲染单张完整卡面，返回 512×512 RGBA Image。

    缺资源/缺字段抛明确异常（FileNotFoundError/KeyError/ValueError），调用方兜底。
    """
    card_type = card["type"]
    if card_type not in TYPE_FRAME_CODE:
        raise ValueError(f"未知卡牌类型: {card_type}")
    code = TYPE_FRAME_CODE[card_type]
    lib = AssetLibrary(assets_dir)

    frame = lib.frame(code)  # 一期固定 norm/low
    ref = _artwork_ref(card)
    art_path = Path(ref["path"])
    if not art_path.is_absolute():
        art_path = Path(card.get("_base_dir", ".")) / art_path
    if not art_path.is_file():
        raise FileNotFoundError(f"卡图缺失: {art_path}")
    art = Image.open(art_path).convert("RGBA")
    art = fit_artwork(art, CARD_SIZE, ref["offset_x"], ref["offset_y"], ref["scale"])
    art = apply_mask(art, lib.mask(code))
    canvas = Image.alpha_composite(frame, art)

    if card.get("level") is not None:
        canvas = add_level_badge(canvas, lib, card["level"],
                                 evolve=card.get("evolve", False))
    if card.get("rarity"):
        canvas = add_rarity(canvas, lib, card["rarity"])
    faction = card.get("faction")
    if faction and faction in FACTION_COLOR:
        canvas = add_faction(canvas, lib, FACTION_COLOR[faction])
    stats = [(k, card[k]) for k in _STAT_KEYS if k in card]
    if stats:
        canvas = add_stats(canvas, lib, stats)

    canvas = draw_name(canvas, lib, card["name"])
    if card.get("description"):
        canvas = draw_description(canvas, lib, card["description"])
    return canvas
```

- [ ] **Step 4: 跑测试确认通过**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_pipeline.py -q`
Expected: 8 passed

- [ ] **Step 5: 全量测试**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全绿（约 27 个用例）

- [ ] **Step 6: Commit**

```bash
git add bwpdiy/render/pipeline.py tests/test_pipeline.py
git commit -m "feat(render): 管线总装 render_card——六类型卡面合成与字段缺省规则"
git push
```

---

### Task 6: CLI 示例渲染 + 用户视觉复查

**Files:**
- Create: `bwpdiy/render/__main__.py`
- Create: `examples/`（gitignore 之外的样例输出目录，仅本地；输出 PNG 不入库）
- Modify: `.gitignore`（加 `examples/`）
- Test: 无新增（复用 Task 5 全量）

**Interfaces:**
- Consumes: `render_card`（Task 5）
- Produces: `python -m bwpdiy.render CARD.json [--assets DIR] [--out PATH]` CLI；CARD.json 为 card dict（`_base_dir` 缺省设为 json 所在目录）

- [ ] **Step 1: 实现 __main__.py**

`bwpdiy/render/__main__.py`：

```python
"""CLI：渲染单张卡面 PNG。用法：python -m bwpdiy.render card.json [--assets assets] [--out out.png]"""

import argparse
import json
import sys
from pathlib import Path

from bwpdiy.render.pipeline import render_card


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m bwpdiy.render")
    ap.add_argument("card", help="卡牌 dict 的 json 文件")
    ap.add_argument("--assets", default="assets", help="美术资源目录")
    ap.add_argument("--out", default=None, help="输出 png 路径（默认 examples/<name>.png）")
    args = ap.parse_args()

    card_path = Path(args.card)
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card.setdefault("_base_dir", str(card_path.parent))
    out = Path(args.out) if args.out else Path("examples") / f"{card['name']}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        img = render_card(card, Path(args.assets))
    except (FileNotFoundError, KeyError, ValueError) as e:
        print(f"渲染失败: {e}", file=sys.stderr)
        return 1
    img.save(out)
    print(f"已输出: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`.gitignore` 追加一行：`examples/`。

- [ ] **Step 2: 造六类型示例卡 json 并渲染**

在 `examples/` 下写 6 个 json（式神/战斗/法术觉醒/形态/幻境/协战，字段同 Task 5 测试参数，`_base_dir` 指向 `tests/fixtures`，artwork path 为 `sample_art.png` 的相对路径——用 `{"_base_dir": "../tests/fixtures", "artwork": {"images": [{"path": "sample_art.png"}]}}`），逐个运行：

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m bwpdiy.render examples/card_shikigami.json
# ……共 6 张
```

Expected: 6 张 PNG 输出到 `examples/`，无报错。

- [ ] **Step 3: 视觉复查（用户参与）**

用 ReadMediaFile 逐张查看 6 张样卡，检查：卡图是否落入蒙版区、等级标/稀有度/派系/数值标位置是否压字/出框、卡名与描述是否居中文本区、字号是否合适。把样卡展示给用户过目，按反馈调整 `layout.py` 常量（仅调常量，不改逻辑），每轮调整后重渲染确认。

- [ ] **Step 4: 全量测试 + Commit**

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q
git add bwpdiy/render/__main__.py .gitignore bwpdiy/render/layout.py
git commit -m "feat(render): CLI 单卡渲染入口；layout 坐标视觉复查定稿"
git push
```

---

## Self-Review 记录

- **Spec 覆盖**：设计文档 §4 渲染管线四步 → Task 2/3/4/5；§4 主入口签名 → Task 5 保持不变；§10 M1「命令行渲染一张示例卡」→ Task 6。骨架/assets 迁移在设计批准前已完成，不在本计划。schema 校验属 M2（store 层），本计划 renderer 只做缺省值处理与明确异常，符合 spec §3「render 层拿到校验后的 dict」。
- **占位符扫描**：无 TBD/TODO；所有代码块完整。Task 6 Step 3 的坐标调整以常量表形式存在，属既定工作流而非占位。
- **类型一致性**：`AssetLibrary` 方法名在 Task 3/4/5 一致（`.frame/.mask/.level_*/.rarity/.faction/.icon/.font`）；`paste_centered` 签名一致；`layout` 常量名在 Task 3 定义、Task 4/5 引用一致；`render_card(card, assets_dir)` 签名与骨架/`bwpdiy/render/__init__.py` 导出一致。
- **已知留白（显式记录，非占位）**：`assets.py` 的 `icon()` 一期无人调用（为二期 #图标预留），若精简复查认为多余可删；layout 坐标初值以 Task 6 用户复查为准。
