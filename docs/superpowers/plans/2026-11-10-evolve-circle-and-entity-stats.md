# 觉醒圆盘层与对局小卡战力图标修正 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 大卡觉醒等级组件增加旧素材中央圆盘层，对局小卡战力/乏力改用 stats 大图标。

**Architecture:** PSD 导入脚本生成保留原 99×99 配准画布的圆盘层，等级组件用独立资源按底座→新星→圆盘→勾玉合成。对局小卡仅切换战力/乏力资源入口，文本内嵌图标保持原路径。

**Tech Stack:** Python 3、Pillow、pytest；无新增依赖。

## Global Constraints

- 圆盘来源仅为 `assets/psd_export/勾玉/底框-觉醒.png`，生成 `assets/levels/evolve_circle.png`。
- 保留 99×99 原画布配准，圆盘跟随 `star_offset` 与 `star_size`；不新增布局字段或 GUI 控件。
- 仅 `level` 存在且 `evolve=true` 时绘制新星与圆盘；勾玉最后绘制。
- 小卡战力/乏力读取 `stats/`，描述文本 `#zl`/`#fl` 仍读取 `icons/`。
- 不修改 `bwpdiy/render/default_layout.json`，不改版本号，不打包发布。
- 测试命令使用 Windows Git Bash 与项目 `.venv/Scripts/python.exe`；每次 commit 后 push。

---

### Task 1: 可重复生成的觉醒圆盘与等级组件分层

**Files:**
- Modify: `scripts/import_psd_assets.py`
- Modify: `bwpdiy/render/assets.py`
- Modify: `bwpdiy/render/badges.py`
- Create: `assets/levels/evolve_circle.png`
- Test: `tests/test_assets.py`
- Test: `tests/test_badges.py`

**Interfaces:**
- Produces: `AssetLibrary.level_evolve_circle() -> Image.Image`，读取 `levels/evolve_circle.png`。
- Produces: `_paste_element(..., trim=True)` 新增可选关键字；仅圆盘传 `trim=False`，既有调用保持逐像素不变。
- Produces: 导入脚本 `import_levels(out: Path | None = None)`；缺省写 `assets/levels/`，测试可写临时目录。

- [ ] **Step 1: 写资源生成与加载失败测试**

在 `tests/test_assets.py` 增加：

```python
def test_evolve_circle_import_is_repeatable_and_preserves_registration(assets_dir, tmp_path):
    from scripts.import_psd_assets import import_levels
    source = assets_dir / "psd_export/勾玉/底框-觉醒.png"
    with Image.open(source) as img:
        source_size = img.size
    import_levels(tmp_path)
    target = tmp_path / "evolve_circle.png"
    first = target.read_bytes()
    import_levels(tmp_path)
    assert target.read_bytes() == first
    with Image.open(target) as img:
        assert img.mode == "RGBA" and img.size == source_size
        assert img.getpixel((0, 0))[3] == 0
        assert img.getpixel((img.width // 2, img.height // 2))[3] > 0
    assert not (tmp_path / "evolve.png").exists()
    assert AssetLibrary(assets_dir).level_evolve_circle().mode == "RGBA"
```

文件顶部按需导入 `Image`；既有 `AssetLibrary` 导入直接复用。

- [ ] **Step 2: 写等级组件顺序与偏移失败测试**

在 `tests/test_badges.py` 增加资源调用顺序测试：用 `monkeypatch` 将 `level_base`、`level_star`、`level_evolve_circle`、`level_num` 分别替换为返回带 `info["layer"]` 的 2×2 RGBA 图，再替换 `badges._paste_element` 记录 `(layer, pos, size, trim)` 并原样返回画布。

```python
def test_evolve_circle_layers_between_star_and_level(assets_dir, monkeypatch):
    import bwpdiy.render.badges as badges
    lib = AssetLibrary(assets_dir)

    def layer(name):
        img = Image.new("RGBA", (2, 2), (255, 255, 255, 255))
        img.info["layer"] = name
        return img

    monkeypatch.setattr(lib, "level_base", lambda: layer("base"))
    monkeypatch.setattr(lib, "level_star", lambda: layer("star"))
    monkeypatch.setattr(lib, "level_evolve_circle", lambda: layer("circle"))
    monkeypatch.setattr(lib, "level_num", lambda n, color="yellow": layer("level"))
    calls = []

    def record(canvas, img, pos, size, composite=False, trim=True):
        calls.append((img.info["layer"], pos, size, trim))
        return canvas

    monkeypatch.setattr(badges, "_paste_element", record)
    elem = {"kind": "level_badge", "pos": [120, 65], "base_size": 72,
            "star_size": 60, "star_offset": [-3, 5], "num_size": 40}
    render_element(canvas(), lib, "level", elem, {"level": 2, "evolve": True})
    assert [call[0] for call in calls] == ["base", "star", "circle", "level"]
    assert calls[1][1] == calls[2][1] == (117, 70)
    assert calls[1][2] == calls[2][2] == (60, 60)
    assert calls[2][3] is False
```

另断言相同调用在 `{"level": 2, "evolve": False}` 与 `{"evolve": True}` 下均不出现 `circle`。

