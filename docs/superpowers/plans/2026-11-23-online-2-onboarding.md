# BWPDIY 在线版 2.0 引导 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新用户无需先理解布局、ID 或存储机制，即可在真实编辑器内完成第一张卡并导出 PNG；老用户可跳过并保留完整高级能力。

**Architecture:** 保留现有三栏渲染与 Worker，不引入框架。新增独立 `tutorial.js/css` 管理欢迎、步骤、目标高亮和草稿隔离；编辑器只提供草稿暂停保存等最小接口。教程使用真实控件和 BWPro 原始范例内容，不建立第二套制作流程。

**Tech Stack:** 原生 HTML/CSS/JavaScript、现有 Pyodide Worker、IndexedDB、localStorage、Playwright 临时浏览器验证、pytest。

## Global Constraints

- 仅修改在线原型；正式 exe 界面、版本号和发布流程不变。
- 不上传作品内容，不收集教程统计，不新增服务端 API。
- 教程中暂停草稿自动保存；退出恢复原草稿，完成后由用户决定是否保留教程作品。
- 手机提示不得遮挡目标控件；卡图双指手势仍不得缩放页面。
- 新静态资源加入服务端白名单和 Service Worker，递增 `RESOURCE_CACHE`。
- 首次使用说明自动弹窗由教程欢迎替代；使用说明仍可手动打开。

## 文件结构

- 新建 `prototype/pyodide/tutorial.js`：步骤状态、目标定位、示例、草稿快照与恢复。
- 新建 `prototype/pyodide/tutorial.css`：欢迎、目标高亮、桌面/手机提示层。
- 修改 `prototype/pyodide/index.html`：主界面文案、默认信息层级、教程结构。
- 修改 `prototype/pyodide/app.js`：首次入口、手动教程入口、教程期间暂停草稿写入。
- 修改 `prototype/pyodide/style.css`：主操作与折叠区样式。
- 修改 `prototype/pyodide/server.py`、`sw.js`：静态资源白名单与缓存版本。
- 修改 `tests/test_pyodide_prototype.py`：静态资源和安全回归。
- 更新 `README.md`、`AGENTS.md`、`docs/online-security.md`。

---

### Task 1: 默认界面信息层级

- [ ] 将在线主标签改为「制作 / 对局预览 / 高级布局」，导出作为唯一金色主按钮，刷新保持次按钮。
- [ ] 卡名和描述保持主流程可见；ID、版本日期与非必要外观项归入可展开高级区，已有草稿恢复逻辑不变。
- [ ] 左栏缓存、存储和草稿工具归入「数据与设置」，卡图上传仍可被教程直接定位。
- [ ] 用浏览器验证无草稿默认值、草稿恢复、各类型切换和按钮间距。

### Task 2: 第一张卡互动教程

- [ ] 新增首次欢迎：「开始第一张卡教程 / 直接使用」，老用户不自动显示。
- [ ] 实现真实控件高亮、步骤进度、上一步/下一步/退出和移动端底部提示。
- [ ] 教程步骤依次覆盖内容与范例、卡图上传或样图、卡图缩放/移动、高亮与内嵌图标、真实 PNG 导出。
- [ ] 在使用说明中提供「开始互动教程」，可随时重开。
- [ ] 添加 `tests/test_pyodide_prototype.py` 静态资源测试，先确认旧服务返回 404，再实现并验证 200。

### Task 3: 草稿隔离与完成选择

- [ ] 开始前用 `currentDraft()` 保存内存快照；教程中 `scheduleDraftSave/saveDraftNow` 不写 IndexedDB。
- [ ] 退出时通过 `restoreDraft()` 恢复原表单、卡图和布局；完成时提供「保留作品 / 恢复原草稿」。
- [ ] 只有完成、跳过或直接使用才记录本地教程已读状态；中途关闭浏览器不视为完成。
- [ ] 浏览器验证有草稿进入教程不会改变 IndexedDB，退出后恢复，保留作品后才真正保存。

### Task 4: 响应式、安全与文档收尾

- [ ] 验证 390px 手机、820px 平板、1440px 桌面目标定位和控件可用性。
- [ ] 验证教程期间自动渲染、上传、触屏手势、导出与离线重载；检查无横向溢出和页面误缩放。
- [ ] 运行 `PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q tests/test_pyodide_prototype.py tests/test_online_log_admin.py` 及所有修改 JS 的 `node --check`。
- [ ] 更新在线说明、安全边界和项目约定，清理临时测试工具，提交并推送开发分支。

## 完成标准

- 新用户能在真实编辑器中按引导完成并导出第一张卡，而不是只阅读弹窗。
- 老用户可直接使用；高级功能仍可达，草稿不被教程覆盖。
- 手机与桌面均可完成教程，服务端没有新增作品数据通道。
- 所有受影响测试和真实浏览器流程通过后再合并主分支；本分支不直接发布 2.0 Release。
