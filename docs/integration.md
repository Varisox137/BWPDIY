# BWPro 集成 BWPDIY 渲染库

本文是与源码同步的集成契约。BWPro 应直接导入 `bwpdiy.render` 获取 PIL 图片，不需要启动 FastAPI/WebGUI，也不应通过 HTTP 调用编辑器进程。

## 1. 安装与依赖

要求 Python ≥ 3.12。BWPro 可选择 Python 包集成或源码树集成；两种方式都必须另行确认 `assets/` 资源路径。

### Python 包集成

在 BWPro 项目根目录执行（路径按实际位置调整）：

```bash
uv add --editable ../BWPDIY
```

editable 安装只解决 Python 导入，**不会自动解决 `assets/` 路径**。标准同级目录可由 BWPro 适配层推导资源根；worktree、非同级目录或便携部署必须显式配置 BWPro 的环境变量：

```bash
BWP_DIY_ROOT='D:/Programming/BWPDIY'
BWP_DIY_LIBRARY='D:/Programming/BWPro/library'
```

`BWP_DIY_ROOT` 指向包含 `bwpdiy/` 与 `assets/` 的仓库根；`BWP_DIY_LIBRARY` 指向 BWPro 使用的卡牌与机制配置库，不是美术资源目录。

基础安装只包含渲染所需的 Pillow；不会安装 PyYAML、FastAPI 或 Uvicorn。只有需要运行 BWPDIY 卡牌库和 WebGUI 时才使用：

```bash
uv add --editable "../BWPDIY[web]"
```

### 源码树集成

不安装包时，BWPro 适配层可将 `BWP_DIY_ROOT` 加入 `sys.path`，并以该根的 `assets/` 作为 `assets_dir`：

```python
import os
import sys
from pathlib import Path

root = Path(os.environ["BWP_DIY_ROOT"])
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
assets = root / "assets"

from bwpdiy.render import render_card, render_entity
```

无论采用哪种方式，渲染层都只加载 `bwpdiy.render`，不导入 store、FastAPI 或 WebGUI。BWPDIY 自身的开发环境直接执行 `uv sync`，开发依赖组已包含 Web、测试与构建依赖。

所有入口返回 `PIL.Image.Image`，调用方负责保存 PNG、转为字节或交给 GUI 使用。资源缺失、卡图缺失、非法字段和非法尺寸会抛出异常；库本身不会静默替换占位卡。

## 2. 资源与卡图路径

- `assets_dir`：BWPDIY 的 `assets/` 目录，含牌框、字体、图标等资源。开发版可用 `bwpdiy.resources.default_assets_dir()`；BWPro 集成时建议显式配置路径。
- 卡牌 `_base_dir`：用户卡图根目录。`artwork.images[0].path` 相对该目录解析，绝对路径也必须位于该目录内，否则抛出 `ValueError`。
- 未提供 `artwork.images[0].path` 时，回退为 `<id 或卡名>.png`。
- 当前渲染只消费 `artwork.images[0]`；多张异画的选择由调用方先完成，再把目标图片放到首项。
- `artwork` 变换：`offset_x/offset_y` 为图像相对画布的偏移，正值向右/向下；`scale > 0`；`rotate` 为绕图片中心的顺时针角度。

## 3. 完整大卡 `render_card`

```python
render_card(
    card: dict,
    assets_dir: Path,
    layout: dict | None = None,
    crop: bool = True,
    info: dict | None = None,
    width: int | None = None,
    height: int | None = None,
) -> Image.Image
```

最小示例：