- [ ] **Step 3: 运行测试并确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_assets.py tests/test_badges.py -k "evolve_circle" -q`
Expected: FAIL，原因是圆盘生成函数、资源入口和分层尚不存在。

- [ ] **Step 4: 实现圆盘资产生成**

在导入脚本使用中央圆形遮罩，初始提取框为源图 `(21, 21, 78, 78)`；在 4 倍尺寸绘制椭圆遮罩后以 LANCZOS 降回 99×99，并与原 alpha 相乘。结果写回同尺寸透明画布，以保留与新星叠加时的固有比例：

```python
def extract_evolve_circle(source: Path, target: Path) -> None:
    with Image.open(source) as opened:
        src = opened.convert("RGBA")
    scale = 4
    mask = Image.new("L", (src.width * scale, src.height * scale), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse(tuple(v * scale for v in (21, 21, 78, 78)), fill=255)
    mask = mask.resize(src.size, Image.LANCZOS)
    src.putalpha(ImageChops.multiply(src.getchannel("A"), mask))
    src.save(target)
```

文件顶部集中导入 `ImageChops`、`ImageDraw`。`LEVELS` 删除旧 `底框-觉醒.png → evolve.png` 映射，避免重导入覆盖新版新星；`import_levels(out=None)` 复制其余 LEVELS 后调用 `extract_evolve_circle(PSD / "勾玉/底框-觉醒.png", out / "evolve_circle.png")`，日志追加 `levels/evolve_circle.png`。

运行一次脚本生成正式资源，并查看圆盘边缘；若星角仍有残留，只调整上述中央提取框，不增加运行时布局项。

- [ ] **Step 5: 实现资源入口与分层绘制**

```python
# assets.py
def level_evolve_circle(self) -> Image.Image:
    return self._img("levels/evolve_circle.png")

# badges.py：仅在裁剪处使用新参数
def _paste_element(..., composite: bool = False, trim: bool = True):
    bbox = img.getchannel("A").getbbox() if trim else None
    if bbox:
        img = img.crop(bbox)
    # 后续缩放与居中逻辑不变
```

觉醒分支先按原逻辑绘制新星，再以相同 `star_pos` 和 `(star_size, star_size)` 绘制 `lib.level_evolve_circle()`，圆盘调用传 `trim=False`；随后由原代码绘制等级勾玉。

- [ ] **Step 6: 验证资源与等级组件**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_assets.py tests/test_badges.py -q`
Expected: PASS。

用 `SAMPLE_CARDS["法术"]` 实际渲染觉醒大卡，并用 ReadMediaFile 检查圆盘位于新星中央、勾玉清晰且边缘无星角残留。

- [ ] **Step 7: 提交本任务**

```bash
git add scripts/import_psd_assets.py bwpdiy/render/assets.py bwpdiy/render/badges.py assets/levels/evolve_circle.png tests/test_assets.py tests/test_badges.py
git commit -m "feat(等级标): 叠加旧版觉醒圆盘层"
git push
```

### Task 2: 小卡战力大图标与文档收尾

**Files:**
- Modify: `bwpdiy/render/entity.py`
- Test: `tests/test_entity_render.py`
- Modify: `AGENTS.md`
- Modify: `docs/terminology.md`
- Modify: `docs/superpowers/specs/2026-09-14-bwpdiy-design.md`

**Interfaces:**
- Consumes: 既有 `AssetLibrary.stat_badge(name)` 与 `stats/combat_power.png`、`stats/weak.png`。
- Produces: `_stat_icon` 对 `combat_power` 正/负值均返回 stats 大图标；其他字段与文本解析接口不变。

- [ ] **Step 1: 改测试以钉死 stats 资源入口**

将 `test_entity_combat_power_picks_icon` 与乏力相关测试的监视对象从 `lib.icon` 改为 `lib.stat_badge`，分别断言 `combat_power` / `weak`，并同时 monkeypatch `lib.icon`：若小卡战力分支调用它则 `pytest.fail("对局小卡战力/乏力须使用 stats 大图标")`。保留 0 不绘制断言。

核心断言：

```python
combat_badges = [name for name in names if name in ("combat_power", "weak")]
assert combat_badges == ([expected] if expected else [])
```

- [ ] **Step 2: 运行测试并确认旧实现失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_entity_render.py -k "combat_power_picks_icon or combat_power_uses" -q`
Expected: 正/负战力用例 FAIL，因为旧实现只调用 `lib.icon`。

- [ ] **Step 3: 实现最小修复**

```python
def _stat_icon(lib: AssetLibrary, field: str, value: int) -> Image.Image:
    if field == "combat_power":
        return lib.stat_badge("combat_power" if value > 0 else "weak")
    if field == "shield":
        return lib.stat_badge("shield" if value > 0 else "combat_fragile_2")
    return lib.stat_badge(field)
```

- [ ] **Step 4: 运行小卡及渲染回归**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_entity_render.py tests/test_pipeline_components.py -q`
Expected: PASS。

分别渲染 `combat_power=2` 与 `combat_power=-2` 的小卡并用 ReadMediaFile 确认使用清晰大图标，0 不绘制。

- [ ] **Step 5: 同步文档与精简复查**

- `AGENTS.md`：等级资源补 `evolve_circle.png` 及四层顺序；对局小卡战力/乏力改用 `stats/`，不再写“仍用 icons 小图”。
- `docs/terminology.md`：等级标、对局式神和资源归档条目采用同一口径；说明圆盘保留原画布配准、跟随星标。
- 主设计文档：同步大卡等级组件与小卡资源目录。
- 检查本轮 diff，仅保留这两项目标所需代码与测试；不改默认布局、版本号或发布资产。

- [ ] **Step 6: 最终验证并提交**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest tests/test_assets.py tests/test_badges.py tests/test_entity_render.py tests/test_pipeline_components.py -q`
Run: `git diff --check`
Expected: 全部 PASS，diff 无空白错误。

```bash
git add bwpdiy/render/entity.py tests/test_entity_render.py AGENTS.md docs/terminology.md docs/superpowers/specs/2026-09-14-bwpdiy-design.md
git commit -m "fix(对局小卡): 战力乏力改用大图标"
git push
```
