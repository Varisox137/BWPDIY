# 对局式神右上组件独立布局 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 将能量与倒计时拆成独立布局元素和互斥样例勾选框，并把永久气绝 `∞` 调整为参考图连续细线轮廓。

**Architecture:** 渲染状态契约不变，仅将布局元素 `right_top` 拆为 `energy/countdown`；旧配置加载时复制迁移。布局编辑器复用现有 counter 拖拽、数字锚点和右栏控件。

**Tech Stack:** Python 3.12+、Pillow、原生 JavaScript、pytest、Node.js 行为测试。

## Global Constraints

- 设计依据：`docs/superpowers/specs/2026-11-03-entity-counter-layout-design.md`。
- 开发版与正式版统一读写 `$HOME/.bwpdiy/layout.json`，删除 `assets/layout.json`；包内 `default_layout.json` 仅作缺省回退。
- 不改 `state` 字段，不破坏能量黄色、倒计时白色、气绝绘制顺序与 0 级规则。
- 不修改或提交用户现有 `assets/legacy/` 删除；不打包、不发布。
- 全量命令：`PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`；提交后推送。

---

### Task 1: 独立 counter 渲染、布局迁移与 ∞ 几何

**Files:**
- Modify: `bwpdiy/render/entity.py`、`bwpdiy/render/badges.py`、`bwpdiy/render/layout.py`、`bwpdiy/resources.py`
- Modify: `bwpdiy/render/default_layout.json`
- Delete: `assets/layout.json`
- Test: `tests/test_entity_render.py`、`tests/test_layout.py`、`tests/test_badges.py`、`tests/conftest.py`、`tests/test_web.py`

**Interfaces:**
- Produces: `elements.energy` 与 `elements.countdown`，均为既有 counter 形状。
- Consumes: 既有 `state.energy/countdown/defeated_countdown` 与 `_render_counter`。

- [x] **Step 1: 写失败测试**

在实体渲染测试中分别给 `energy/countdown` 不同 `pos`、`num_offset`、字号和图标尺寸，断言各自实际调用对应元素且数字独立；旧 `right_top` 不再作为渲染键。布局测试构造仅含旧 `right_top` 的版本 2 配置，断言加载后其参数复制到两个新元素、旧键移除，已有新元素优先。∞ 测试断言新轮廓比旧比例更窄更高，且仍有白墨与黑描边。

- [x] **Step 2: 运行测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_entity_render.py tests/test_layout.py tests/test_badges.py -k "counter or infinity or right_top"`

Expected: 因新元素尚未接入且 ∞ 仍为旧比例而失败。

- [x] **Step 3: 实现最小改动**

`_right_top_counter` 返回 `(字段名, 数值, 颜色)`，字段名直接为 `energy/countdown`；校验、边界准备和最终绘制按激活状态选择对应元素。布局加载在默认深补全前迁移旧 `right_top`。包内默认 JSON 用旧 `right_top` 参数生成两个独立元素。`_render_infinity` 按参考图改为连续交叉细线，主体尺寸为字号 ×0.65/×0.42。

- [x] **Step 4: 运行相关测试并提交**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_entity_render.py tests/test_layout.py tests/test_badges.py`

```bash
git add bwpdiy/render/entity.py bwpdiy/render/badges.py bwpdiy/render/layout.py assets/layout.json bwpdiy/render/default_layout.json tests/test_entity_render.py tests/test_layout.py tests/test_badges.py
git commit -m "feat(布局): 拆分能量与倒计时组件"
git push
```

---

### Task 2: 互斥样例勾选、独立编辑控件与文档验收

**Files:**
- Modify: `bwpdiy/web/static/editor-layout.js`、`bwpdiy/changelog.py`
- Modify: `AGENTS.md`、`docs/terminology.md`、`docs/integration.md`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: Task 1 的 `elements.energy/countdown`。
- Produces: 布局样例两个互斥勾选框，以及两个元素各自的位置、数字锚点和右栏参数。

- [x] **Step 1: 写前端失败测试**

用真实 `buildCardProps/buildLists/buildProps` 驱动断言：存在「能量」「倒计时」勾选框而无「右上组件」下拉；勾选其一会清空另一个状态，取消当前项则全关；两个数值输入分别写 `entityLayoutSample.energy/countdown`。元素列表和右栏均分别支持 energy/countdown，且计数组件不显示符号参数。

- [x] **Step 2: 运行测试确认失败**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_web.py -k "layout and (counter or energy or countdown)"`

Expected: 因仍使用 `right_top` 与下拉框而失败。

- [x] **Step 3: 实现界面并同步文档**

用两个 `battleCheckbox` 替代下拉，勾选互斥、取消即关闭；保留各组件数值输入。`DISP`、元素顺序、拖拽和右栏改用 energy/countdown。文档将 right_top 旧术语标为已迁移，changelog 在 1.8.0 补充独立布局与参考图连续细线 ∞；不新增版本号。

- [x] **Step 4: 全量验证与真实服务验收**

运行完整前端/渲染测试、全量 pytest、全部 JS `node --check` 和 `git diff --check`。隔离启动源码服务，生成能量、倒计时、气绝和永久气绝样图，确认独立参数生效且布局文件未被验收修改，随后正常关闭并清理临时文件。

- [x] **Step 5: 精简审查、提交并推送**

删除本批不再使用的 right_top 生产代码与重复测试，不删除迁移、校验、边界、并发或绘制顺序测试。仅暂存本任务文件：

```bash
git add bwpdiy/web/static/editor-layout.js bwpdiy/changelog.py AGENTS.md docs/terminology.md docs/integration.md docs/superpowers/plans/2026-11-03-entity-counter-layout.md tests/test_web.py
git commit -m "feat(界面): 支持右上组件独立调参"
git push
```
