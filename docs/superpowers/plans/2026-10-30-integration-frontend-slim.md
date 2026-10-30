# BWPDIY 集成文档、前端拆分与低风险精简实施计划

> **For agentic workers:** 本计划由主上下文内联执行；每一步保持现有功能，先验证相关测试，最后运行全量测试。

**Goal:** 补齐 BWPro 渲染集成契约，拆分单体前端并减少依赖和重复维护点，同时保持 v1.7.7 的功能与输出不变。

**Architecture:** 渲染仍只由 `bwpdiy.render` 暴露纯 PIL 能力；WebGUI 使用按依赖顺序加载的经典 JS，不引入框架或构建步骤。打包继续收集整个静态目录，Web 专属 Python 包改为可选依赖。

**Tech Stack:** Python 3.12、Pillow、FastAPI/Uvicorn（Web 可选）、vanilla HTML/CSS/JS、pytest、Node（已有前端行为测试）。

## Global Constraints

- 不改变版本号，不打包、不发布 Release；完成后中文 conventional commit 并 push。
- 不改变渲染像素、API 请求/响应、前端状态管理和持久化格式。
- 不精简文本/schema/路径/并发/跨站校验、缓存一致性或结算时序测试。
- `legacy/`、PSD 与归档素材保持不动；本地 `releases/` 仅保留最近 5 个二级版本各自的最新 exe，GitHub 历史 Release 不受影响。

---

### Task 1: 固定本地 Release 保留规则

**Files:**
- Modify: `scripts/build_exe.py`
- Test: `tests/test_main.py`
- Modify: `AGENTS.md`

- [x] 添加临时目录测试，构造多个三级版本，断言每个二级版本只留最新包且总共只留最近五个二级版本。
- [x] 运行该测试并确认因 `_prune_releases` 尚不存在而失败。
- [x] 实现纯路径/版本号处理的 `_prune_releases`，在构建复制 exe 后调用；不匹配命名和 `.sha256` 文件不由该函数处理。
- [x] 重跑测试并核对当前 `releases/` 只含 1.3、1.4、1.5、1.6、1.7 五个 exe。

### Task 2: 消除实体默认布局与 PNG 响应重复

**Files:**
- Modify: `bwpdiy/render/entity.py`
- Modify: `bwpdiy/web/app.py`
- Test: `tests/test_layout.py`、`tests/test_web.py`

- [x] 用包内 `default_layout.json` 的「对局式神」段初始化 `_DEFAULT_LAYOUT`，删除手抄常量，保持字典结构不变。
- [x] 增加模块级 `_png_response(img, headers=None)`，替换六处相同 PNG 编码响应，不改变媒体类型和自定义响应头。
- [x] 运行布局同步、实体渲染与 Web 预览测试，确认输出和响应不变。

### Task 3: 将 Web 依赖改为可选安装

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`
- Modify: `README.md`
- Test: `tests/test_main.py`

- [x] 添加 `tomllib` 测试：基础依赖只有 Pillow；`web` extra 含 PyYAML/FastAPI/Uvicorn；开发组仍含完整测试与 Web 运行依赖。
- [x] 运行测试并确认当前依赖声明不符合目标。
- [x] 调整依赖声明并执行 `uv lock`；用 `uv sync --dry-run` 和 `uv lock --check` 核对锁文件。
- [x] 验证仅导入 `bwpdiy.render` 不导入 FastAPI/YAML，完整 Web 测试在当前开发环境不受影响。

### Task 4: 无行为拆分前端

**Files:**
- Create: `bwpdiy/web/static/editor.css`
- Create: `bwpdiy/web/static/editor-core.js`
- Create: `bwpdiy/web/static/editor-cards.js`
- Create: `bwpdiy/web/static/editor-mech.js`
- Create: `bwpdiy/web/static/editor-layout.js`
- Create: `bwpdiy/web/static/editor-main.js`
- Modify: `bwpdiy/web/static/editor.html`
- Test: `tests/test_web.py`

- [x] 先修改 `_script()`：解析 HTML 中顺序排列的 `<script src>`，读取并拼接真实静态脚本；添加 CSS/脚本引用顺序与文件存在性断言。
- [x] 运行现有 Node 测试，确认拆分前因外部脚本尚未建立而失败。
- [x] 按现有注释边界原样移动 CSS 和 JS：共享/导航 → 卡牌库 → 机制 → 布局 → 入口；不得调整语句顺序或改写函数。
- [x] 运行 `tests/test_web.py`，保证所有现有行为测试通过，并核对构建脚本仍递归收集静态目录。

### Task 5: 编写 BWPro 集成契约

**Files:**
- Create: `docs/integration.md`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/terminology.md`
- Modify: `docs/superpowers/specs/2026-09-14-bwpdiy-design.md`

- [x] 按真实签名记录 `render_card`、`render_entity`、`render_portrait`、`render_mechanism` 的输入、返回、异常、路径和布局规则。
- [x] 提供可执行的 Pillow 保存 PNG 示例，说明 `width/height` 原生重绘及机制 `chars_per_line/font_scale` 的不同语义。
- [x] 明确默认安装仅带渲染依赖，WebGUI 使用 `web` extra；README 链接集成文档并移除 M4 待办表述。
- [x] 逐项核对文档中的字段名与源码，不承诺多卡图切换、批量导出等尚未实现能力。

### Task 6: 全量验收与收尾

**Files:**
- Modify: 本轮实际涉及文件

- [x] 运行 `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`。
- [x] 在隔离临时目录启动真实服务，请求 `/` 与全部静态 CSS/JS，再调用 `/api/shutdown` 验证正常退出。
- [x] 执行 `git diff --check`、检查最终 diff 与生成物，删除测试缓存及生成的布局备份。
- [x] 更新计划完成状态，提交并推送；不构建 exe、不上传 Release。
