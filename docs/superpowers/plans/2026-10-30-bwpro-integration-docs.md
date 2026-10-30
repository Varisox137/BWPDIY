# BWPro 集成文档优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完善 BWPDIY 集成契约，并在 BWPro 文档中留下可独立实施的适配层修复指南，不修改生产代码。

**Architecture:** BWPDIY `docs/integration.md` 继续作为真实渲染 API 的唯一集成契约；BWPro `docs/bwpdiy-integration.md` 作为后续适配层改造清单，引用当前代码位置并定义验收用例。审查报告与设计文档保留决策依据。

**Tech Stack:** Markdown、Python 3.12+、Pillow、pytest、真实 BWPDIY 美术资源。

## Global Constraints

- BWPDIY 只允许修改文档；BWPro 只允许新增 `docs/bwpdiy-integration.md`。
- 不修改生产代码、测试、布局、卡牌数据、`legacy/` 或 BWPro 用户未提交内容。
- 不改变 `render_card`、`render_entity`、`render_portrait`、`render_mechanism` 的签名与行为。
- 文档中的路径、字段和示例必须与当前源码一致；不引入依赖，不打包或发布。
- 两仓库分别使用中文 conventional commit，提交后推送。

---

### Task 1: 完善 BWPDIY 集成契约

**Files:**
- Modify: `docs/integration.md`
- Add existing review record: `docs/integration-bwpro-review.md`
- Reference: `bwpdiy/render/__init__.py`、`bwpdiy/render/duo.py`、`bwpdiy/render/mech.py`

**Interfaces:**
- Consumes: 当前四个渲染入口及 `assets_dir`、`_base_dir`、尺寸和布局契约。
- Produces: 包集成/源码树集成说明、三层缓存边界、失败处理清单和可执行最小自检。

- [ ] **Step 1: 重写安装与资源根说明**

将第 1 节拆成两种路径：editable 安装用于 Python 导入，源码树通过 `BWP_DIY_ROOT` 同时定位包与 `assets/`。明确 editable 不自动定位资源，worktree、非同级目录和便携部署必须显式设置：

```bash
BWP_DIY_ROOT='D:/Programming/BWPDIY'
BWP_DIY_LIBRARY='D:/Programming/BWPro/library'
```

保留基础依赖与 `web` extra 的现有说明，不添加安装新依赖的命令。

- [ ] **Step 2: 补充失败处理与三层缓存说明**

在第 7 节增加调用方检查项：记录渲染类型、实体 id、资源根与堆栈；占位图不算成功；预热失败不得进入成功清单；修复资源后可重试；尺寸先校验为正整数。

将第 8 节拆成：

1. BWPDIY `AssetLibrary` 的字体、牌框和图片缓存；
2. BWPro 大卡/小卡/头像的磁盘或 LRU 缓存；
3. BWPro 预热 manifest 成功清单。

说明内容 SHA-256、配置/资源指纹由 BWPro 适配层负责，重启 BWPDIY 编辑器或图片 mtime 变化不会自动清除 BWPro 后两层缓存。

- [ ] **Step 3: 增加最小集成自检**

新增第 9 节，复用本文现有示例构造一张大卡、对应小卡、一个头像和一个机制框，逐项断言：

```python
assert card.width > 0 and card.height > 0
assert entity.width > 0 and entity.height > 0
assert portrait.width > 0 and portrait.height > 0
assert mechanism.width > 0 and mechanism.height > 0
```

增加非法尺寸检查，并要求调用方记录异常而不是静默吞掉：

```python
import logging
try:
    render_card(card_data, assets, width=0)
except ValueError:
    logging.getLogger("bwpro.integration").exception(
        "大卡自检失败：id=%s assets=%s", card_data.get("id"), assets)
else:
    raise AssertionError("width=0 必须抛出 ValueError")
```

- [ ] **Step 4: 核对文档契约并执行真实自检**

对照源码检查四个函数签名和字段。使用 `D:/Programming/BWPDIY/assets` 与临时卡图实际执行四类渲染和 `width=0` 异常检查；自检输出写入临时目录，不写入仓库。

- [ ] **Step 5: 运行 BWPDIY 全量测试并提交**

Run: `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`
Expected: 全部通过。

```bash
git add docs/integration.md docs/integration-bwpro-review.md
git commit -m "docs(集成): 明确部署缓存与失败自检契约"
git push
```

---

### Task 2: 编写 BWPro 适配层调整指南

**Files:**
- Create: `D:/Programming/BWPro/docs/bwpdiy-integration.md`
- Reference: `client/gui/portrait.py`、`client/gui/cardart.py`、`client/gui/prewarm.py`、`client/gui/mechanisms.py`、`client/gui/settings.py`
- Reference tests: `tests/test_gui_builder.py`、`tests/test_gui_prewarm.py`、`tests/test_gui_mechanisms.py`

**Interfaces:**
- Consumes: Task 1 的集成契约和现有审查报告。
- Produces: BWPro 后续代码修改的优先级、推荐行为、兼容约束和回归测试清单。

- [ ] **Step 1: 记录高优先级修复**

按当前代码位置写明：

- `bwpdiy_root()`：环境变量优先，向上寻找同级 `BWPDIY/assets`，保留原路径回退；
- 渲染异常：记录类型、id、资源根与堆栈，有界去重，清缓存后允许重新记录；
- 预热：非空 `QPixmap` 才成功，失败不进入成功 `entries`，下次自动重试，manifest 记录 `succeeded/failed/skipped` 与失败原因；
- 设置页：显示三项统计和失败摘要，完整原因留在 manifest。

保持 `prewarm_all()` 返回全部期望条目，避免无关调用方变更。

- [ ] **Step 2: 记录中低优先级修复**

写明显式 `library_dir/cache_dir` 转发、`frame_variant` 同时进入负载和 `get_type_layout`、`badge` 进入机制负载与缓存键、头像使用内容 SHA-256。每项列出对应文件和预期行为，不粘贴大段实现代码。

- [ ] **Step 3: 定义后续回归测试与实施顺序**

为每项列出测试名称和核心断言：worktree 根目录、日志上下文与去重、非默认预热路径、失败重试、设置页统计、非常规框布局、badge 缓存区分、同 mtime/大小图片替换。要求先看到旧实现失败，再修改代码，最后运行相关 GUI 测试和全量：

```bash
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q
```

实施顺序为资源根/日志/预热，路径转发，框品与 badge，最后头像摘要。

- [ ] **Step 4: 核对范围并提交 BWPro 文档**

Run: `git diff --check -- docs/bwpdiy-integration.md`
Expected: 无空白错误；`git status` 中本任务只新增该文档，不暂存用户已有修改。

```bash
git add docs/bwpdiy-integration.md
git commit -m "docs(集成): 记录BWPDIY适配层调整指南"
git push
```

---

### Task 3: 最终交叉核对

**Files:**
- Verify: `D:/Programming/BWPDIY/docs/integration.md`
- Verify: `D:/Programming/BWPro/docs/bwpdiy-integration.md`

**Interfaces:**
- Consumes: 两个已提交文档。
- Produces: 文档一致性结论和两仓库状态。

- [ ] **Step 1: 交叉检查**

确认环境变量名、四类渲染名称、缓存责任、失败成功判定和尺寸规则一致；检查两份文档无占位内容、无要求本批次修改 BWPro 代码的表述。

- [ ] **Step 2: 汇报**

列出两仓库提交、真实自检结果和 BWPDIY 测试数；明确 BWPro 代码与测试未修改，未打包或发布。
