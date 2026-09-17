# 里程碑计划：编辑器主体骨架（M2+M3 骨架）+ 布局设置并入

日期：2026-09-17　状态：待批准

## 目标与范围

把布局配置工具从独立调参页升级为 DIY 编辑器主体的正式功能。用户已裁定：

- **范围 = 骨架先行**：编辑器主体（导航 + 卡牌库列表 + 卡牌编辑表单 + 实时预览复用）+ 布局设置迁入；**卡图上传、卡图拖拽/滚轮定位、PNG 导出、M4 集成留待下一轮**。
- **布局作用域 = 全局共用**：布局设置页改的是全局 `assets/layout.json`，不做项目级/卡级覆盖。

## 前置：调整批 3 修复轮（主上下文直接做，不委托）

审查（adjust3-review.md，DONE_WITH_CONCERNS）发现：

1. **[中] propagateFromCurrentType 镜像语义过宽**：`field` 被跨类型覆盖（式神/形态 `power`→`power+`、法术 `health+`→`health`，已在 assets/layout.json 造成实际数据污染）。
   - 修法：镜像改为**样式键白名单**——`size/icon_size/font_size/num_offset/gap/margin/base_size/star_size/num_size/font/style`；`kind/field/icon/icon_neg/pos/enabled` 一律不镜像。
   - 数据回退：assets/layout.json 三处 field 恢复原值（对齐 default_layout.json）。
2. **[低] signed 口径**：adjust3 的 `_STAT_SIGN = {战斗:"+-", 法术:"+"}` 整体由下表规则取代——法术觉醒 ±、非觉醒法术无任何角标（见第 4 项矩阵）。
3. **[低] GUI STAT_INPUTS 硬编码 field**：改为从布局 stat 元素的 `field` 派生，消除"改了没反应"类错位。
4. **[中] stat 适用矩阵钉死**（用户裁定，覆盖此前所有相关口径，作为渲染与 GUI 的唯一事实来源）：

   | 卡牌类型 | 左下 | 右下 | 符号 | 0 值 |
   |---|---|---|---|---|
   | 式神 | 力量（非负） | 生命（非负） | 无 | 照常绘制 |
   | 战斗 | 力量 | 护甲（正）/破甲（负，贴图自动换） | ± | 不绘制角标 |
   | 法术觉醒 | 力量 | 生命 | ± | 不绘制角标 |
   | 形态 | 力量（非负） | 生命（非负） | 无 | 照常绘制 |
   | 幻境 | — | 耐久（非负） | 无 | 照常绘制 |
   | 协战/非觉醒法术/其余一切组合 | — | — | — | **不提供输入框、也不绘制** |

   - 渲染层：badges.py stat 分支按 (type, field) 白名单+符号规则表实现，表外组合即使 card 带该字段也跳过；法术觉醒数值不限非负（目前游戏中均为非负，但工具不强制），符号按实际正负拼 +/−，0 不绘制。
   - GUI：STAT_INPUTS 按此表生成，非法组合不显示输入框。
5. 补测试：propagate 不覆盖 field/icon、上表全组合（绘制/省略/符号/贴图）的像素级或行为级断言、布局 field 与样卡口径一致回归。

## Task 1：store 层（bwpdiy/store/）

- 项目制存储（文件系统即数据库，设计文档 §3）：
  ```
  library/<项目名>/shikigami.yaml、cards/<卡名>.yaml、images/
  ```
- API：`list_projects / create_project / rename_project / delete_project / list_cards / load_card / save_card / delete_card`（纯函数 + Path 注入，不依赖 FastAPI）。
- schema 校验：按类型白名单（类型枚举、按类型必填字段、数值范围、派系/稀有度枚举），错误信息中文并指出字段名；保存时执行。
- PyYAML 依赖：`uv add pyyaml`（store/web 层可用，render 层红线不变）。
- TDD：CRUD 全路径 + 校验正反例 + 中文错误消息。

## Task 2：Web 后端扩展（bwpdiy/web/app.py）

- 项目/卡牌 REST：
  - `GET/POST /api/projects`、`PUT/DELETE /api/projects/{name}`
  - `GET /api/projects/{p}/cards`、`GET/PUT/DELETE /api/projects/{p}/cards/{card}`
  - `POST /api/projects/{p}/cards/{card}/preview` → PNG（复用 render_card，artwork 基准目录 = 项目 images/；缺图回退 tests/fixtures 占位或透明底，报告说明取舍）
- 卡牌保存前走 store 校验，422 返回中文错误。
- 页面路由：`/` → 编辑器主体页；布局设置作为主体内的 tab（不再单独 /layout 入口，或保留重定向兼容，实现时择一并记录）。
- create_app 增加 library_dir 参数（缺省项目根 library/）。

## Task 3：前端编辑器主体（static/editor.html，vanilla JS 无构建）

- 顶部 tab 导航：**卡牌库 / 布局设置**。
- 卡牌库 tab：左栏项目列表 + 项目内卡牌列表（新建/删除/重命名，复制可留待下轮）；中栏实时预览（复用既有防抖 preview 链路）；右栏卡牌表单——按类型动态显隐字段（复用批 3 的 stat 滚轮/式神名/子类型/描述 textarea 组件思路），表单变更即时校验 + 防抖预览；保存调 Task 2 API（422 错误显示在表单侧）。
- 布局设置 tab：迁入现有 layout.html 全部功能（六类型元素表/拖拽锚点/desc 矩形/实时预览/保存），预览样卡机制保持。
- 样式与交互与现有 layout.html 保持一致（同一套 CSS 约定）。

## Task 4：收尾

- 文档同步：README（进度、入口说明）、design.md §5/§10（布局设置并入、骨架/完整分期调整）、terminology.md 如需、AGENTS.md 如需。
- 精简复查：批 3 以来 diff 的删除清单式审查；layout.html 迁入后的死代码清理。
- 全量测试 + 终审（本轮全分支审查）。
- 记录遗留：上传/拖拽定位/导出/M4、propagate 白名单是否需覆盖新样式键。

## 执行方式

- 前置修复轮（含 stat 适用矩阵）派一个 coder 子代理做（TDD），完成后主上下文复核；Task 1-3 各派 coder 子代理，每任务后派审查子代理，有问题走修复轮；Task 4 主上下文收尾。
- 测试命令：`PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -m pytest -q`；迭代期只跑受影响文件，收尾全量。
- 中文 conventional commit，每次 commit 后 push；8630 用户服务进程不杀，冒烟用 TestClient/tmp_path。

## 验收标准

- `python -m bwpdiy` 打开 `/`：卡牌库 tab 可新建项目/卡牌、表单编辑实时预览、保存落盘 library/；布局设置 tab 功能与现 /layout 完全一致。
- 全量测试全绿（含新增 store/web 测试）。
- 布局全局语义不变：布局设置保存仍写 assets/layout.json，所有卡牌预览共用。