```python
from pathlib import Path
from bwpdiy.render import render_card

assets = Path("D:/Programming/BWPDIY/assets")
images = Path("D:/work/bwpdiy-images")
card = {
    "type": "式神",
    "id": "900001",
    "name": "自定义式神",
    "level": 1,
    "rarity": "R",
    "power": 2,
    "health": 3,
    "description": "己方回合开始时，获得1#ll。",
    "_base_dir": str(images),
    "artwork": {"images": [{
        "path": "900001.png",
        "offset_x": 0,
        "offset_y": 0,
        "scale": 1.0,
        "rotate": 0,
    }]},
}

image = render_card(card, assets)
image.save("card.png")

# 按目标宽度原生重绘文字、图标、卡图和布局，不是先出图再 resize。
large = render_card(card, assets, width=image.width * 2)
large.save("card@2x.png")
```

卡牌主要字段：

- 通用：`type`、`name`、`description`、`level`、`rarity`、`frame_variant`、`special_type`、`version_date`。
- 类型：式神/战斗/法术/形态/幻境/协战；式神/形态使用 `power/health`，幻境使用 `durability`，战斗使用 `power+/shield+`，觉醒法术使用 `power+/health+`。
- 可选：`evolve`、`level_color`、各数值的 `<field>_color`、`footer`、`layout`。
- 协战：`shikigami1/shikigami2`、可选 `duo_frame`。由 WebGUI 注入的双头像内部键 `_duo` 属于高级集成数据，普通 BWPro 卡面调用无需提供。

`layout` 是**该卡类型与框品的单套有效布局**，不是完整布局字典。缺省时自动读取运行环境布局并合并卡内 `layout` 稀疏覆盖。需要手动构造时：

```python
from bwpdiy.render.layout import get_type_layout, load_layouts, merge_card_layout

layouts = load_layouts(assets)
base = get_type_layout(layouts, card["type"], card.get("frame_variant", "norm"))
effective = merge_card_layout(base, card.get("layout"))
image = render_card(card, assets, layout=effective)
```

默认 `crop=True` 返回透明边裁齐的大卡，高度通常为 512，宽度随框体与外扩元素变化；`crop=False` 返回内部工作画布。传入 `info={}` 时回填 `anchor_x` 和 `crop_origin`，主要用于编辑器坐标换算。

## 4. 对局式神小卡 `render_entity`

```python
render_entity(
    card: dict,
    state: dict,
    assets_dir: Path,
    layout: dict | None = None,
    crop: bool = True,
    info: dict | None = None,
    width: int | None = None,
    height: int | None = None,
) -> Image.Image
```

```python
from bwpdiy.render import render_entity

state = {
    "level": 2,
    "level_color": "yellow",
    "power": 3,
    "health": 4,
    "combat_power": 1,
    "shield": -2,          # 正值护甲、负值破甲；combat_power 正/负对应战力/乏力
    "art_scale": 1.0,     # 仅小卡卡图缩放；偏移沿用大卡 artwork，并修正到框内可见窗
    "power_color": "green",
    "health_color": "red",
}
entity = render_entity(card, state, assets, width=192)
entity.save("entity.png")
```

- 适用来源：式神、形态或任意 `evolve: true` 的卡牌；其他类型抛出 `ValueError`。
- `level` 为 0–3；0 只绘制底框和卡图，不绘制等级标及数值角标。
- `power/health` 必须非负；`combat_power/shield` 可为负。四个数值颜色均可选 `red/green/purple`，缺省白色。
- `layout` 使用布局字典的「对局式神」独立段；缺省读取包内默认段。小卡基础框为 96×144，外扩元素会扩大最终紧致边界。
- `entity_eligible(card)` 可预先判断来源是否支持；`validate_entity_state(state)` 可单独取得规范化状态。

## 5. 式神头像 `render_portrait`

```python
render_portrait(
    lib: AssetLibrary,
    elem: dict,
    art_ref: dict | None,
    faction: str | None,
    scale: float = 2,
    faction_style: int | None = None,
    with_frame: bool = True,
    width: int | None = None,
    height: int | None = None,
) -> Image.Image
```

头像入口使用协战双式神框的单槽位布局。`art_ref.path` 应是可读取的图片路径，集成时建议传绝对路径；缺图可传 `None`，得到空头像槽位。

