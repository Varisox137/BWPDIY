# BWPro 集成契约对照审查报告

日期：2026-10-30

## 范围与结论

对照 `docs/integration.md` 与 BWPro 当前 `client/gui` 渲染适配层，检查导入方式、资源路径、渲染参数、异常处理、预热和缓存。BWPDIY 的 `render_card`、`render_entity`、`render_portrait`、`render_mechanism` 接口本身能够支撑现有集成；主要问题位于 BWPro 适配层的错误诊断、失败状态记录和开发环境路径解析，文档则可进一步说明这些边界。

本报告只记录审查结论，不要求修改 BWPDIY 渲染器 API。

## 高优先级问题

### 1. worktree 中默认 BWPDIY 根目录解析错误

BWPro `client/gui/portrait.py:18-21` 使用 `parents[3] / "BWPDIY"` 推导源码树。该推导在 `D:/Programming/BWPro` 主检出中成立，但在 `.worktrees/<分支>` 中会定位到不存在的 `.worktrees/BWPDIY`。

因此，即使按集成文档执行 `uv add --editable ../BWPDIY` 并成功导入包，`assets/` 的资源路径仍可能错误。大卡、小卡、头像和机制框随后一起进入回退路径。

建议：

- BWPro 的环境变量 `BWP_DIY_ROOT` 应始终优先于自动推导；非标准目录和 worktree 必须显式配置。
- 自动推导可向上寻找具有同级 `BWPDIY/assets` 的项目根，而不是固定 `parents[3]`。
- 集成文档应明确 editable 安装只解决 Python 导入，不会自动解决 `assets/` 路径。

### 2. 渲染异常被静默吞掉

集成文档第 7 节要求调用方“捕获并记录异常”。当前 BWPro 多处直接 `except Exception: return None`，没有日志，包括：

- `client/gui/cardart.py:364-365`、`:435-436`、`:656-657`、`:767-768`；
- `client/gui/portrait.py:203-204`、`:225-226`；
- `client/gui/mechanisms.py:175-176`；
- 部分卡牌配置解析失败也在 `cardart.py:281-282`、`portrait.py:82-83` 被静默忽略。

这会把资源缺失、路径错误、非法布局、非法尺寸和真实渲染缺陷全部表现为同一种“无图”。实际维护中，动画大卡图因浮点高度被拒绝后退回灰框，正是该问题隐藏根因的例子。

建议在 BWPro 边界记录渲染类型、卡牌/式神 id、资源根和异常堆栈，再返回明确的占位结果。不要在缺少上下文的情况下重复刷同一异常，也不要把异常文本直接拼入页面 HTML。

### 3. 预热会把渲染失败写成成功清单

BWPro `client/gui/prewarm.py:103-115` 未检查 `card_pixmap`/`entity_pixmap` 是否返回 `None`，就写入最新 `manifest.json`。下一次启动看到相同清单后会跳过合成，`client/gui/settings.py:36-44` 又仅按 entries 数量展示缓存状态，可能把全部失败显示为已生成。

建议：

- 只有实际得到非空 pixmap 的条目才计为成功；
- 失败条目不得写入可跳过后续重试的成功清单；
- 设置页同时显示成功、失败和跳过数量，并保留可查看的失败原因；
- 修复资源或配置后，失败条目应自动参与下一次重试。

## 中低优先级问题

### 4. 预热显式路径参数未传入渲染调用

`client/gui/prewarm.py:54-58` 接收 `library_dir/cache_dir` 并用其计算清单，但 `prewarm.py:104`、`:110` 的实际渲染调用未转发这两个参数，最终使用默认库和默认缓存目录。

默认启动流程目前不受影响；显式调用时会出现“清单来自 A、实际渲染与写入使用 B”的错配。建议转发参数，并增加非默认临时目录的集成测试。

### 5. 大卡框品未进入负载和布局选择

`client/gui/cardart.py:612-615` 只选取 artwork 和 faction_style，`cardart.py:638-639` 调用 `get_type_layout` 时未传 `frame_variant`，因此固定使用普通框布局。

这与集成文档第 3 节的框品契约不完整。当前 BWPro library 未使用蓝/黑/红框配置，所以暂无现存视觉影响；引入框品前应将 `frame_variant` 同时传入卡牌负载和 `get_type_layout`。

### 6. 机制框 badge 在适配层丢失

`client/gui/mechanisms.py:106-109` 已读取 `badge`，但 `mechanisms.py:158-168` 的缓存键和 `render_mechanism` 负载只包含 name/frame/text。

当前 library 的机制均为 skill 且 badge=null，暂无视觉影响。若启用 seal 的 bless/eclipse 角标，应把 badge 纳入渲染负载和缓存键。

### 7. 头像缓存存在极窄的陈旧边界

`client/gui/portrait.py:172-182` 以图片路径、mtime 和大小识别缓存。若同路径图片在保留时间戳且大小不变的情况下被替换，仍可能得到旧头像。大卡和小卡适配层已经使用内容 SHA-256，不受此边界影响。

该行为与集成文档“按修改时间识别更新”的字面说明一致，因此不是文档错误；若希望与大小卡具有相同可靠性，可改用内容摘要。

## 对 integration.md 的优化建议

### 1. 将安装方式改为两种明确路径

当前 `uv add --editable ../BWPDIY` 是有效方式，但不应写成唯一集成方式。建议分为：

- **Python 包集成**：editable 安装，适合标准同级目录和稳定开发环境；
- **源码树集成**：BWPro 通过 `BWP_DIY_ROOT` 定位包与 assets，通过 `BWP_DIY_LIBRARY` 定位卡牌和机制配置。

示例：

```bash
BWP_DIY_ROOT='D:/Programming/BWPDIY'
BWP_DIY_LIBRARY='D:/Programming/BWPro/library'
```

同时注明：worktree、非同级目录或便携部署必须显式设置资源根。

### 2. 区分三层缓存

第 8 节目前只说明 BWPDIY `AssetLibrary`。建议明确区分：

1. BWPDIY 内部字体、牌框和图片缓存；
2. BWPro 大卡/小卡/头像的磁盘或 LRU 缓存；
3. BWPro 启动预热的 manifest 成功清单。

“重启进程”和“图片 mtime 变化”并不必然使后两层全部失效。文档应说明由哪一层负责内容摘要、配置指纹和失败重试，避免用户误判缓存状态。

### 3. 增加失败处理清单

建议在第 7 节后增加调用方检查项：

- 捕获时记录渲染类型、实体 id 和异常堆栈；
- 占位图是 BWPro 的显示策略，不代表渲染成功；
- 预热、缓存状态和设置页不得把占位结果计为成功；
- 失败结果应可在资源修复后重试；
- 尺寸参数在适配层转换为正整数，非法输入不要静默吞掉。

### 4. 增加最小集成自检

建议提供四个无 WebGUI 的冒烟步骤：渲染一张大卡、一张小卡、一个头像和一个机制框；逐项检查返回图片非空，并故意使用一次非法尺寸确认异常能在调用方日志中定位。这样可以在启动完整 GUI 前区分安装、资源和适配问题。

## 推荐处理顺序

1. 修复 BWPro 异常日志、预热成功判定和 worktree 资源根；
2. 修复预热路径参数转发；
3. 在启用对应数据前补齐 frame_variant 和 badge；
4. 按需统一头像与大/小卡的内容摘要策略；
5. 补充集成文档的源码树配置、缓存边界和失败自检说明。
