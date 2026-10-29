# 机制框默认宽度与每行字数 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 三类机制框默认宽缩至 312px，公开渲染参数改为每行字数，并允许每个机制条目独立保存该值；最终重新发布 v1.7.6。

**Architecture:** 布局默认值仍使用像素文本宽，`render_mechanism` 在未传字数时沿用布局，显式 `chars_per_line` 才覆盖布局。条目预览/导出对缺失字段回退 12；`font_scale` 同步缩放横向布局与文字，保持每行字数。

**Tech Stack:** Python 3.13、Pillow、FastAPI、JavaScript、pytest、PyInstaller、GitHub CLI。

## Global Constraints

- 版本保持 `1.7.6`。
- 出厂默认 `chars_per_line=12`、`text_x=12`、文本宽 288px、框宽 312px。
- 不再接受像素 `width` 参数；字数为正整数，缺失时按布局值。
- `font_scale` 改变文字、文本区/框宽/横向偏移与行高，不改变实际每行字数和角标尺寸。
- 不改写 `$HOME/.bwpdiy/layout.json`；打包只以其非机制配置为基底。
- 全量测试通过后才提交、构建和发布。

---

### Task 1: 默认布局与字数渲染

**Files:**
- Modify: `bwpdiy/render/mech.py`
- Modify: `assets/layout.json`
- Modify: `bwpdiy/render/default_layout.json`
- Test: `tests/test_mech_render.py`

**Interfaces:**
- Produces: `render_mechanism(..., chars_per_line: int | None = None, font_scale: float = 1.0)`。

- [ ] 先把默认框宽断言改为 312px、默认左缘改为 12px，并新增 10/11/12/13 字、原生最小框宽、倍率保持字数及非法参数用例，确认旧实现失败。
- [ ] 将内置和出厂三类框默认 `text_x` 改为 12、文本宽保持 288；以 `chars_per_line × text_size` 计算文本宽，框宽不小于素材原宽。
- [ ] 让 `font_scale` 同步缩放文本区、框宽和横向偏移，并用缩放后的实际字号计算换行宽，保证字数不变。
- [ ] 运行 `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_mech_render.py`，确认全部通过。

### Task 2: 条目字段、GUI 与文档

**Files:**
- Modify: `bwpdiy/store/schema.py`
- Modify: `bwpdiy/web/app.py`
- Modify: `bwpdiy/web/static/editor.html`
- Modify: `bwpdiy/changelog.py`
- Modify: `AGENTS.md`
- Modify: `docs/terminology.md`
- Modify: `docs/superpowers/specs/2026-10-29-mechanism-default-width-design.md`
- Test: `tests/test_store.py`
- Test: `tests/test_web.py`
- Test: `tests/test_web_projects.py`

**Interfaces:**
- Consumes: 机制 yaml 可选 `chars_per_line` 正整数，缺失回退 12。
- Produces: 右栏「每行字数」数字输入；保存、预览、导出使用当前条目值。

- [ ] 先新增 schema 接受/拒绝、条目保存后预览、未保存覆盖预览和 JS 校验测试，确认旧实现失败。
- [ ] 将字段加入机制白名单并校验正整数；条目预览调用 `render_mechanism` 时传入 `mech.get("chars_per_line", 12)`。
- [ ] 右栏增加最小值 1 的整数输入，新建机制写入 12；即时预览、保存与导出沿用现有表单数据流。
- [ ] 同步术语、项目约定、设计说明与 v1.7.6 更新说明，保留加粗出厂布局变更提示。
- [ ] 运行 `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`，全部通过后中文 conventional commit 并 `git push`。

### Task 3: 打包与覆盖发布

**Files:**
- Generate: `releases/BWPDIY-v1.7.6.exe`
- Generate temporarily: `releases/BWPDIY-v1.7.6.exe.sha256`

**Interfaces:**
- Produces: GitHub Release `v1.7.6` 的同名替换资产。

- [ ] 读取正式版布局，仅在内存中把三类机制 `text_x` 改为 12、`width` 改为 288；临时注入两个打包配置源，构建后在 `finally` 中恢复工作区文件，不写回用户布局。
- [ ] 用 `CArchiveReader` 核对包内配置，隔离 HOME 启动 exe，核对版本及规范化布局后结束验证进程。
- [ ] 执行 `gh release upload v1.7.6 releases/BWPDIY-v1.7.6.exe releases/BWPDIY-v1.7.6.exe.sha256 --clobber`，核对远程大小、SHA256 和 Latest。
- [ ] 删除本地 sha256、`build/`、`dist/`、`.smoke/` 与验证进程，保留 v1.7.6 exe。