```python
from bwpdiy.render.assets import get_library
from bwpdiy.render.duo import render_portrait
from bwpdiy.render.layout import load_layouts

lib = get_library(assets)
elem = load_layouts(assets)["协战"]["elements"]["duo_frame"]
art = {
    "path": str((images / "900001.png").resolve()),
    "offset_x": 0,
    "offset_y": 0,
    "scale": 1.0,
    "rotate": 0,
}
portrait = render_portrait(lib, elem, art, "红莲", faction_style=2)
portrait.save("portrait.png")

bare = render_portrait(lib, elem, art, "红莲", with_frame=False)
```

`with_frame=False` 只保留菱形裁剪头像，不绘制斜方框和派系标。默认输出为方形，尺寸由 `scale` 与布局共同决定。

## 6. 机制描述框 `render_mechanism`

```python
render_mechanism(
    mech: dict,
    assets_dir: Path,
    layout: dict | None = None,
    info: dict | None = None,
    chars_per_line: int | None = None,
    font_scale: float = 1.0,
) -> Image.Image
```

```python
from bwpdiy.render.mech import render_mechanism

mech = {
    "name": "自定义机制",
    "frame": "invocation",       # invocation / skill / seal
    "text": "[[唯一]]。\n己方回合开始时，获得1#ll。",
}
image = render_mechanism(mech, assets, chars_per_line=12)
image.save("mechanism.png")

scaled = render_mechanism(mech, assets, chars_per_line=12, font_scale=2)
```

机制框不使用大卡的 `width/height`：

- `chars_per_line` 为正整数，按每行字数决定文本宽和框宽；`None` 使用「机制」布局中的文本宽。
- `font_scale` 同步缩放名称/正文字号、文本区、框宽、横向偏移和框行高，保持每行字数，不缩放加护/蚀印角标。
- `badge` 仅 `seal` 框可用，取 `bless` 或 `eclipse`。
- `layout` 使用「机制」段；`info={}` 回填裁剪后文本块 `{text_x, text_top, text_width, text_height}`。

## 7. 尺寸、文本与异常约定

大卡、小卡和头像的 `width/height` 规则一致：

- 单参数按默认紧致输出比例推算另一维；双参数允许取整造成的 1px 比例误差，不一致抛出 `ValueError`。
- 必须是正整数，单边 ≤ 8192，总像素 ≤ 64,000,000。
- 按目标比例重新计算布局、字体、描边、图标、卡图和间距，最后只裁齐或补透明边，不重采样默认成品。

描述文本支持 `[[关键字]]` 高亮和 `#xx` 内嵌图标；未匹配的双括号按普通文本显示，未知图标代码会报错。卡图与中间缩放缓存有像素上限，防止异常输入造成过量内存分配。

常见异常：

- `ValueError`：未知类型、非法字段、非法尺寸、卡图路径越界、机制参数不合法。
- `FileNotFoundError`：美术资源或卡图不存在。
- Pillow 解码异常：图片损坏或格式不受支持。

BWPro 应在自身边界捕获并记录异常，再决定使用占位图或取消操作，不要把异常文本直接当作用户输入拼接到页面 HTML。调用方至少应检查：

- 日志包含渲染类型、卡牌/式神 id、资源根和异常堆栈；相同失败可做有界去重，但不能静默吞掉。
- 占位图只是显示策略，不代表渲染成功；预热、缓存状态和设置页不得把空图或占位图计为成功。
- 失败结果不得进入可跳过后续重试的成功清单，修复资源或配置后应自动参与下一次预热。
- `width/height` 在适配层校验为正整数，非法输入应记录并暴露原因，不能表现为无上下文的“无图”。

## 8. 缓存与资源更新

集成中有三层独立缓存，不能把它们视为同一个失效机制：

1. **BWPDIY 资源缓存**：`get_library(assets_dir)` 按资源根共享字体、牌框和卡图缓存。运行中替换美术资源后应重启 BWPro 进程；仅修改卡牌字典不需要重建 `AssetLibrary`，内部卡图缓存按路径和修改时间识别更新。
2. **BWPro 图片缓存**：大卡、小卡和头像的磁盘或 LRU 缓存由 BWPro 适配层负责。缓存身份应覆盖卡牌负载、有效布局、配置与资源指纹、渲染器版本和目标尺寸；图片推荐使用内容 SHA-256，避免同路径、同大小且保留 mtime 的替换产生旧图。
3. **BWPro 预热清单**：manifest 是“哪些静态结果可跳过”的成功记录，不是条目数量清单。只有实际得到非空图片的条目才能写入；失败条目必须保留下次重试所需的信息。

重启 BWPDIY 编辑器或仅看到图片 mtime 变化，并不保证后两层全部失效。BWPro 应主动计算内容摘要和配置/资源指纹，并确保失败结果可重试；清理其中一层也不代表其他层已清理。

## 9. 最小集成自检

以下示例不启动 WebGUI，使用一张临时卡图依次检查大卡、小卡、头像和机制框。路径按实际部署调整；在 BWPro 环境已能导入 `bwpdiy` 后执行：

```python
import logging
import tempfile
from pathlib import Path

from PIL import Image

from bwpdiy.render import render_card, render_entity
from bwpdiy.render.assets import get_library
from bwpdiy.render.duo import render_portrait
from bwpdiy.render.layout import load_layouts
from bwpdiy.render.mech import render_mechanism

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bwpro.integration")
assets = Path("D:/Programming/BWPDIY/assets")

with tempfile.TemporaryDirectory() as temp:
    images = Path(temp)
    art_path = images / "900001.png"
    Image.new("RGBA", (64, 64), "#336699").save(art_path)
    art = {
        "path": art_path.name,
        "offset_x": 0,
        "offset_y": 0,
        "scale": 1.0,
        "rotate": 0,
    }
    card_data = {
        "type": "式神",
        "id": "900001",
        "name": "集成自检",
        "level": 1,
        "rarity": "R",
        "power": 2,
        "health": 3,
        "description": "己方回合开始时，获得1#ll。",
        "_base_dir": str(images),
        "artwork": {"images": [art]},
    }
    state = {
        "level": 1,
        "level_color": "yellow",
        "power": 2,
        "health": 3,
        "combat_power": 0,
        "shield": 0,
        "art_scale": 1.0,
    }

    card = render_card(card_data, assets)
    entity = render_entity(card_data, state, assets)
    lib = get_library(assets)
    layouts = load_layouts(assets)
    elem = layouts["协战"]["elements"]["duo_frame"]
    portrait_art = dict(art, path=str(art_path.resolve()))
    portrait = render_portrait(lib, elem, portrait_art, "红莲", faction_style=2)
    mechanism = render_mechanism({
        "name": "集成自检",
        "frame": "invocation",
        "text": "[[唯一]]。\n己方回合开始时，获得1#ll。",
    }, assets, layout=layouts["机制"], chars_per_line=12)

    assert card.width > 0 and card.height > 0
    assert entity.width > 0 and entity.height > 0
    assert portrait.width > 0 and portrait.height > 0
    assert mechanism.width > 0 and mechanism.height > 0

    try:
        render_card(card_data, assets, width=0)
    except ValueError:
        log.exception("预期的非法尺寸异常：id=%s assets=%s", card_data["id"], assets)
    else:
        raise AssertionError("width=0 必须抛出 ValueError")

log.info("四类渲染与非法尺寸自检通过")
```

四项图片均非空且非法尺寸异常能被调用方日志定位，才说明安装、资源与基本调用链路可用。若任一失败，应保留完整堆栈并先检查 `BWP_DIY_ROOT`、`assets/` 和卡图根目录，不要把失败统一转换成空图后再继续预热。
